from __future__ import annotations

from protocol.chip_spi import ChipSpi
from core.measurement_hook import E5052BMeasurementHook, FlowOptions
from core.session import TestSession
from core.sweeper import apply_presets
from scripts.fullflow.common import (
    build_capture_options, build_case_policy,
    make_client_from_config,
    print_flow_config,
    print_record,
    print_presets,
    print_block,
)
from utils.e5052b_config import load_e5052b_config
from utils.value_spec import iter_value_spec
from core.formatter import format_output_paths

# =========================================================
# User config section
# =========================================================
CASE_NAME = 'template_fullflow_case'

CASE_POLICY = {
    'DEBUG': False,
    'CONTINUE_ON_ERROR': False,
    'SPI_RETRY_ON_FAIL': False,
    'SPI_RETRY_COUNT': 1,
    'SPI_RETRY_DELAY_S': 0.05,
    'STRICT_SPI_LINK_CHECK': False,
    'MAX_CONSECUTIVE_SPI_FAILS': 3,
    'CONTINUE_ON_DEVICE_LOSS': False,
    'RAISE_ON_SPI_VERIFY_FAIL': False,
}

# ----- Full-flow switches -----
ENABLE_MEASUREMENT = True
SAVE_SCREENSHOT = False
SAVE_CSV = True
SAVE_EXCEL = True
DELAY_BEFORE_MEASUREMENT_S = 0.0

# ----- Optional presets (apply before SPI scan) -----
ENABLE_PRESETS = True
PRESETS = [
    {'name': 'CFG_OSC2_GMP_NUM', 'value': 3},
    {'name': 'CFG_OSC2_IDAC_IBIAS', 'value': 5},
]

# ----- SPI scan setup -----
FIELD_NAME = 'CFG_OSC2_TEST_BUF_IBIAS'
VALUE_SPEC = {'values': [0, 3, 4, 7]}


def main():
    cfg = load_e5052b_config()
    policy = build_case_policy(CASE_POLICY)
    capture_options = build_capture_options(cfg, save_screenshot=SAVE_SCREENSHOT)
    flow = FlowOptions(
        enable_measurement=ENABLE_MEASUREMENT,
        save_screenshot=SAVE_SCREENSHOT,
        save_csv=SAVE_CSV and cfg.get('save_csv', True),
        save_excel=SAVE_EXCEL and cfg.get('save_excel', True),
        delay_before_measurement_s=DELAY_BEFORE_MEASUREMENT_S,
        output_dir=f'outputs/fullflow/{CASE_NAME}',
        case_name=CASE_NAME,
    )
    print_flow_config(CASE_NAME, flow)

    with ChipSpi() as chip, make_client_from_config(cfg) as inst:
        preset_values = {}
        if ENABLE_PRESETS and PRESETS:
            preset_results = apply_presets(chip, PRESETS)
            print_presets(preset_results)
            preset_values = {item['name']: item['value'] for item in PRESETS}

        hook = E5052BMeasurementHook(inst, capture_options, flow) if ENABLE_MEASUREMENT else None
        session = TestSession(chip, hook, runtime_policy=policy)

        for value in iter_value_spec(VALUE_SPEC):
            record = session.run_field_write_read(
                FIELD_NAME,
                value,
                case_name=CASE_NAME,
                preset_values=preset_values,
                active_values={FIELD_NAME: value},
            )
            print_record(record)

        if hook is not None:
            merged = hook.export_merged_summary(f'merged_summary_{CASE_NAME}.xlsx')
            print_block(format_output_paths({'merged_summary_path': merged, 'run_dir': str(hook.run_dir)}))


if __name__ == '__main__':
    main()
