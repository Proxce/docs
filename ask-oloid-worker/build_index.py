"""Build the Ask Oloid search index from the published .mdx pages.

    python build_index.py          (run from ask-oloid-worker/, or via wrangler)

Walks the docs repo one level up, splits every published page into sections
(one chunk per ##/### heading, long sections split further) and writes
src/docs-index.json: the chunks plus a precomputed BM25 inverted index, so the
Worker does no tokenising at start-up.

Excluded: drafts/ and excluded/ (unpublished or hidden tabs), the generated
index.mdx, and this directory. The tokenizer below must stay identical to
tokenize() in src/index.ts - the stopword list is shipped in the index so the
two cannot drift on that part.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "src", "docs-index.json")

SKIP_DIRS = {"drafts", "excluded", "ask-oloid-worker", "node_modules", ".git",
             "intercom_export", "intercom_workspaces", "output", "images", "logo"}
SKIP_FILES = {"index.mdx"}

CHUNK_CHARS = 1500  # target size of one chunk sent to Claude

STOPWORDS = sorted("""
a an and are as at be but by can do does for from has have how i if in into is
it its me my of on or our so that the their then there these this to up was we
what when where which who will with you your yours
""".split())
_STOP = set(STOPWORDS)


def tokenize(text):
    out = []
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if len(w) < 2 or w in _STOP:
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


def parse_frontmatter(raw):
    meta = {}
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            for line in raw[3:end].splitlines():
                m = re.match(r'^(\w+):\s*"?(.*?)"?\s*$', line)
                if m:
                    meta[m.group(1)] = m.group(2)
            raw = raw[end + 4:]
    return meta, raw


def clean(body):
    body = re.sub(r"\{/\*.*?\*/\}", "", body, flags=re.S)          # MDX comments
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body)                # images
    body = re.sub(r"<Frame>.*?</Frame>", "", body, flags=re.S)      # video frames
    body = re.sub(r"</?(Note|Warning|Tip|Info|Check|Frame)[^>]*>", "", body)
    body = re.sub(r"<(iframe|img|video)[^>]*/?>", "", body)
    body = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", body)     # keep link targets
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def split_sections(body):
    """[(heading, text)] - one entry per ##/### heading, intro has heading ''."""
    sections, heading, buf = [], "", []
    for line in body.splitlines():
        m = re.match(r"^#{2,3}\s+(.*)$", line)
        if m:
            sections.append((heading, "\n".join(buf).strip()))
            heading, buf = m.group(1).strip(), []
        else:
            buf.append(line)
    sections.append((heading, "\n".join(buf).strip()))
    return [(h, t) for h, t in sections if t]


def split_long(text):
    if len(text) <= CHUNK_CHARS:
        return [text]
    parts, cur = [], ""
    for para in text.split("\n\n"):
        if cur and len(cur) + len(para) > CHUNK_CHARS:
            parts.append(cur)
            cur = para
        else:
            cur = (cur + "\n\n" + para) if cur else para
    if cur:
        parts.append(cur)
    return parts


def iter_pages():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel_dir = os.path.relpath(dirpath, ROOT)
        if rel_dir == ".":
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in sorted(filenames):
            if not name.endswith(".mdx") or name.endswith(".draft.mdx"):
                continue
            if rel_dir == "." and name in SKIP_FILES:
                continue
            path = os.path.join(dirpath, name)
            url = "/" + os.path.relpath(path, ROOT)[:-4].replace(os.sep, "/")
            yield path, url


def main():
    chunks = []
    for path, url in iter_pages():
        with open(path, encoding="utf-8") as f:
            meta, body = parse_frontmatter(f.read())
        title = meta.get("title") or url.rsplit("/", 1)[-1]
        sections = split_sections(clean(body))
        if not sections and "<Frame>" in body:
            # video-only page: index it by title so it can still be found
            sections = [("", "Video tutorial. " + meta.get("description", ""))]
        for heading, text in sections:
            for part in split_long(text):
                chunks.append({"t": title, "h": heading, "u": url, "x": part})

    postings, lengths = {}, []
    for i, c in enumerate(chunks):
        # title and heading count twice: they say what the chunk is about
        tokens = tokenize(c["t"]) * 2 + tokenize(c["h"]) * 2 + tokenize(c["x"])
        lengths.append(len(tokens))
        tf = {}
        for tok in tokens:
            tf[tok] = tf.get(tok, 0) + 1
        for tok, n in tf.items():
            postings.setdefault(tok, []).extend((i, n))

    index = {
        "stop": STOPWORDS,
        "avgdl": sum(lengths) / max(len(lengths), 1),
        "len": lengths,
        "post": postings,   # term -> flat [chunkId, tf, chunkId, tf, ...]
        "chunks": chunks,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))

    pages = len({c["u"] for c in chunks})
    size = os.path.getsize(OUT) / 1e6
    print(f"docs-index.json: {pages} pages, {len(chunks)} chunks, "
          f"{len(postings)} terms, {size:.1f} MB")


if __name__ == "__main__":
    sys.exit(main())
