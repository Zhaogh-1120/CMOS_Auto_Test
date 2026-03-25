from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Mapping

CFG_PATH = Path('config/common/field_alias.json')


@lru_cache(maxsize=1)
def load_field_alias_map() -> dict[str, str]:
    if not CFG_PATH.exists():
        return {}
    return json.loads(CFG_PATH.read_text(encoding='utf-8'))


def alias_for(field_name: str) -> str:
    return load_field_alias_map().get(field_name, field_name)


def aliases_for(fields: list[str] | tuple[str, ...]) -> list[str]:
    return [alias_for(name) for name in fields]
