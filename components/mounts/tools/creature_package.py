"""Compatibility entry point for the suite-owned shared creature package."""
from pathlib import Path
import runpy
_SOURCE = Path(__file__).resolve().parents[3]/"tools/creature_package.py"
if __name__ == "__main__":
    runpy.run_path(str(_SOURCE), run_name="__main__")
else:
    globals().update({k:v for k,v in runpy.run_path(str(_SOURCE)).items() if not k.startswith("__")})
