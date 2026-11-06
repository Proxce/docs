#!/usr/bin/env python3
"""
oloid.py - Fetch every Intercom Help Center article via the REST API and export
them to CSV, one file per product (top-level collection), plus a reconciliation
report showing exactly what was fetched and what was not.

DEPENDENCIES: none. Python 3.8+ standard library only.
See requirements.txt - there is nothing to pip install and nothing to remove later.

Usage:
    python oloid.py                          # token from API_KEY below or $INTERCOM_API_KEY
    python oloid.py --api-key dG9r...
    python oloid.py --split workspace_id     # split by workspace instead of product
    python oloid.py --no-collections         # skip product lookup, 1 fewer API call
    python oloid.py --no-state               # stateless snapshot
"""

# ===========================================================================
#  PUT YOUR BEARER TOKEN HERE
#  ---------------------------------------------------------------------
#  Paste the Intercom access token between the quotes, e.g.
#      API_KEY = "dG9rOjE2NGYyNzE4X2E5..."
#
#  Precedence:  --api-key flag  >  $INTERCOM_API_KEY env var  >  this constant
#
#  Safer than hardcoding (recommended if this file is committed to git):
#      PowerShell:  $env:INTERCOM_API_KEY = "your_token"
#      bash:        export INTERCOM_API_KEY=your_token
#
#  The token is sent as:  Authorization: Bearer <API_KEY>
#  Get one at: Intercom > Settings > Integrations > Developer Hub > your app
#              > Authentication.  It needs the "Read Help Center content" scope.
# ===========================================================================
API_KEY = ""

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API_ROOT = "https://api.intercom.io"
ARTICLES_PATH = "/articles"
COLLECTIONS_PATH = "/help_center/collections"
API_VERSION = "2.11"

# Intercom caps per_page at 150 for list endpoints; the default is 25.
DEFAULT_PER_PAGE = 150
MAX_RETRIES = 5
RETRY_BACKOFF = 2.0  # seconds, doubled per attempt
UNASSIGNED = "_Unassigned"

# Columns written to every CSV. `hash` and `status` are still computed and used
# for change tracking (state file + _report.csv), they are just not exported here.
CSV_COLUMNS = [
    "order",
    "product",
    "collection",
    "workspace_id",
    "article_id",
    "title",
    "url",
    "state",
    "created_at",
    "updated_at",
]


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

class IntercomError(RuntimeError):
    """A request failed in a way that is not worth retrying."""


def request_json(url, token, timeout=30):
    """GET a URL with bearer auth, retrying on 429 and 5xx. Returns parsed JSON."""
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", "Bearer %s" % token)
    req.add_header("Accept", "application/json")
    req.add_header("Intercom-Version", API_VERSION)
    req.add_header("User-Agent", "oloid-article-export/1.1")

    delay = RETRY_BACKOFF
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:400]
            if exc.code in (401, 403):
                raise IntercomError(
                    "Auth failed (HTTP %s). Check the bearer token at the top of this "
                    "file (API_KEY) or $INTERCOM_API_KEY, and that it has Help Center "
                    "read scope.\n%s" % (exc.code, body)
                )
            if exc.code == 429:
                reset = exc.headers.get("X-RateLimit-Reset")
                wait = delay
                if reset and reset.isdigit():
                    wait = max(1.0, int(reset) - time.time())
                sys.stderr.write(
                    "  rate limited, waiting %.0fs (attempt %d/%d)\n"
                    % (wait, attempt, MAX_RETRIES)
                )
                time.sleep(min(wait, 60))
                last_error = "HTTP 429"
                continue
            if 500 <= exc.code < 600:
                sys.stderr.write(
                    "  HTTP %s, retrying in %.0fs (attempt %d/%d)\n"
                    % (exc.code, delay, attempt, MAX_RETRIES)
                )
                time.sleep(delay)
                delay *= 2
                last_error = "HTTP %s" % exc.code
                continue
            raise IntercomError("HTTP %s from %s\n%s" % (exc.code, url, body))
        except (urllib.error.URLError, TimeoutError) as exc:
            sys.stderr.write(
                "  network error (%s), retrying in %.0fs (attempt %d/%d)\n"
                % (exc, delay, attempt, MAX_RETRIES)
            )
            time.sleep(delay)
            delay *= 2
            last_error = str(exc)

    raise IntercomError("Gave up on %s after %d attempts (%s)" % (url, MAX_RETRIES, last_error))


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------

