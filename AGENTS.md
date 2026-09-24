> **First-time setup**: Customize this file for your project. Prompt the user to customize this file for their project.
> For Mintlify product knowledge (components, configuration, writing standards),
> install the Mintlify skill: `npx skills add https://mintlify.com/docs`

# Documentation project instructions

## About this project

- This is a documentation site built on [Mintlify](https://mintlify.com)
- Pages are MDX files with YAML frontmatter
- Configuration lives in `docs.json`
- Use the Mintlify MCP server, `https://mcp.mintlify.com`, to edit content and settings via MCP
- Use the Mintlify docs MCP server, `https://www.mintlify.com/docs/mcp`, to query information about using Mintlify via MCP

## Terminology

{/* Add product-specific terms and preferred usage */}
{/* Example: Use "workspace" not "project", "member" not "user" */}

## Migration

`python intercom_to_mintlify.py --migrate` is the full run. It reads
`navigation.json`, fetches every article, and writes each page into the
directory of the group whose `collections` list claims it. `docs.json` is not
written here - `build_nav.py` runs at the end and rebuilds it from disk.

Only GET endpoints are used, and no write endpoint is ever called:

```
GET /help_center/collections   the Product / Section tree used for grouping
GET /articles                  every article summary, 150 per page
GET /articles/{id}             the full body
```

Per-article JSON is cached under `intercom_export/articles/` and reused when
`updated_at` matches, so a re-run only fetches what changed. Useful flags:
`--limit N` (smoke test), `--dry-run`, `--refresh`, `--no-nav`.

Rules the run applies:

- **Page shape mirrors oloid.help.** Headings keep their own text and their own
  relative depth; nothing is renamed to a template section and nothing is
  promoted. The one exception is the no-H1 rule below.
- **Articles with an empty body are skipped** and listed in the report, rather
  than written as blank pages.
- **A group's `overview.mdx` placeholder is deleted** once real articles land in
  it. Groups still empty keep theirs so the navigation renders.
- **Unmapped collections are reported, never guessed.** If Intercom grows a
  collection that no group claims, its articles are not written - add it to
  `navigation.json` and re-run.

## Document template

The template below is the *older* enforced shape, still applied by
`python intercom_to_mintlify.py --reformat` (no Intercom token needed). The
`--migrate` run above does not use it: it mirrors oloid.help instead.

```
---
title:        full article title        <- the page's ONLY H1
sidebarTitle: short form for the nav
description:  one sentence
icon:         file-lines
keywords:     [...]                     <- feeds search, renders nothing
---

## Introduction            required
## Prerequisites           required, bullet list
## Steps to <do the task>  required, numbered procedure
###   sub-procedure
####    sub-sub-procedure
## Additional Information  optional
## Related Articles        optional
```

Rules the script applies, and that hand-edits must keep:

- **Never write an H1 in the body.** The frontmatter `title` is the page's only
  H1. An `# Heading` renders as a second 32px title, which is what made pages
  look oversized. Body sections start at `##`.
- **Indent list continuations to the content column**, not a flat two spaces:
  3 spaces under `1. `, 2 under `- `, 4 under `10. `. A step's screenshot, its
  note and its sub-steps all share that column. This is the alignment rule.
- **Notes are callouts.** `**Note:**` becomes `<Note>`; Important/Caution/
  Warning become `<Warning>`; Tip becomes `<Tip>`. Indent the callout to the
  column of the step it belongs to.
- **Screenshots are plain markdown** (`![alt](/images/...)`), not `<Frame>`.
  Frame is a block component and cannot sit inside a step. `style.css` gives
  images the rounded border instead. `<Frame>` is still used for videos.
- **Keywords live in frontmatter only.** Intercom's trailing one-row pipe table
  renders as a malformed box; the script lifts it into `keywords:`.
- **No Intercom `#h_xxxx` anchors** - they 404 in Mintlify. The script rewrites
  them to real heading slugs, or drops the link if it cannot resolve one.
- Section headings are canonical: "Prerequisites" (not "Prerequisite"),
  "Related Articles", "Additional Information", trailing "Tab" capitalised.

Missing required sections are reported, never invented - add them by hand.

## Navigation

`docs.json` and `index.mdx` are **generated**. `navigation.json` is the source of
truth: the tab / menu / group tree, plus the Intercom collections
(`Product :: Collection`) whose articles belong in each group.

```
python build_nav.py --check     # report only: which collections nothing claims
python build_nav.py             # write docs.json, index.mdx and placeholders
```

- A group's pages are whatever `.mdx` files sit in its directory, so migrated
  content wires itself into the nav with no config. A group with no pages yet
  gets an `overview.mdx` placeholder listing its source collections and counts.
- `index.mdx` is a generated card index of every tab, with article counts. The
  `Home` tab is `hidden: true`: it keeps `/` routing to `index.mdx` without
  showing a tab. Edit the header text in `LANDING_HEADER` in `build_nav.py`.
- The navbar lives in `navigation.json` too. The Support link is parked in
  `navbar.hidden_links`; move it back into `links` to restore it.
- Hand edits to `docs.json` or `index.mdx` are lost on the next run. Edit
  `navigation.json`.


## Typography

Page *structure* follows oloid.help exactly (verified: all 16 headings match
1:1 in level and order, 31 images vs 31). The *size* is deliberately one notch
below it, because the help-centre scale reads large on a docs site that also
has a sidebar:

```
                oloid.help      here
    body          16px          15px
    h1 (title)    32px          27px
    h2 section    24px          19px
    h3            20px        16.5px
    h4            18px          15px
    line-height   1.53          1.60
```

`docs.json` cannot change any of this: `styling` carries only `eyebrows` and
`codeblocks`, and `fonts` only takes family/weight - there is no size or
density key. The topbar search/assistant width is one of them
(`--oloid-search-width`). All sizes are CSS variables at the top of the `STYLE_CSS`
constant in `intercom_to_mintlify.py`, so making it smaller again is one block
to edit. Do not edit `style.css` directly; the script overwrites it.

The `luma` theme is kept because it already has the narrowest content column
of the available themes (max-w-174, about 696px, against mint's 864px and
aspen's 1152px). Switching theme changes styling, not size.

`docs.json` also has every starter-kit link stripped - anchors, navbar links
and social accounts that still pointed at mintlify.com - and the per-page
contextual toolbar trimmed from 8 options to 4. The script only removes links
pointing at mintlify.com, so real Oloid URLs are left alone once added.

## Style preferences

{/* Add any project-specific style rules below */}

- Use active voice and second person ("you")
- Keep sentences concise — one idea per sentence
- Use sentence case for headings
- Bold for UI elements: Click **Settings**
- Code formatting for file names, commands, paths, and code references

## Content boundaries

{/* Define what should and shouldn't be documented */}
{/* Example: Don't document internal admin features */}
