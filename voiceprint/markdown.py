"""Split markdown into prose and everything else.

Used twice: to keep non-prose out of the training corpus (a code fence is not
your voice), and to leave it untouched when rewriting a document.
"""

from __future__ import annotations

import re

FENCE_RE = re.compile(r"^(\s{0,3})(`{3,}|~{3,})")
HR_RE = re.compile(r"^\s*([-*_])\1{2,}\s*$")
LINK_REF_RE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s")
FRONT_MATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)

PROSE = "prose"
KEEP = "keep"


def strip_front_matter(md: str) -> str:
    return FRONT_MATTER_RE.sub("", md, count=1)


def segment(md: str) -> list[tuple[str, str]]:
    """Split into ('prose'|'keep', text) blocks, preserving every character.

    Code fences, headings, tables, blockquotes, horizontal rules, HTML blocks and
    link-reference definitions are 'keep'. Everything else is prose.
    """
    lines = md.splitlines(keepends=True)
    out: list[tuple[str, str]] = []
    buf: list[str] = []
    kind = PROSE

    def flush() -> None:
        if buf:
            out.append((kind, "".join(buf)))
            buf.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()

        fence = FENCE_RE.match(line)
        if fence:
            flush()
            kind = KEEP
            closing = fence.group(2)[0] * len(fence.group(2))
            buf.append(line)
            i += 1
            while i < len(lines):
                buf.append(lines[i])
                if lines[i].lstrip().startswith(closing):
                    i += 1
                    break
                i += 1
            flush()
            kind = PROSE
            continue

        is_keep = (
            stripped.startswith("#")
            or stripped.startswith(">")
            or stripped.startswith("|")
            or stripped.startswith("<")
            or HR_RE.match(line) is not None
            or LINK_REF_RE.match(line) is not None
        )
        if is_keep:
            if kind != KEEP:
                flush()
                kind = KEEP
            buf.append(line)
            i += 1
            continue

        if kind != PROSE:
            flush()
            kind = PROSE
        buf.append(line)
        i += 1

    flush()
    return out


def prose_only(md: str) -> str:
    """The prose of a document, with structure dropped. Paragraph breaks survive."""
    blocks = [text for kind, text in segment(strip_front_matter(md)) if kind == PROSE]
    joined = "".join(blocks)
    return re.sub(r"\n{3,}", "\n\n", joined).strip()