def build_url(path, per_page, page=None, starting_after=None):
    params = {"per_page": str(per_page)}
    if starting_after:
        params["starting_after"] = starting_after
    elif page:
        params["page"] = str(page)
    return "%s%s?%s" % (API_ROOT, path, urllib.parse.urlencode(params))


def fetch_paginated(path, token, per_page, label_noun):
    """Walk every page of a list endpoint.

    Intercom returns page-number metadata and, on newer versions, a cursor in
    pages.next. Cursor is preferred when present; page numbers are the fallback.

    Returns (items, meta) where meta records what the API claimed to hold.
    """
    items = []
    seen_ids = set()
    meta = {
        "total_count": None,
        "total_pages": None,
        "pages_fetched": 0,
        "duplicates_skipped": 0,
        "failed_pages": [],
    }

    page_num = 1
    cursor = None

    while True:
        url = build_url(path, per_page, page=page_num, starting_after=cursor)
        label = "cursor %s" % cursor[:12] if cursor else "page %d" % page_num
        sys.stderr.write("Fetching %s %s ...\n" % (label_noun, label))

        try:
            payload = request_json(url, token)
        except IntercomError as exc:
            if not items:
                raise  # nothing salvageable, surface it
            sys.stderr.write("  FAILED %s: %s\n" % (label, exc))
            meta["failed_pages"].append({"page": label, "error": str(exc)})
            break

        meta["pages_fetched"] += 1

        if meta["total_count"] is None:
            meta["total_count"] = payload.get("total_count")
        pages = payload.get("pages") or {}
        if meta["total_pages"] is None:
            meta["total_pages"] = pages.get("total_pages")

        batch = payload.get("data") or []
        for item in batch:
            iid = str(item.get("id", ""))
            if iid and iid in seen_ids:
                meta["duplicates_skipped"] += 1
                continue
            seen_ids.add(iid)
            items.append(item)

        sys.stderr.write("  got %d (running total %d)\n" % (len(batch), len(items)))

        # Decide how to advance.
        next_page = pages.get("next")
        if isinstance(next_page, dict) and next_page.get("starting_after"):
            cursor = next_page["starting_after"]
            page_num = None
            continue
        if isinstance(next_page, str) and next_page:
            # Older shape: pages.next is a full URL.
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(next_page).query)
            if qs.get("starting_after"):
                cursor = qs["starting_after"][0]
                page_num = None
                continue
            if qs.get("page"):
                cursor = None
                page_num = int(qs["page"][0])
                continue

        total_pages = pages.get("total_pages")
        current = pages.get("page", page_num)
        if total_pages and current and int(current) < int(total_pages):
            cursor = None
            page_num = int(current) + 1
            continue

        if not batch:
            break
        if total_pages is None and len(batch) == per_page:
            # No metadata at all: keep going until a short page comes back.
            cursor = None
            page_num = (page_num or 1) + 1
            continue

        break

    return items, meta


# --------------------------------------------------------------------------
# Collections -> product names
# --------------------------------------------------------------------------

def build_collection_index(collections):
    """id -> {name, parent_id}. Sections are collections that have a parent_id."""
    index = {}
    for coll in collections:
        cid = str(coll.get("id", ""))
        if not cid:
            continue
        parent = coll.get("parent_id")
        index[cid] = {
            "name": (coll.get("name") or "").strip(),
            "parent_id": str(parent) if parent not in (None, "") else None,
        }
    return index


