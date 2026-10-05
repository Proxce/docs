#!/usr/bin/env python3
"""
intercom_workspaces.py - Export every Intercom article as MDX, split by
workspace and by state.

    GET /articles         every article summary, 150 per page
    GET /articles/{id}    the full article (workspace_id, state, body, ...)

Only GET endpoints are used; nothing is ever written back to Intercom.

Output (under --out, default ./intercom_workspaces):

    <workspace_id>/
        published/<id>-<slug>.mdx
        draft/<id>-<slug>.mdx
        images/intercom/<id>/...      screenshots, downloaded (CDN links expire)
        index.csv                     id, title, state, updated_at, url, file

Per-article JSON is cached under <out>/.cache/articles/ and reused when
`updated_at` matches the list endpoint, so a re-run only calls
/articles/{id} for articles that changed.

Usage:
    python intercom_workspaces.py --api-key <token>
    python intercom_workspaces.py --api-key <token> --limit 20      # smoke test
    python intercom_workspaces.py --api-key <token> --refresh       # ignore the cache
    python intercom_workspaces.py --api-key <token> --dry-run       # fetch, write no MDX

The token falls back to $INTERCOM_API_KEY, then ./.intercom_token, exactly as
intercom_fetch.py does.
"""

import argparse
import csv
import html
import os
import re
import sys
import time
from datetime import datetime, timezone

import intercom_fetch as fetchlib
import intercom_to_mintlify as convert

DEFAULT_OUT = "intercom_workspaces"
UNKNOWN_WORKSPACE = "_no_workspace"
UNKNOWN_STATE = "_no_state"


def safe_dirname(value, fallback):
    """Workspace ids and states become folder names; keep them filesystem-safe."""
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "")).strip("-.")
    return value or fallback


def iso(ts):
    if not ts:
        return ""
    return datetime.fromtimestamp(int(ts), timezone.utc).isoformat(timespec="seconds")


def article_to_mdx(art, image_root, download, dry_run, img_stats):
    """Convert one full article to an MDX page, the same way --migrate does."""
    article_id = str(art.get("id"))
    title = html.unescape((art.get("title") or "Untitled").strip())

    on_image = None
    if download:
        def on_image(u):
            return convert.download_image(u, image_root, article_id, dry_run, img_stats)

    body_mdx, _images, _videos = convert.html_to_mdx(
        art.get("body") or "", on_image=on_image,
        alt_prefix=convert.short_title(title, 40))
    body_mdx, keywords, _audit = convert.apply_template(body_mdx, mirror=True)
    body_mdx = convert.drop_repeated_title(body_mdx, title)
    return convert.build_mdx(art, body_mdx, icon=convert.DEFAULT_PAGE_ICON,
                             keywords=keywords)


def write_index(ws_dir, rows):
    path = os.path.join(ws_dir, "index.csv")
    cols = ["id", "title", "state", "created_at", "updated_at", "url", "file"]
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        for row in sorted(rows, key=lambda r: (r["state"], r["title"].lower())):
            writer.writerow(row)


def export(args):
    out = args.out
    cache = os.path.join(out, ".cache", "articles")

    fetchlib.log("[1/3] GET /articles ...")
    summaries = fetchlib.fetch_article_list(args.api_key, args.limit)
    fetchlib.log("      %d articles" % len(summaries))

    fetchlib.log("[2/3] GET /articles/{id} ...")
    articles = fetchlib.fetch_article_bodies(args.api_key, summaries, cache,
                                             refresh=args.refresh)

    fetchlib.log("[3/3] writing MDX ...")
    img_stats = {"saved": 0, "reused": 0, "bytes": 0,
                 "large": [], "oversize": [], "failed": []}
    rows_by_ws = {}
    counts = {}          # {workspace: {state: n}}
    empty, failed = [], []

    for art in articles:
        article_id = str(art.get("id"))
        workspace = safe_dirname(art.get("workspace_id"), UNKNOWN_WORKSPACE)
        state = safe_dirname(art.get("state"), UNKNOWN_STATE)
        title = html.unescape((art.get("title") or "Untitled").strip())

        if art.get("_fetch_error"):
            failed.append((article_id, title))
        if not (art.get("body") or "").strip():
            empty.append((article_id, state, title))   # still written, as a stub

        ws_dir = os.path.join(out, workspace)
        filename = "%s-%s.mdx" % (article_id, convert.page_slug(art))
        rel = "%s/%s" % (state, filename)

        text = article_to_mdx(art, ws_dir, not args.no_download_images,
                              args.dry_run, img_stats)
        if not args.dry_run:
            path = os.path.join(ws_dir, state, filename)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)

        rows_by_ws.setdefault(workspace, []).append({
            "id": article_id,
            "title": title,
            "state": state,
            "created_at": iso(art.get("created_at")),
            "updated_at": iso(art.get("updated_at")),
            "url": art.get("url") or "",
            "file": rel,
        })
        ws_counts = counts.setdefault(workspace, {})
        ws_counts[state] = ws_counts.get(state, 0) + 1

    if not args.dry_run:
        for workspace, rows in rows_by_ws.items():
            write_index(os.path.join(out, workspace), rows)

    print("")
    print("=" * 72)
    print("Intercom -> workspaces%s" % ("  (DRY RUN - nothing written)" if args.dry_run else ""))
    print("=" * 72)
    print("Articles : %d in %d workspace(s)" % (len(articles), len(counts)))
    for workspace in sorted(counts):
        states = ", ".join("%s %d" % (s, n) for s, n in sorted(counts[workspace].items()))
        print("   %-40s %s" % (workspace, states))
    print("Images   : %d saved, %d reused, %d failed"
          % (img_stats["saved"], img_stats["reused"], len(img_stats["failed"])))
    if empty:
        print("")
        print("EMPTY BODY - %d (written as stub pages):" % len(empty))
        for article_id, state, title in empty[:25]:
            print("   %-10s %-10s %s" % (article_id, state, title[:60]))
        if len(empty) > 25:
            print("   ... and %d more" % (len(empty) - 25))
    if failed:
        print("")
        print("404 ON /articles/{id} - %d (written from the list copy):" % len(failed))
        for article_id, title in failed[:25]:
            print("   %-10s %s" % (article_id, title[:70]))
    print("")
    print("Output   : %s/" % out)
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Export Intercom articles as MDX, grouped by workspace_id and state.")
    parser.add_argument(
        "--api-key", default=None,
        help="Intercom bearer token. Falls back to $INTERCOM_API_KEY, then "
             "./.intercom_token.")
    parser.add_argument("--out", default=DEFAULT_OUT,
                        help="output directory (default: %s)" % DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=None,
                        help="stop after N articles - use for a smoke test")
    parser.add_argument("--refresh", action="store_true",
                        help="ignore the cache and re-fetch every article")
    parser.add_argument("--no-download-images", action="store_true",
                        help="keep Intercom's image URLs (they expire within hours)")
    parser.add_argument("--dry-run", action="store_true",
                        help="fetch and report, but write no MDX, images or index")
    args = parser.parse_args()

    args.api_key = fetchlib.resolve_token(args.api_key)
    if not args.api_key:
        fetchlib.die("no API token. Provide one of:\n"
                     "  1. python intercom_workspaces.py --api-key <token>\n"
                     "  2. $env:INTERCOM_API_KEY = '<token>'   (PowerShell)\n"
                     "  3. put it in ./%s   (gitignored, one line)" % fetchlib.TOKEN_FILE)

    start = time.time()
    code = export(args)
    fetchlib.log("done in %.0fs" % (time.time() - start))
    return code


if __name__ == "__main__":
    sys.exit(main())
