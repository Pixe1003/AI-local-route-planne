import re
from functools import lru_cache
from pathlib import Path


PROMPTS_DIR = Path(__file__).resolve().parent
VERSION_PATTERN = re.compile(r"<!--\s*version:\s*(v[\d.]+)\s*-->")


@lru_cache
def load_prompt(name: str) -> tuple[str, str]:
    path = PROMPTS_DIR / f"{name}.system.md"
    content = path.read_text(encoding="utf-8")
    match = VERSION_PATTERN.search(content)
    version = match.group(1) if match else "unversioned"
    return content, version


def get_prompt_version(name: str) -> str:
    _, version = load_prompt(name)
    return version