def resolve_product(article, index):
    """Map an article to (product, collection, collection_id).

    product    = name of the top-level collection (walk parent_id up to the root)
    collection = name of the immediate collection/section the article sits in
    """
    candidates = [str(p) for p in (article.get("parent_ids") or []) if p not in (None, "")]
    if article.get("parent_id") not in (None, ""):
        candidates.append(str(article["parent_id"]))

    # parent_ids is ordered root-first, so the last known id is the deepest.
    chosen = None
    for cid in candidates:
        if cid in index:
            chosen = cid
    if chosen is None:
        return UNASSIGNED, UNASSIGNED, (candidates[-1] if candidates else "")

    collection_name = index[chosen]["name"] or UNASSIGNED

    root = chosen
    seen = {root}
    while True:
        parent = index.get(root, {}).get("parent_id")
        if not parent or parent not in index or parent in seen:
            break
        seen.add(parent)
        root = parent

    return (index[root]["name"] or UNASSIGNED), collection_name, chosen


# --------------------------------------------------------------------------
# Transform
# --------------------------------------------------------------------------

def article_hash(article):
    """Stable identity hash: the same article always produces the same value."""
    basis = "|".join([
        str(article.get("workspace_id", "")),
        str(article.get("id", "")),
        str(article.get("url", "")),
    ])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def iso(ts):
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError, OverflowError):
        return str(ts)


def to_row(article, order, status, index):
    product, collection, collection_id = resolve_product(article, index)
    parents = article.get("parent_ids") or []
    return {
        "hash": article_hash(article),
        "order": order,
        "product": product,
        "collection": collection,
        "workspace_id": article.get("workspace_id") or "unknown",
        "article_id": article.get("id", ""),
        "title": (article.get("title") or "").strip(),
        "url": article.get("url") or "",
        "state": article.get("state") or "",
        "collection_id": collection_id,
        "parent_ids": ";".join(str(p) for p in parents),
        "created_at": iso(article.get("created_at")),
        "updated_at": iso(article.get("updated_at")),
        "status": status,
    }


