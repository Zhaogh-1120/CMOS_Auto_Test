from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

DEFAULT_PATH = Path("config/common/runtime_policy.json")


def load_runtime_policy_defaults(path: str | Path | None = None) -> dict[str, Any]:
    cfg_path = Path(path) if path is not None else DEFAULT_PATH
    if not cfg_path.exists():
        return {}
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def build_runtime_policy(case_overrides: Mapping[str, Any] | None = None, path: str | Path | None = None) -> dict[str, Any]:
    policy = load_runtime_policy_defaults(path)
    if case_overrides:
        for k, v in case_overrides.items():
            if v is not None:
                policy[k] = v
    return policy
