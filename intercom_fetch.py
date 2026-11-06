#!/usr/bin/env python3
"""
intercom_fetch.py - Two-pass Intercom Help Center export.

Pass 1  GET /help_center/collections   -> the collection tree (product / section / sub-section)
Pass 2  GET /articles                  -> every article summary (id, title, parent_ids, url, ...)
Pass 3  GET /articles/{id}             -> the full article, including `body` and `statistics`

The list endpoint returns `body` but Intercom truncates or omits it on some
workspaces, and never returns `statistics`; pass 3 is what guarantees complete
content. Every article fetched in pass 3 is cached to disk, so a re-run only
pulls what changed (compared on `updated_at`).

DEPENDENCIES: none. Python 3.8+ standard library only.

Usage:
    python intercom_fetch.py --api-key dG9r...
    python intercom_fetch.py                      # token from $INTERCOM_API_KEY or API_KEY below
    python intercom_fetch.py --limit 25           # smoke test: first 25 articles only
    python intercom_fetch.py --no-bodies          # pass 1 + 2 only, skip the per-article calls
    python intercom_fetch.py --refresh            # ignore the cache, re-fetch every article
    python intercom_fetch.py --out export_2026    # write somewhere other than ./intercom_export

Outputs (under --out):
    collections.json      the raw collection tree plus a resolved id -> path map
    articles.json         every article, full body, with product/collection resolved
    articles/<id>.json    one file per article (the cache; safe to delete)
    articles_index.csv    flat index for triage in Excel/Sheets
    summary.txt           product -> collection -> count tree
"""

# ===========================================================================
#  PUT YOUR BEARER TOKEN HERE (or leave empty and use the env var / flag)
#
#  Precedence:  --api-key flag  >  $INTERCOM_API_KEY  >  this constant
#      PowerShell:  $env:INTERCOM_API_KEY = "your_token"
#      bash:        export INTERCOM_API_KEY=your_token
#
#  Sent as:  Authorization: Bearer <token>
#  Needs the "Read Help Center content" scope.
# ===========================================================================
API_KEY = ""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

TOKEN_FILE = ".intercom_token"

API_ROOT = "https://api.intercom.io"
API_VERSION = "2.11"

PER_PAGE = 150          # Intercom caps list endpoints at 150; the default is 25
MAX_RETRIES = 5
RETRY_BACKOFF = 2.0     # seconds, doubled per attempt
PACE = 0.06             # seconds between calls; Intercom allows ~1000/min
UNASSIGNED = "_Unassigned"


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

def api_get(path, token, params=None):
    """GET an Intercom endpoint, retrying on 429 and 5xx. Returns parsed JSON."""
    url = API_ROOT + path
    if params:
        url += "?" + urllib.parse.urlencode(params)

    for attempt in range(MAX_RETRIES):
        req = urllib.request.Request(url)
        req.add_header("Authorization", "Bearer %s" % token)
        req.add_header("Accept", "application/json")
        req.add_header("Intercom-Version", API_VERSION)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:400]
            if exc.code in (401, 403):
                die("HTTP %d from %s\n%s\n\nThe token is missing, wrong, or "
                    "lacks the 'Read Help Center content' scope."
                    % (exc.code, path, body))
            if exc.code == 404:
                return None
            if exc.code == 429 or exc.code >= 500:
                if attempt == MAX_RETRIES - 1:
                    die("HTTP %d from %s after %d attempts\n%s"
                        % (exc.code, path, MAX_RETRIES, body))
                wait = float(exc.headers.get("Retry-After") or 0) or \
                    RETRY_BACKOFF * (2 ** attempt)
                log("  rate limited (%d), waiting %.0fs" % (exc.code, wait))
                time.sleep(wait)
                continue
            die("HTTP %d from %s\n%s" % (exc.code, path, body))
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == MAX_RETRIES - 1:
                die("network error on %s: %s" % (path, exc))
            time.sleep(RETRY_BACKOFF * (2 ** attempt))
    return None