def classify(article, previous):
    """NEW / UNCHANGED / UPDATED, based on the hash already being tracked."""
    prior = previous.get(article_hash(article))
    if prior is None:
        return "NEW"
    if str(prior.get("updated_at")) != str(article.get("updated_at")):
        return "UPDATED"
    return "UNCHANGED"


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def safe_name(value):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("_")
    return cleaned or "unknown"


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_outputs(out_dir, rows, removed_rows, meta, coll_meta, split_key):
    os.makedirs(out_dir, exist_ok=True)
    written = []

    # The CSVs are a clean snapshot of what the API returns now. Articles that
    # disappeared have no row to carry, so they are reported separately below.
    all_path = os.path.join(out_dir, "_all_articles.csv")
    write_csv(all_path, rows)
    written.append(all_path)

    groups = {}
    for row in rows:
        groups.setdefault(row[split_key], []).append(row)

    for group, group_rows in sorted(groups.items()):
        path = os.path.join(out_dir, "%s.csv" % safe_name(group))
        write_csv(path, group_rows)
        written.append(path)

    report_path = os.path.join(out_dir, "_report.csv")
    with open(report_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["metric", "value"])
        writer.writerow(["generated_at", datetime.now(timezone.utc).isoformat()])
        writer.writerow(["split_by", split_key])
        writer.writerow(["api_total_count", meta["total_count"]])
        writer.writerow(["articles_fetched", len(rows)])
        missing = ""
        if isinstance(meta["total_count"], int):
            missing = meta["total_count"] - len(rows)
        writer.writerow(["not_fetched", missing])
        writer.writerow(["api_total_pages", meta["total_pages"]])
        writer.writerow(["pages_fetched", meta["pages_fetched"]])
        writer.writerow(["duplicates_skipped", meta["duplicates_skipped"]])
        writer.writerow(["failed_pages", len(meta["failed_pages"])])
        writer.writerow(["collections_fetched", coll_meta.get("fetched", "skipped")])
        writer.writerow(["groups", len(groups)])
        writer.writerow([])
        writer.writerow(["breakdown", "count"])
        tracked = rows + removed_rows
        for status in ("NEW", "UPDATED", "UNCHANGED", "REMOVED"):
            writer.writerow([status, sum(1 for r in tracked if r["status"] == status)])
        writer.writerow([])
        writer.writerow(["article_state", "count"])
        states = {}
        for row in rows:
            key = row["state"] or "(none)"
            states[key] = states.get(key, 0) + 1
        for state, count in sorted(states.items()):
            writer.writerow([state, count])
        writer.writerow([])
        writer.writerow([split_key, "articles"])
        for group, group_rows in sorted(groups.items()):
            writer.writerow([group, len(group_rows)])

        # Which specific articles changed, since the CSVs no longer carry a status column.
        changed = [r for r in rows if r["status"] in ("NEW", "UPDATED")]
        if changed:
            writer.writerow([])
            writer.writerow(["change", "product", "article_id", "title", "url"])
            for row in changed:
                writer.writerow([row["status"], row["product"], row["article_id"], row["title"], row["url"]])
        if removed_rows:
            writer.writerow([])
            writer.writerow(["removed", "product", "article_id", "title", "url"])
            for row in removed_rows:
                writer.writerow(["REMOVED", row["product"], row["article_id"], row["title"], row["url"]])

        if meta["failed_pages"]:
            writer.writerow([])
            writer.writerow(["failed_page", "error"])
            for failure in meta["failed_pages"]:
                writer.writerow([failure["page"], failure["error"]])
    written.append(report_path)

    return written, groups


# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------

def load_state(path):
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh).get("articles", {})
    except (ValueError, OSError) as exc:
        sys.stderr.write("Could not read state file %s (%s), treating as empty.\n" % (path, exc))
        return {}


