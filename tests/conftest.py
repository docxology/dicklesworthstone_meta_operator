"""Shared pytest setup for the meta-operator test suite.

Puts the project root and ``src/`` on ``sys.path`` so tests import project
modules as ``from src.models import RepoMeta`` regardless of the pytest
invocation directory (canonical: template monorepo root).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _p in (PROJECT_ROOT, PROJECT_ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
