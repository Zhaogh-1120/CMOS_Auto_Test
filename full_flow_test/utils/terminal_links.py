"""Clickable local file/folder links for VS Code's integrated terminal.

Only terminal output uses OSC 8. The on-disk run_log.txt receives clean,
absolute, human-readable paths (never terminal escape codes).

No file creation, hardware access, browser use, or automatic opening occurs.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def _clean_display(value: str) -> str:
    """Do not allow filenames to inject control sequences into the terminal."""
    return "".join(c if c.isprintable() else "?" for c in value)


def _supports_osc8(stream: Any) -> bool:
    try:
        return bool(stream.isatty())
    except (AttributeError, OSError):
        return False


def emit_path_link(
    label: str,
    filepath: str | Path,
    *,
    log_handle: Any = None,
    show_full_path: bool = False,
    stream: Any = None,
) -> None:
    """Print a clickable file:// hyperlink and a plain absolute path to the log.

    In a VS Code terminal the visible name/path can be Ctrl+clicked. Piped
    output gracefully degrades to a plain absolute path. A hyperlink never
    opens a file on its own, and this function does not check/change its bytes.
    """
    if stream is None:
        stream = sys.stdout
    absolute = Path(filepath).expanduser().resolve()
    full_name = _clean_display(str(absolute))
    visible = full_name if show_full_path else _clean_display(absolute.name)
    prefix = f"{label:<14}: "
    if _supports_osc8(stream):
        # Path.as_uri() percent-encodes non-ASCII and spaces in Windows paths.
        uri = absolute.as_uri()
        output = f"{prefix}\x1b]8;;{uri}\x1b\\{visible}\x1b]8;;\x1b\\"
    else:
        output = prefix + full_name
    print(output, file=stream, flush=True)
    if log_handle is not None:
        log_handle.write(prefix + full_name + "\n")
        log_handle.flush()


def emit_run_file_links(run_dir: str | Path, *, log_handle: Any = None) -> None:
    """Show links to all existing per-run summary artifacts after a scan."""
    directory = Path(run_dir)
    emit_path_link("Output Folder", directory, log_handle=log_handle, show_full_path=True)
    for label, relative in (
        ("Summary Excel", "summary_ibias_swcap_indcap.xlsx"),
        ("PN Comparison", "pn_comparison.xlsx"),
        ("Summary CSV", "summary_ibias_swcap_indcap.csv"),
        ("Run Log", "run_log.txt"),
        ("PN Traces CSV", "all_traces_long.csv"),
    ):
        candidate = directory / relative
        if candidate.is_file():
            emit_path_link(label, candidate, log_handle=log_handle)
    for label, dirname in (
        ("Screenshots", "screenshots"),
        ("Point Excels", "summary"),
        ("Raw PN CSVs", "traces"),
    ):
        candidate = directory / dirname
        if candidate.is_dir():
            emit_path_link(label, candidate, log_handle=log_handle)
