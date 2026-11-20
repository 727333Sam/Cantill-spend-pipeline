import json
from pathlib import Path
from typing import Any


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    if "company" not in config or "taxonomy" not in config:
        raise ValueError(f"Invalid config: {config_path}")
    return config
