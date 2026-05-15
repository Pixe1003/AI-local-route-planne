from pathlib import Path


_ROOT_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
__path__ = [str(_ROOT_SCRIPTS)]
