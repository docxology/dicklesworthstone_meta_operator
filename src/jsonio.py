"""JSON/text artifact I/O with atomic writes.

Shared serialization seam for every ``output/`` artifact writer: reads are
strict by default (a missing required artifact is an error, never a silent
empty object) and writes are atomic (temp file + ``os.replace``) so a crash
mid-write can never leave a truncated artifact behind.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def read_json(path: Path, *, required: bool = True) -> Any:
    """Read and parse a JSON file.

    Args:
        path: File to read.
        required: When True (default), a missing file raises
            ``FileNotFoundError``; when False, returns ``None``.

    Raises:
        FileNotFoundError: If ``required`` and the file does not exist.
        json.JSONDecodeError: If the file is not valid JSON (never masked).
    """
    if not path.exists():
        if required:
            raise FileNotFoundError(f"required JSON artifact missing: {path}")
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write(path: Path, payload: str) -> Path:
    """Write ``payload`` to ``path`` atomically (temp file + os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=path.name + ".", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():  # replace failed before consuming the temp file
            tmp_path.unlink()
    return path


def write_json(path: Path, payload: Any) -> Path:
    """Atomically write ``payload`` as JSON: indent 2, trailing newline."""
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    return _atomic_write(path, text)


def write_text(path: Path, text: str) -> Path:
    """Atomically write UTF-8 text."""
    return _atomic_write(path, text)


def sha8(text: str) -> str:
    """First 8 hex chars of the SHA-256 of ``text`` (UTF-8)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
