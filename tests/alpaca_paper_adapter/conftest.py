from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
for package in ("contracts", "execution"):
    sys.path.insert(0, str(ROOT / "packages" / package / "src"))
