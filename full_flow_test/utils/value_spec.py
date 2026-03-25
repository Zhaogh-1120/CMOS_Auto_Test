from __future__ import annotations

from itertools import product
from typing import Any, Iterable

from utils.range_helper import inclusive_range


def iter_discrete_values(values: Iterable[int]) -> list[int]:
    return [int(v) for v in values]


def normalize_value_spec(spec: Any) -> dict:
    if isinstance(spec, dict):
        if 'values' in spec:
            return {'mode': 'discrete', 'values': iter_discrete_values(spec['values'])}
        if {'start', 'stop'} <= set(spec.keys()):
            step = int(spec.get('step', 1))
            return {'mode': 'range', 'start': int(spec['start']), 'stop': int(spec['stop']), 'step': step}
    if isinstance(spec, (list, tuple, set)):
        return {'mode': 'discrete', 'values': iter_discrete_values(spec)}
    raise ValueError(f'Unsupported value spec: {spec!r}')


def iter_value_spec(spec: Any) -> list[int]:
    normalized = normalize_value_spec(spec)
    if normalized['mode'] == 'discrete':
        return normalized['values']
    return inclusive_range(normalized['start'], normalized['stop'], normalized['step'])


def build_value_product(spec_map: dict[str, Any]) -> list[dict[str, int]]:
    keys = list(spec_map.keys())
    value_lists = [iter_value_spec(spec_map[k]) for k in keys]
    return [dict(zip(keys, combo)) for combo in product(*value_lists)]