#: How many consecutive all-duplicate pages before giving up on a walk.
STALE_PAGES = 3


def paginate(path, token):
    """Yield every item from a paginated list endpoint.

    Handles both shapes Intercom returns: cursor pagination
    (`pages.next.starting_after`) and plain page numbers (`pages.total_pages`).
    """
    params = {"per_page": PER_PAGE}
    page_no = 1
    seen = set()
    duplicates = 0
    cursors = set()
    stale = 0

    while True:
        payload = api_get(path, token, params) or {}
        data = payload.get("data") or []

        # Every item is yielded at most once. Intercom will happily serve the
        # same page again - a stalled cursor, or a page that shifts under you
        # while you are reading it - and without this the walk never ends and
        # the totals come out several times larger than the help centre.
        fresh = 0
        for item in data:
            key = item.get("id") if isinstance(item, dict) else None
            if key is not None:
                key = str(key)
                if key in seen:
                    duplicates += 1
                    continue
                seen.add(key)
            fresh += 1
            yield item

        # An empty page ends the walk. A page that was entirely duplicates does
        # not: the cursor may still be advancing past a page that shifted while
        # it was being read. Only a run of them means the endpoint is stuck.
        if not data:
            if duplicates:
                log("  (%s: %d duplicate(s) skipped, %d unique)"
                    % (path, duplicates, len(seen)))
            return
        stale = 0 if fresh else stale + 1
        if stale >= STALE_PAGES:
            log("  (%s: %d pages with nothing new, stopping at %d unique)"
                % (path, stale, len(seen)))
            return

        pages = payload.get("pages") or {}
        nxt = pages.get("next")
        if isinstance(nxt, dict) and nxt.get("starting_after"):
            cursor = nxt["starting_after"]
            params = {"per_page": PER_PAGE, "starting_after": cursor}
        elif isinstance(nxt, str) and nxt:
            # absolute URL form: pull the query back off it
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(nxt).query)
            params = {k: v[0] for k, v in qs.items()}
            cursor = params.get("starting_after") or params.get("page")
        else:
            total = pages.get("total_pages") or 1
            if page_no >= total:
                if duplicates:
                    log("  (%s: %d duplicate(s) skipped, %d unique)"
                        % (path, duplicates, len(seen)))
                return
            page_no += 1
            cursor = page_no
            params = {"per_page": PER_PAGE, "page": page_no}

        # A cursor that repeats means the endpoint is pointing back at a page
        # already read; following it again would loop for ever.
        if cursor is not None:
            if cursor in cursors:
                log("  (%s: cursor repeated, stopping at %d unique)"
                    % (path, len(seen)))
                return
            cursors.add(cursor)
        time.sleep(PACE)


# --------------------------------------------------------------------------
# Collections -> readable hierarchy
# --------------------------------------------------------------------------

def fetch_collections(token):
    """Return (raw_list, id -> [ancestor names ... own name])."""
    raw = list(paginate("/help_center/collections", token))
    by_id = {str(c["id"]): c for c in raw}

    def path_of(cid, seen=None):
        seen = seen or set()
        c = by_id.get(str(cid))
        if not c or str(cid) in seen:
            return []
        seen.add(str(cid))
        parent = c.get("parent_id")
        prefix = path_of(parent, seen) if parent else []
        return prefix + [clean(c.get("name") or "")]

    return raw, {cid: path_of(cid) for cid in by_id}


def resolve_placement(article, paths):
    """Turn parent_ids into (product, collection, full path string).

    `parent_ids` is ordered root-first, so the deepest entry is the collection
    the article actually sits in. Articles with no parent land in _Unassigned.
    """
    parents = [str(p) for p in (article.get("parent_ids") or [])]
    deepest = None
    for pid in reversed(parents):
        if paths.get(pid):
            deepest = paths[pid]
            break
    if not deepest:
        pid = str(article.get("parent_id") or "")
        deepest = paths.get(pid) or []
    if not deepest:
        return UNASSIGNED, UNASSIGNED, UNASSIGNED
    product = deepest[0]
    collection = deepest[-1]
    return product, collection, " / ".join(deepest)


