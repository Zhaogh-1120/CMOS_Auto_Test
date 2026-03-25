from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def load_e5052b_config() -> Dict[str, Any]:
    cfg_path = Path("config/instrument/e5052b_config.json")
    if not cfg_path.exists():
        raise FileNotFoundError(f"E5052B config not found: {cfg_path}")
    return json.loads(cfg_path.read_text(encoding="utf-8"))