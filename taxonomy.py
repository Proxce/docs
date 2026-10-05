#!/usr/bin/env python3
"""
taxonomy.py - map the Intercom export onto the target documentation structure.

The Intercom content is organised by (product, collection). The docs are
organised as tab -> menu -> group. This file holds the rules that translate
one into the other, so an import knows where an article belongs without
anyone placing it by hand.

Run it to see coverage:

    python taxonomy.py                 # summary per tab/menu
    python taxonomy.py --unmapped      # only what no rule claims
    python taxonomy.py --menu "Webkey" # the articles behind one menu

Rules are tried in order and the first match wins, so put the specific ones
first - "Windows Login v2.0" has to be tested before the general
"Windows Login" rule or version 2 disappears into the general guides.
"""

import argparse
import collections
import csv
import io
import re
import sys

CSV_PATH = "output/_all_articles.csv"

# (tab, menu, product_pattern, collection_pattern)
#   - a pattern of None matches anything
#   - matching is case-insensitive, on a regex search
RULES = [
    # ---- 1. Windows -----------------------------------------------------
    ("Windows", "Version 2",     None, r"windows login v2"),
    ("Windows", "Version 1",     r"supervisor app", None),
    ("Windows", "Version 1",     r"windows login \(healthcare", None),
    ("Windows", "Version 1",     None, r"presence detection"),
    ("Windows", "Getting started", None, r"getting started.*windows|windows.*getting started"),
    ("Windows", "General guides", None, r"windows login"),

    # ---- 2. Device ------------------------------------------------------
    ("Device", "Android (Devicelock)", None, r"device ?lock"),
    ("Device", "iOS (Connect, Verify)", r"oloid verify/connect", None),

    # ---- 5. Webkey ------------------------------------------------------
    #  Checked before the platform rules: WebKey collections live inside the
    #  Passwordless Authenticator product and would otherwise be swallowed.
    ("Webkey", "Webkey", None, r"webkey"),

    # ---- 4. Oloid Vault -------------------------------------------------
    ("Oloid Vault", "Chrome Vault", r"oloid chrome vault", None),
    ("Oloid Vault", "Chrome Vault", None, r"chrome vault"),
    ("Oloid Vault", "iOS Vault",    None, r"ios vault|iphone vault"),

    # ---- 6. Workflow ----------------------------------------------------
    ("Workflow", "Oloid Workflow", r"oloid workflow", None),

    # ---- 3. Administration ----------------------------------------------
    ("Administration", "Admin Portal",   None, r"admin portal"),
    ("Administration", "User Portal",    r"oloid user portal", None),
    ("Administration", "Supervisor Portal", r"supervisor portal", None),
    ("Administration", "Platform (Enterprise Features)",
     r"oloid platform - enterprise features", None),
    ("Administration", "Platform (Enterprise Features)",
     r"oloid platform starter", None),

    # ---- 7. Resources ---------------------------------------------------
    ("Resources", "Changelog",           r"release notes", None),
    ("Resources", "Troubleshooting",     r"troubleshooting", None),
    ("Resources", "Supporting Documents", r"supporting documents", None),
    ("Resources", "QRG",                 r"quick reference guides", None),
    ("Resources", "Guides",              r"what is oloid|the oloid glossary", None),
    ("Resources", "Integrations",        None, r"integration"),
    ("Resources", "Industries",          None, r"healthcare|retail|manufacturing"),
    ("Resources", "Unassigned",          r"_unassigned", None),

    # ---- catch-alls for products with no home above ----------------------
    ("Device", "Android (Devicelock)", r"m-tag", None),
    ("Oloid Vault", "iOS Vault",       r"oloid cloudkey", None),
    ("Device", "iOS (Connect, Verify)", r"oloid app", None),

    # Connect-for-Passwordless sits in the Passwordless product but is Connect
    # content, so it belongs with the rest of Connect on the Device tab.
    ("Device", "iOS (Connect, Verify)", None, r"connect for passwordless|oloid connect"),

    # Everything still left in Passwordless Authenticator is cross-cutting
    # Windows Login material - platform config, credentials, reporting, SSO -
    # that names no version or device. It lands in the general guides rather
    # than being dropped. Keep this rule LAST: it is deliberately greedy.
    ("Windows", "General guides", r"passwordless authenticator", None),
]