# --------------------------------------------------------------------------
# Articles
# --------------------------------------------------------------------------

def fetch_article_list(token, limit=None):
    out = []
    for art in paginate("/articles", token):
        out.append(art)
        if limit and len(out) >= limit:
            break
        if len(out) % 150 == 0:
            log("  listed %d articles" % len(out))
    return out


def fetch_article_bodies(token, summaries, cache_dir, refresh=False):
    """Pass 3: GET /articles/{id} for each summary, using the on-disk cache.

    A cached copy is reused when its `updated_at` matches the one the list
    endpoint just reported, so re-runs only pay for articles that changed.
    """
    os.makedirs(cache_dir, exist_ok=True)
    full, hits, misses = [], 0, 0

    for i, summary in enumerate(summaries, 1):
        aid = str(summary["id"])
        cache_file = os.path.join(cache_dir, "%s.json" % aid)

        cached = None
        if not refresh and os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as fh:
                    cached = json.load(fh)
            except (ValueError, OSError):
                cached = None

        if cached and cached.get("updated_at") == summary.get("updated_at"):
            full.append(cached)
            hits += 1
        else:
            art = api_get("/articles/%s" % aid, token)
            if art is None:
                log("  !! %s returned 404, keeping the list-endpoint copy" % aid)
                art = dict(summary)
                art["_fetch_error"] = "404 on /articles/%s" % aid
            with open(cache_file, "w", encoding="utf-8") as fh:
                json.dump(art, fh, ensure_ascii=False, indent=2)
            full.append(art)
            misses += 1
            time.sleep(PACE)

        if i % 100 == 0 or i == len(summaries):
            log("  %d/%d articles (%d cached, %d fetched)"
                % (i, len(summaries), hits, misses))

    return full


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

TAG_RE = re.compile(r"<[^>]+>")


def word_count(html):
    return len(TAG_RE.sub(" ", html or "").split())


