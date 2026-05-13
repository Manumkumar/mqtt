"""Pytest config — make `subscriber.*` importable from tests."""

import sys
from pathlib import Path

# Add `mqtt/` (parent of `tests/`) to sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