TAB_ORDER = ["Windows", "Device", "Administration", "Oloid Vault",
             "Webkey", "Workflow", "Resources"]

MENU_ORDER = {
    "Windows": ["Getting started", "Version 1", "Version 2", "General guides"],
    "Device": ["Android (Devicelock)", "iOS (Connect, Verify)"],
    "Administration": ["Admin Portal", "User Portal", "Supervisor Portal",
                       "Platform (Enterprise Features)"],
    "Oloid Vault": ["Chrome Vault", "iOS Vault"],
    "Webkey": ["Webkey"],
    "Workflow": ["Oloid Workflow"],
    "Resources": ["Guides", "Integrations", "Industries", "Changelog",
                  "Troubleshooting", "Supporting Documents", "QRG", "Unassigned"],
}


def classify(product, collection):
    """Return (tab, menu) for an article, or (None, None) if no rule claims it."""
    product = product or ""
    collection = collection or ""
    for tab, menu, p_pat, c_pat in RULES:
        if p_pat and not re.search(p_pat, product, re.I):
            continue
        if c_pat and not re.search(c_pat, collection, re.I):
            continue
        return tab, menu
    return None, None


def group_for(collection):
    """The third level: Intercom already separates guides from videos."""
    c = (collection or "").lower()
    if "video" in c:
        return "Videos"
    if "admin" in c:
        return "Admin Guides"
    if "user guide" in c:
        return "User Guides"
    if "faq" in c:
        return "FAQs"
    if "getting started" in c:
        return "Getting Started"
    if "installation" in c or "configuration" in c or "settings" in c:
        return "Setup"
    return "Guides"


def load(path=CSV_PATH):
    with io.open(path, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default=CSV_PATH)
    ap.add_argument("--unmapped", action="store_true", help="list what no rule claims")
    ap.add_argument("--menu", help="list the articles behind one menu")
    ap.add_argument("--published-only", action="store_true",
                    help="ignore Intercom drafts")
    args = ap.parse_args()

    rows = load(args.csv)
    if args.published_only:
        rows = [r for r in rows if r.get("state") == "published"]

    counts = collections.defaultdict(collections.Counter)
    unmapped = collections.Counter()
    per_menu = collections.defaultdict(list)

    for r in rows:
        tab, menu = classify(r.get("product"), r.get("collection"))
        if tab is None:
            unmapped[(r.get("product"), r.get("collection"))] += 1
            continue
        counts[tab][menu] += 1
        per_menu[menu].append(r)

    if args.menu:
        picked = per_menu.get(args.menu, [])
        print("%s - %d article(s)\n" % (args.menu, len(picked)))
        for r in picked[:60]:
            print("  %-9s %-22s %s" % (r["article_id"], group_for(r["collection"]),
                                       r["title"][:64]))
        return 0

    if args.unmapped:
        total = sum(unmapped.values())
        print("unmapped: %d article(s) across %d (product, collection) pairs\n"
              % (total, len(unmapped)))
        for (p, c), n in unmapped.most_common(40):
            print("  %4d  %-40s %s" % (n, (p or "-")[:40], (c or "-")[:60]))
        return 0

    mapped = sum(sum(m.values()) for m in counts.values())
    print("=" * 66)
    print("Target structure - %d of %d articles mapped" % (mapped, len(rows)))
    print("=" * 66)
    for i, tab in enumerate(TAB_ORDER, 1):
        menus = counts.get(tab, {})
        print("\n%d. %-28s %4d" % (i, tab, sum(menus.values())))
        for menu in MENU_ORDER.get(tab, []):
            n = menus.get(menu, 0)
            flag = "" if n else "   <- nothing maps here yet"
            print("     %-34s %4d%s" % (menu, n, flag))
        for menu, n in menus.items():
            if menu not in MENU_ORDER.get(tab, []):
                print("     %-34s %4d   <- not in the requested order" % (menu, n))
    left = sum(unmapped.values())
    print("\nunmapped: %d  (run --unmapped to see them)" % left)
    return 0


if __name__ == "__main__":
    sys.exit(main())