def write_outputs(out_dir, raw_collections, paths, articles):
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(out_dir, "collections.json"), "w", encoding="utf-8") as fh:
        json.dump({"fetched_at": now_iso(),
                   "count": len(raw_collections),
                   "collections": raw_collections,
                   "paths": paths}, fh, ensure_ascii=False, indent=2)

    records = []
    for art in articles:
        product, collection, full_path = resolve_placement(art, paths)
        body = art.get("body") or ""
        records.append({
            "id": str(art.get("id")),
            "title": clean(art.get("title") or ""),
            "product": product,
            "collection": collection,
            "collection_path": full_path,
            "state": art.get("state"),
            "url": art.get("url"),
            "author_id": art.get("author_id"),
            "created_at": art.get("created_at"),
            "updated_at": art.get("updated_at"),
            "word_count": word_count(body),
            "image_count": body.count("<img"),
            "body": body,
            "description": art.get("description") or "",
            "statistics": art.get("statistics") or {},
            "parent_ids": art.get("parent_ids") or [],
        })

    with open(os.path.join(out_dir, "articles.json"), "w", encoding="utf-8") as fh:
        json.dump({"fetched_at": now_iso(),
                   "count": len(records),
                   "articles": records}, fh, ensure_ascii=False, indent=2)

    cols = ["id", "title", "product", "collection", "collection_path", "state",
            "word_count", "image_count", "created_at", "updated_at", "url"]
    csv_path = os.path.join(out_dir, "articles_index.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for rec in sorted(records, key=lambda r: (r["product"], r["collection"], r["title"])):
            writer.writerow(rec)

    return records


def write_summary(out_dir, records):
    tree = {}
    for rec in records:
        tree.setdefault(rec["product"], {}).setdefault(rec["collection"], 0)
        tree[rec["product"]][rec["collection"]] += 1

    lines = ["Intercom Help Center - %d articles in %d products (%s)"
             % (len(records), len(tree), now_iso()), ""]
    empty = [r for r in records if r["word_count"] == 0]
    for product in sorted(tree, key=lambda p: -sum(tree[p].values())):
        lines.append("== %s  (%d)" % (product, sum(tree[product].values())))
        for coll, n in sorted(tree[product].items(), key=lambda kv: -kv[1]):
            lines.append("     - %-60s [%d]" % (coll[:60], n))
        lines.append("")
    if empty:
        lines.append("%d articles have an empty body:" % len(empty))
        for rec in empty[:50]:
            lines.append("     %s  %s" % (rec["id"], rec["title"][:70]))

    text = "\n".join(lines)
    with open(os.path.join(out_dir, "summary.txt"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    return text


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def clean(text):
    """Collapse whitespace and decode the HTML entities Intercom leaves in names."""
    text = (text or "").replace("&amp;", "&").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip()


def token_from_file(path=TOKEN_FILE):
    """Read the bearer token from a gitignored file.

    Lets the token live on disk without going into a tracked source file or a
    shell history. Blank lines and # comments are ignored.
    """
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                return line
    return ""


def resolve_token(cli_value=None):
    """--api-key  >  $INTERCOM_API_KEY / $INTERCOM_TOKEN  >  .intercom_token  >  API_KEY"""
    return (cli_value
            or os.environ.get("INTERCOM_API_KEY")
            or os.environ.get("INTERCOM_TOKEN")
            or token_from_file()
            or API_KEY)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(msg):
    sys.stderr.write(msg.encode("ascii", "replace").decode("ascii") + "\n")
    sys.stderr.flush()


def die(msg):
    log("\nERROR: %s" % msg)
    sys.exit(1)


# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fetch every Intercom Help Center article, with full bodies.")
    parser.add_argument(
        "--api-key", default=None,
        help="Intercom bearer token. Falls back to $INTERCOM_API_KEY, then "
             "./.intercom_token, then the API_KEY constant.")
    parser.add_argument("--out", default="intercom_export",
                        help="output directory (default: intercom_export)")
    parser.add_argument("--limit", type=int, default=None,
                        help="stop after N articles - use for a smoke test")
    parser.add_argument("--no-bodies", action="store_true",
                        help="skip pass 3; keep only what the list endpoint returned")
    parser.add_argument("--refresh", action="store_true",
                        help="ignore the cache and re-fetch every article")
    args = parser.parse_args()

    args.api_key = resolve_token(args.api_key)
    if not args.api_key:
        die("no API token. Provide one of:\n"
            "  1. put it in ./%s   (gitignored, one line)\n"
            "  2. $env:INTERCOM_API_KEY = '<token>'   (PowerShell)\n"
            "  3. python intercom_fetch.py --api-key <token>" % TOKEN_FILE)

    start = time.time()

    log("[1/3] fetching collection tree ...")
    raw_collections, paths = fetch_collections(args.api_key)
    log("      %d collections" % len(raw_collections))

    log("[2/3] listing articles ...")
    summaries = fetch_article_list(args.api_key, args.limit)
    log("      %d articles" % len(summaries))

    if args.no_bodies:
        log("[3/3] skipped (--no-bodies)")
        articles = summaries
    else:
        log("[3/3] fetching full article content ...")
        articles = fetch_article_bodies(
            args.api_key, summaries,
            os.path.join(args.out, "articles"), refresh=args.refresh)

    records = write_outputs(args.out, raw_collections, paths, articles)
    print(write_summary(args.out, records))

    log("\ndone in %.0fs -> %s/" % (time.time() - start, args.out))
    log("  articles.json        full content, product/collection resolved")
    log("  articles_index.csv   flat index for triage")
    log("  summary.txt          the tree printed above")


if __name__ == "__main__":
    main()
