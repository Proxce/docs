#!/usr/bin/env python3
"""
build_nav.py - turn navigation.json into the docs.json navigation.

navigation.json is the source of truth: it holds the tab / menu / group tree,
the display labels, the icons, the ordering, and the Intercom collections each
group is fed from. This script reads it, fills every group with the pages
actually present on disk, and writes the result into docs.json.

Edit navigation.json, never docs.json.

    python build_nav.py              # rewrite the docs.json navigation
    python build_nav.py --dry-run    # print the tree, write nothing
    python build_nav.py --empty      # only the groups still waiting on content

Two functions here are also imported by intercom_to_mintlify.py --migrate,
which uses them to decide where a fetched article is written:

    iter_groups(nav)  every group, with its directory and breadcrumbs
    norm(text)        normalise a 'Product :: Collection' key for matching
"""

import argparse
import html
import json
import os
import re
import sys
import unicodedata

NAV_FILE = "navigation.json"
DOCS_FILE = "docs.json"

# Directories that never hold documentation pages.
SKIP_DIRS = {".git", "node_modules", "__pycache__", "images", "logo",
             "output", "auth", ".claude", ".github",
             "intercom_export", "intercom_workspaces"}

# The tab carrying this key is the Drafts tab: it mirrors every visible tab.
MIRROR_KEY = "mirror_drafts"


# ---------------------------------------------------------------------------
#  Reading navigation.json
# ---------------------------------------------------------------------------

def norm(text):
    """Normalise a "Product :: Collection" key so the two sides match.

    Intercom's own data is not tidy - "Windows Login (Healthcare )" carries a
    stray space inside the bracket, and collections drift in capitalisation -
    so case, non-breaking spaces, repeated spaces and space-before-punctuation
    are all flattened before comparing. Both the navigation file and the live
    API values go through this, so it only has to be consistent, not pretty.

    Entities are decoded first: the Intercom API returns collection names
    HTML-escaped ("Chrome Vault - Accounts &amp; Settings") while
    navigation.json spells them with a literal "&", and without this 68
    articles across 8 collections find no home.
    """
    text = html.unescape(text or "")
    text = unicodedata.normalize("NFKC", text).replace(chr(0x00a0), " ")
    parts = []
    for part in text.split("::"):
        part = re.sub(r"\s+", " ", part).strip().lower()
        part = re.sub(r"\s+([)\],.])", r"\1", part)   # "healthcare )" -> "healthcare)"
        part = re.sub(r"([(\[])\s+", r"\1", part)
        parts.append(part)
    return " :: ".join(parts)


def iter_groups(nav):
    """Yield (group, slug_parts, crumbs) for every group in navigation.json.

    The file nests tab -> [menu ->] group, and either level may carry a slug.
    `slug_parts` are the directory segments with empty slugs dropped, so the
    hidden Home tab (slug "") resolves to the repository root rather than a
    directory literally called "". `crumbs` are the display labels, for
    readable log lines.
    """
    def slugs(node, acc):
        value = node.get("slug")
        return acc + [value] if value else acc

    for tab in nav.get("tabs") or []:
        tab_slugs = slugs(tab, [])
        tab_crumbs = [tab.get("tab")]

        for grp in tab.get("groups") or []:
            yield grp, slugs(grp, tab_slugs), tab_crumbs + [grp.get("group")]

        for item in tab.get("menu") or []:
            item_slugs = slugs(item, tab_slugs)
            item_crumbs = tab_crumbs + [item.get("item")]
            for grp in item.get("groups") or []:
                yield grp, slugs(grp, item_slugs), item_crumbs + [grp.get("group")]


def drafts_tab(nav):
    for tab in nav.get("tabs") or []:
        if tab.get(MIRROR_KEY):
            return tab
    return None


def mirrored_tabs(nav):
    """The tabs whose drafts the Drafts tab shows: every visible tab but itself.

    Hidden tabs (Home, Excluded) are left out on purpose - their drafts stay
    in their own directories, as hidden as the rest of them.
    """
    return [t for t in nav.get("tabs") or []
            if not t.get("hidden") and not t.get(MIRROR_KEY)]


def draft_directory(nav, directory):
    """Where a draft whose published home is `directory` is written instead.

    "windows/version-1/guides" -> "drafts/windows/version-1/guides". Groups
    outside the mirrored tabs are returned unchanged: Excluded keeps its
    drafts, and the Drafts tab's own menus are already under drafts/.
    """
    tab = drafts_tab(nav)
    directory = directory.replace("\\", "/")
    if not tab or not tab.get("slug"):
        return directory
    head = directory.split("/")[0]
    if head in {t.get("slug") for t in mirrored_tabs(nav) if t.get("slug")}:
        return "%s/%s" % (tab["slug"], directory)
    return directory


