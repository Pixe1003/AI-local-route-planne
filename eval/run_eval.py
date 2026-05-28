from pathlib import Path
import runpy
import sys


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

runpy.run_path(str(BACKEND / "eval" / "run_eval.py"), run_name="__main__")
