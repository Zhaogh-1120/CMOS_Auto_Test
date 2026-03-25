from __future__ import annotations

from itertools import product
from typing import Any

from protocol.chip_spi import ChipSpi
from utils.range_helper import inclusive_range
from utils.value_spec import iter_value_spec, build_value_product


def apply_presets(chip: ChipSpi, presets: list[dict[str, Any]], use_shadow: bool = False) -> list[dict]:
    results: list[dict] = []
    for item in presets:
        name = item['name']
        value = int(item['value'])
        results.append(chip.write_field_then_read(name, value, use_shadow=use_shadow))
    return results


def run_field_values(chip: ChipSpi, field_name: str, value_spec: Any, use_shadow: bool = False) -> list[dict]:
    return [chip.write_field_then_read(field_name, value, use_shadow=use_shadow) for value in iter_value_spec(value_spec)]


def run_multi_field_product(chip: ChipSpi, field_specs: dict[str, Any], use_shadow: bool = False) -> list[dict[str, dict]]:
    combos = build_value_product(field_specs)
    results: list[dict[str, dict]] = []
    for combo in combos:
        combo_results: dict[str, dict] = {}
        for field_name, value in combo.items():
            combo_results[field_name] = chip.write_field_then_read(field_name, value, use_shadow=use_shadow)
        results.append(combo_results)
    return results

__all__ = [
    'inclusive_range',
    'apply_presets',
    'run_field_values',
    'run_multi_field_product',
    'iter_value_spec',
    'build_value_product',
]