VIDEOS_SLUG = "videos"


def video_directory(nav, directory):
    """Where a video-only article whose home is `directory` is written instead.

    The Videos group of the same menu - "windows/version-1/supervisor-app" ->
    "windows/version-1/videos" - when that menu has one. Unchanged when it
    has none, when the article is already in it, or when its group sets
    `keep_videos` (Healthcare, which Resources > Industries lists as a set).
    """
    directory = directory.replace("\\", "/")
    groups = {"/".join(parts): grp for grp, parts, _c in iter_groups(nav)}
    if (groups.get(directory) or {}).get("keep_videos"):
        return directory
    parent = directory.rsplit("/", 1)[0] if "/" in directory else ""
    target = "/".join(p for p in (parent, VIDEOS_SLUG) if p)
    return target if target in groups else directory


def load_nav(root=".", filename=NAV_FILE):
    with open(os.path.join(root, filename), encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
#  Filling groups from disk
# ---------------------------------------------------------------------------

def group_dir(grp, slug_parts, prefix=""):
    """The directory a group's pages live in, as a docs-relative path.

    `pages_from` points at another group's directory: Healthcare is written
    once under Windows > Version 1 and listed a second time under
    Resources > Industries, so the second group borrows the first's files.
    `prefix` is the Drafts tab's slug when listing a group's drafts, so a
    borrowed directory is borrowed from the drafts side too.
    """
    if grp.get("pages_from"):
        directory = grp["pages_from"].replace("\\", "/").strip("/")
    else:
        directory = "/".join(slug_parts)
    return "/".join(p for p in (prefix, directory) if p)


def pages_for(grp, slug_parts, root, prefix=""):
    """Page paths for one group, in sidebar order.

    An explicit `pages` list wins - that is how the Home tab pins index and
    quickstart. Otherwise the group's own directory is listed, one level only:
    a nested directory belongs to a different group and would otherwise be
    claimed twice.
    """
    if grp.get("pages") is not None and not prefix:
        return list(grp["pages"])

    directory = group_dir(grp, slug_parts, prefix)
    absolute = os.path.join(root, directory) if directory else root
    if not os.path.isdir(absolute):
        return []

    pages = []
    for name in sorted(os.listdir(absolute)):
        if not name.endswith(".mdx"):
            continue
        stem = name[:-4]
        pages.append("%s/%s" % (directory, stem) if directory else stem)
    return pages


def build_tabs(nav, root, report):
    """navigation.json -> the docs.json `tabs` array.

    A group with no pages yet is left out rather than emitted empty, because
    Mintlify fails the build on a group with nothing in it; the group returns
    by itself once its collection is migrated. Hidden tabs are dropped too:
    docs.json has no tab-level `hidden`, and their pages still route.
    """
    def collect_groups(node, slug_parts, crumbs, prefix=""):
        out = []
        for grp in node.get("groups") or []:
            parts = slug_parts + ([grp["slug"]] if grp.get("slug") else [])
            pages = pages_for(grp, parts, root, prefix)
            trail = crumbs + [grp.get("group")]
            if not pages:
                if not prefix:          # a group with no drafts is the norm
                    report["empty"].append(" > ".join(str(c) for c in trail))
                continue
            entry = {"group": grp.get("group"), "pages": pages}
            if grp.get("icon"):
                entry["icon"] = grp["icon"]
            out.append(entry)
            report["pages"] += len(pages)
        return out

    def mirror_menus(drafts):
        """One menu per visible tab, holding that tab's drafts.

        docs.json has one level fewer than tab > menu > group needs here, so
        the mirrored tab's menus become groups and its groups nest inside
        them - Mintlify renders a group inside a group's `pages`.
        """
        prefix = drafts["slug"]
        menus = []
        for src in mirrored_tabs(nav):
            src_slugs = [src["slug"]] if src.get("slug") else []
            crumbs = [drafts.get("tab"), src.get("tab")]
            if src.get("menu"):
                groups = []
                for item in src["menu"]:
                    item_slugs = src_slugs + ([item["slug"]] if item.get("slug") else [])
                    nested = collect_groups(item, item_slugs,
                                            crumbs + [item.get("item")], prefix)
                    if not nested:
                        continue
                    entry = {"group": item.get("item"), "pages": nested}
                    if item.get("icon"):
                        entry["icon"] = item["icon"]
                    groups.append(entry)
            else:
                groups = collect_groups(src, src_slugs, crumbs, prefix)
            if not groups:
                continue
            entry = {"item": src.get("tab"), "groups": groups}
            if src.get("icon"):
                entry["icon"] = src["icon"]
            menus.append(entry)
        return menus

    tabs = []
    for tab in nav.get("tabs") or []:
        name = tab.get("tab")
        if tab.get("hidden"):
            # Not emitted - docs.json has no tab-level `hidden` - but its
            # pages still route, so they are recorded and must not then be
            # reported as unclaimed.
            report["hidden"].append(name)
            for grp, parts, _crumbs in iter_groups({"tabs": [tab]}):
                report["hidden_pages"].extend(pages_for(grp, parts, root))
            continue
        tab_slugs = [tab["slug"]] if tab.get("slug") else []

        if tab.get("menu") or tab.get(MIRROR_KEY):
            menus = mirror_menus(tab) if tab.get(MIRROR_KEY) else []
            for item in tab.get("menu") or []:
                item_slugs = tab_slugs + ([item["slug"]] if item.get("slug") else [])
                groups = collect_groups(item, item_slugs, [name, item.get("item")])
                if not groups:
                    continue
                entry = {"item": item.get("item"), "groups": groups}
                if item.get("icon"):
                    entry["icon"] = item["icon"]
                menus.append(entry)
            if not menus:
                report["skipped_tabs"].append(name)
                continue
            built = {"tab": name, "menu": menus}
        else:
            groups = collect_groups(tab, tab_slugs, [name])
            if not groups:
                report["skipped_tabs"].append(name)
                continue
            built = {"tab": name, "groups": groups}

        if tab.get("icon"):
            built["icon"] = tab["icon"]
        tabs.append(built)
    return tabs


def flat_pages(pages):
    """Page paths in a docs.json `pages` list, descending into nested groups."""
    out = []
    for page in pages:
        if isinstance(page, dict):
            out.extend(flat_pages(page.get("pages") or []))
        else:
            out.append(page)
    return out


def orphans(root, listed):
    """Pages on disk that no group claims - they would be unreachable."""
    found = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if name.endswith(".mdx"):
                rel = os.path.relpath(os.path.join(dirpath, name), root)
                found.add(rel.replace(os.sep, "/")[:-4])
    return sorted(found - set(listed))


def expected_counts(root, nav):
    """{group id: how many Intercom articles are destined for it}

    Read from the article inventory exported by oloid.py, so a section can be
    shown as "3 of 49 migrated" rather than just "3". Returns an empty mapping
    when the export is absent - the count is a convenience, not a dependency.
    """
    path = os.path.join(root, "output", "_all_articles.csv")
    if not os.path.isfile(path):
        return {}, 0
    import csv, io
    per_collection = {}
    total = 0
    with io.open(path, encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            key = norm("%s :: %s" % (row.get("product"), row.get("collection")))
            per_collection[key] = per_collection.get(key, 0) + 1
            total += 1
    counts = {}
    for grp, parts, crumbs in iter_groups(nav):
        n = sum(per_collection.get(norm(c), 0) for c in grp.get("collections") or [])
        counts[id(grp)] = n
    return counts, total


def print_tree(nav, root):
    """Every section and subsection, with pages on disk and articles expected."""
    counts, total = expected_counts(root, nav)
    grand_on_disk = grand_expected = 0

    for tab in nav.get("tabs") or []:
        name = tab.get("tab")
        rows = []
        tab_slugs = [tab["slug"]] if tab.get("slug") else []

        def rows_for(node, slug_parts, depth):
            got = exp = 0
            for grp in node.get("groups") or []:
                parts = slug_parts + ([grp["slug"]] if grp.get("slug") else [])
                pages = len(pages_for(grp, parts, root))
                want = counts.get(id(grp), 0)
                rows.append((depth, grp.get("group"), pages, want,
                             len(grp.get("collections") or [])))
                got += pages
                exp += want
            return got, exp

        tab_got, tab_exp = rows_for(tab, tab_slugs, 1)
        for item in tab.get("menu") or []:
            item_slugs = tab_slugs + ([item["slug"]] if item.get("slug") else [])
            at = len(rows)
            got, exp = rows_for(item, item_slugs, 2)
            rows.insert(at, (1, item.get("item"), got, exp, None))
            tab_got += got
            tab_exp += exp

        flag = "  (hidden)" if tab.get("hidden") else ""
        print("")
        print("%-40s %5d / %-5d%s" % (name, tab_got, tab_exp, flag))
        for depth, label_, got, want, ncoll in rows:
            pad = "   " * depth
            note = ""
            if ncoll == 0:
                note = "   no collections mapped"
            elif want and not got:
                note = "   not migrated yet"
            elif want and got < want:
                note = "   partial"
            print("%s%-*s %5d / %-5d%s"
                  % (pad, 37 - len(pad), (label_ or "")[:37 - len(pad)], got, want, note))
        grand_on_disk += tab_got
        grand_expected += tab_exp

    print("")
    print("=" * 62)
    print("%-40s %5d / %-5d" % ("TOTAL  (on disk / expected)", grand_on_disk, grand_expected))
    if total:
        # A collection listed in two groups is counted once per group, so the
        # expected column adds up to more than the export holds. Healthcare is
        # the intended case: reachable from Windows > Version 1 and again from
        # Resources > Industries, one set of files in two sidebars.
        distinct = set()
        for grp, _parts, _crumbs in iter_groups(nav):
            distinct.update(norm(c) for c in grp.get("collections") or [])
        counted = sum(1 for grp, _p, _c in iter_groups(nav)
                      for _ in (grp.get("collections") or []))
        print("%d article(s) in the Intercom export" % total)
        if counted > len(distinct):
            print("expected exceeds that because %d collection(s) are listed in "
                  "more than one group" % (counted - len(distinct)))


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--dry-run", action="store_true", help="print, write nothing")
    ap.add_argument("--empty", action="store_true",
                    help="list the groups still waiting on content")
    ap.add_argument("--tree", action="store_true",
                    help="every section and subsection, migrated vs expected")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    nav = load_nav(root)
    report = {"pages": 0, "empty": [], "hidden": [], "hidden_pages": [],
              "skipped_tabs": []}
    tabs = build_tabs(nav, root, report)

    if args.tree:
        print_tree(nav, root)
        return 0

    if args.empty:
        print("%d group(s) with no pages yet\n" % len(report["empty"]))
        for trail in report["empty"]:
            print("   %s" % trail)
        return 0

    listed = []
    for tab in tabs:
        for node in tab.get("menu") or [tab]:
            for grp in node.get("groups") or []:
                listed.extend(flat_pages(grp["pages"]))

    count = lambda g: len(flat_pages(g["pages"]))
    print("=" * 68)
    for tab in tabs:
        kids = tab.get("menu") or tab.get("groups") or []
        total = sum(count(g) for k in kids for g in (k.get("groups") or [k]))
        print("%-34s %4d" % (tab["tab"], total))
        for k in kids:
            groups = k.get("groups") or [k]
            if k.get("groups"):
                print("   %-31s %4d" % (k.get("item"), sum(count(g) for g in groups)))
            for g in groups:
                pad = "      " if k.get("groups") else "   "
                print("%s%-28s %4d" % (pad, g["group"], count(g)))
    print("=" * 68)
    print("%d pages in %d tab(s)" % (report["pages"], len(tabs)))
    if report["hidden"]:
        print("hidden tabs, not emitted : %s  (%d page(s), still routable)"
              % (", ".join(report["hidden"]), len(report["hidden_pages"])))
    if report["skipped_tabs"]:
        print("tabs with no content yet : %s" % ", ".join(report["skipped_tabs"]))
    print("groups awaiting content  : %d   (--empty to list)" % len(report["empty"]))

    stranded = orphans(root, listed + report["hidden_pages"])
    if stranded:
        print("\n%d page(s) on disk that no group claims:" % len(stranded))
        for page in stranded[:15]:
            print("   %s" % page)
        if len(stranded) > 15:
            print("   ... and %d more" % (len(stranded) - 15))

    if args.dry_run:
        return 0

    docs_path = os.path.join(root, DOCS_FILE)
    with open(docs_path, encoding="utf-8") as fh:
        docs = json.load(fh)
    docs["navigation"] = {"tabs": tabs}
    navbar = nav.get("navbar") or {}
    if navbar.get("links") is not None or navbar.get("primary"):
        keep = {k: v for k, v in navbar.items()
                if k in ("links", "primary") and v}
        if keep:
            docs["navbar"] = keep
    with open(docs_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(docs, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("\nwritten to %s" % docs_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
