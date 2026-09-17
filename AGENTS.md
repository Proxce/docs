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

## Document template

Every migrated help-centre page uses the same shape. `intercom_to_mintlify.py`
enforces it; `python intercom_to_mintlify.py --reformat` re-applies it to the
pages already on disk (no Intercom token needed) and is safe to re-run.

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
density key. All sizes are CSS variables at the top of the `STYLE_CSS`
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
