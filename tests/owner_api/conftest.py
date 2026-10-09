from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
for package_source in (
    ROOT / "packages" / "owner_api" / "src",
    ROOT / "packages" / "contracts" / "src",
):
    sys.path.insert(0, str(package_source))
