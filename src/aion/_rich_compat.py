"""Rich library compatibility shims.

The `rich` library is excluded from production dependencies as a non-essential
visual aid (see [tool.uv].override-dependencies in pyproject.toml). CLI modules
import these names from here so they work with or without rich installed.

When rich is present, names are re-exported as-is. When absent, plain-text
fallbacks degrade gracefully (markup like `[dim]...[/dim]` is stripped, tables
become pipe-delimited text, panels become divider-bracketed text, progress
bars become no-op print calls).
"""

import re

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.table import Table
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

    _MARKUP_RE = re.compile(r"\[/?[^\]]*\]")

    class Console:  # type: ignore[no-redef]
        def print(self, *args, **kwargs):
            for arg in args:
                if isinstance(arg, str):
                    print(_MARKUP_RE.sub("", arg))
                else:
                    print(arg)

    class Markdown:  # type: ignore[no-redef]
        def __init__(self, content: str, **kwargs):
            self.content = content

        def __str__(self) -> str:
            return self.content

    class Panel:  # type: ignore[no-redef]
        def __init__(self, content, title: str = "", **kwargs):
            self.content = _MARKUP_RE.sub("", str(content))
            self.title = title

        def __str__(self) -> str:
            sep = "=" * 40
            header = f"--- {self.title} ---\n" if self.title else ""
            return f"{sep}\n{header}{self.content}\n{sep}"

    class Table:  # type: ignore[no-redef]
        def __init__(self, title: str = "", **kwargs):
            self.title = title
            self._headers: list[str] = []
            self._rows: list[list[str]] = []

        def add_column(self, name: str, **kwargs):
            self._headers.append(name)

        def add_row(self, *cells):
            self._rows.append([_MARKUP_RE.sub("", str(c)) for c in cells])

        def __str__(self) -> str:
            lines = []
            if self.title:
                lines.append(self.title)
                lines.append("-" * len(self.title))
            if self._headers:
                lines.append(" | ".join(self._headers))
            for row in self._rows:
                lines.append(" | ".join(row))
            return "\n".join(lines)

    class _NoopProgressItem:  # type: ignore[no-redef]
        """No-op for Progress columns — they're decorative-only."""

        def __init__(self, *args, **kwargs):
            pass

    SpinnerColumn = _NoopProgressItem  # type: ignore[misc,assignment]
    TextColumn = _NoopProgressItem  # type: ignore[misc,assignment]

    class Progress:  # type: ignore[no-redef]
        """Plain-text progress fallback: prints task descriptions, no live bar."""

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def add_task(self, description: str, **kwargs) -> int:
            print(_MARKUP_RE.sub("", description))
            return 0

        def update(self, *args, **kwargs):
            pass


__all__ = [
    "Console",
    "HAS_RICH",
    "Markdown",
    "Panel",
    "Progress",
    "SpinnerColumn",
    "Table",
    "TextColumn",
]