def save_state(path, rows):
    payload = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "articles": {
            row["hash"]: {
                "id": row["article_id"],
                "title": row["title"],
                "url": row["url"],
                "product": row["product"],
                "collection": row["collection"],
                "workspace_id": row["workspace_id"],
                "updated_at": row["_raw_updated_at"],
            }
            for row in rows
        },
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Export all Intercom Help Center articles to CSV, split by product."
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("INTERCOM_API_KEY") or os.environ.get("INTERCOM_TOKEN") or API_KEY,
        help="Intercom bearer token. Defaults to $INTERCOM_API_KEY, then the API_KEY constant.",
    )
    parser.add_argument("--out", default="output", help="Output directory (default: output)")
    parser.add_argument(
        "--split",
        choices=["product", "collection", "workspace_id"],
        default="product",
        help="Which column gets its own CSV file (default: product)",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=DEFAULT_PER_PAGE,
        help="Items per request, 1-150 (default: %d)" % DEFAULT_PER_PAGE,
    )
    parser.add_argument(
        "--no-collections",
        action="store_true",
        help="Skip the collections lookup; every article lands under %s." % UNASSIGNED,
    )
    parser.add_argument(
        "--state",
        default="oloid_state.json",
        help="State file for NEW/UPDATED/UNCHANGED/REMOVED (default: oloid_state.json)",
    )
    parser.add_argument("--no-state", action="store_true", help="Stateless snapshot.")
    args = parser.parse_args()

    if not args.api_key:
        parser.error(
            "No bearer token found. Either:\n"
            "  1. set API_KEY = \"your_token\" at the top of oloid.py, or\n"
            "  2. $env:INTERCOM_API_KEY = 'your_token'   (PowerShell), or\n"
            "  3. python oloid.py --api-key your_token"
        )

    per_page = max(1, min(args.per_page, 150))
    if per_page != args.per_page:
        sys.stderr.write("Clamped --per-page to %d (Intercom allows 1-150).\n" % per_page)

    state_path = None if args.no_state else args.state
    previous = load_state(state_path)

    # 1. Collections -> product names
    index = {}
    coll_meta = {}
    if not args.no_collections:
        collections, _ = fetch_paginated(COLLECTIONS_PATH, args.api_key, per_page, "collections")
        index = build_collection_index(collections)
        coll_meta = {"fetched": len(collections)}
        roots = sum(1 for v in index.values() if not v["parent_id"])
        sys.stderr.write("  %d collections (%d top-level products)\n" % (len(index), roots))

    # 2. Articles
    articles, meta = fetch_paginated(ARTICLES_PATH, args.api_key, per_page, "articles")

    rows = []
    current_hashes = set()
    for order, article in enumerate(articles, start=1):
        status = "TRACKED" if args.no_state else classify(article, previous)
        row = to_row(article, order, status, index)
        row["_raw_updated_at"] = article.get("updated_at")
        rows.append(row)
        current_hashes.add(row["hash"])

    removed_rows = []
    if not args.no_state:
        for h, prior in previous.items():
            if h in current_hashes:
                continue
            removed_rows.append({
                "hash": h,
                "order": "",
                "product": prior.get("product") or UNASSIGNED,
                "collection": prior.get("collection") or UNASSIGNED,
                "workspace_id": prior.get("workspace_id") or "unknown",
                "article_id": prior.get("id", ""),
                "title": prior.get("title") or "",
                "url": prior.get("url") or "",
                "state": "",
                "collection_id": "",
                "parent_ids": "",
                "created_at": "",
                "updated_at": iso(prior.get("updated_at")),
                "status": "REMOVED",
            })

    written, groups = write_outputs(args.out, rows, removed_rows, meta, coll_meta, args.split)

    if not args.no_state:
        save_state(state_path, rows)

    # ---- console summary: what was fetched, and what was not ----
    total = meta["total_count"]
    print("")
    print("=" * 64)
    print("Intercom article export complete")
    print("=" * 64)
    print("API reported total_count : %s" % total)
    print("Articles fetched         : %d" % len(rows))
    if isinstance(total, int):
        gap = total - len(rows)
        print("NOT fetched              : %d%s" % (gap, "" if gap == 0 else "   <-- investigate"))
    else:
        print("NOT fetched              : unknown (API did not report total_count)")
    print("Pages fetched            : %s of %s" % (meta["pages_fetched"], meta["total_pages"]))
    print("Collections fetched      : %s" % coll_meta.get("fetched", "skipped"))
    if meta["duplicates_skipped"]:
        print("Duplicates skipped       : %d" % meta["duplicates_skipped"])
    if meta["failed_pages"]:
        print("Failed pages             : %d" % len(meta["failed_pages"]))
        for failure in meta["failed_pages"]:
            print("   - %s: %s" % (failure["page"], failure["error"]))
    print("")
    if not args.no_state:
        counts = {}
        for row in rows + removed_rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        print("Tracking: " + ", ".join(
            "%s=%d" % (k, counts.get(k, 0)) for k in ("NEW", "UPDATED", "UNCHANGED", "REMOVED")
        ))
    print("")
    print("Articles per %s:" % args.split)
    for group, group_rows in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        print("   %-42s %4d" % (group[:42], len(group_rows)))
    unassigned = len(groups.get(UNASSIGNED, []))
    if unassigned:
        print("   (%d article(s) had no resolvable collection)" % unassigned)
    print("")
    print("Files written:")
    for path in written:
        print("   %s" % path)
    print("")

    return 1 if meta["failed_pages"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except IntercomError as exc:
        sys.stderr.write("\nERROR: %s\n" % exc)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.stderr.write("\nInterrupted.\n")
        sys.exit(130)
