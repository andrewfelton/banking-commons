"""Markdown -> HTML rendering for email bodies.

Matches the extension set the projects already standardized on (`extra` for
tables/attr-lists/footnotes, `sane_lists` for predictable list nesting), so
existing digests render identically after switching to the shared sender.
"""
from __future__ import annotations

import markdown as _markdown

_EXTENSIONS = ["extra", "sane_lists"]


def markdown_to_html(content: str | None) -> str:
    """Render Markdown to an HTML fragment. Safe on None (returns "")."""
    if content is None:
        return ""
    return _markdown.markdown(content, extensions=_EXTENSIONS)
