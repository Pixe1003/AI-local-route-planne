from pathlib import Path
import importlib.util
import sys


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
METRICS = BACKEND / "eval" / "metrics.py"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

spec = importlib.util.spec_from_file_location("_airoute_eval_metrics", METRICS)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = module
spec.loader.exec_module(module)

EvalResult = module.EvalResult
aggregate = module.aggregate
explanation_faithfulness = module.explanation_faithfulness
