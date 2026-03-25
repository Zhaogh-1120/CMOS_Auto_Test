from __future__ import annotations

import time

from protocol.chip_spi import ChipSpi
from core.measurement_hook import E5052BMeasurementHook, FlowOptions
from core.result_model import FullFlowRecord
from core.session import TestSession
from core.sweeper import apply_presets
from scripts.fullflow.common import build_capture_options, build_case_policy, make_client_from_config, print_flow_config, print_record, print_block, print_case_start, print_progress, print_case_summary, print_case_done, print_case_error, write_run_meta, print_presets, register_error_record, print_debug_info, print_instrument_debug
from utils.e5052b_config import load_e5052b_config
from utils.value_spec import build_value_product
from core.formatter import format_output_paths

# =========================================================
# User config section
# =========================================================
CASE_NAME = 'case_preset_then_nested_sweep_capture'
# DEBUG:
# False = standard terminal output only
# True  = print extra internal debug details for troubleshooting
DEBUG = False

# CONTINUE_ON_ERROR:
# False = stop the whole case immediately when one step fails
# True  = record the failure and continue remaining steps
CONTINUE_ON_ERROR = False

CASE_POLICY = {
    'DEBUG': DEBUG,
    'CONTINUE_ON_ERROR': CONTINUE_ON_ERROR,
    'SPI_RETRY_ON_FAIL': False,
    'SPI_RETRY_COUNT': 1,
    'SPI_RETRY_DELAY_S': 0.05,
    'STRICT_SPI_LINK_CHECK': False,
    'MAX_CONSECUTIVE_SPI_FAILS': 3,
    'CONTINUE_ON_DEVICE_LOSS': False,
    'RAISE_ON_SPI_VERIFY_FAIL': False,
}

CASE_DESC = 'apply presets then nested multi-field sweep with E5052B capture'

# ----- Full-flow switches -----
ENABLE_MEASUREMENT = True
SAVE_SCREENSHOT = False
SAVE_CSV = True
SAVE_EXCEL = True
DELAY_BEFORE_MEASUREMENT_S = 0.0

# ----- Optional presets (apply before SPI scan) -----
PRESETS = [
    {'name': 'CFG_OSC2_GMP_NUM', 'value': 3},
    {'name': 'CFG_OSC2_IDAC_IBIAS', 'value': 5},
]


# ----- SPI scan setup -----
FIELD_SPECS = {'CFG_OSC2_TEST_BUF_IBIAS': {'values': [0, 3, 4, 7]}, 'CFG_OSC2_GMP_NUM': {'values': [1, 4, 7]}}


def main():
    start_ts = time.perf_counter()
    local_records: list[FullFlowRecord] = []
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
        case_desc=CASE_DESC,
        debug=bool(policy.get('DEBUG', DEBUG)),
        continue_on_error=bool(policy.get('CONTINUE_ON_ERROR', CONTINUE_ON_ERROR)),
    )
    print_case_start(CASE_NAME, case_desc=CASE_DESC, debug=DEBUG, continue_on_error=CONTINUE_ON_ERROR)
    print_flow_config(CASE_NAME, flow)
    print_debug_info('CASE CONFIG', {
        'debug': DEBUG,
        'continue_on_error': CONTINUE_ON_ERROR,
        'enable_measurement': ENABLE_MEASUREMENT,
        'save_screenshot': SAVE_SCREENSHOT,
        'save_csv': SAVE_CSV,
        'save_excel': SAVE_EXCEL,
        'delay_before_measurement_s': DELAY_BEFORE_MEASUREMENT_S,
    }, DEBUG)
    combos = build_value_product(FIELD_SPECS)
    hook = None
    try:
        with ChipSpi() as chip, make_client_from_config(cfg) as inst:
            print_instrument_debug(cfg, inst, bool(policy.get('DEBUG', DEBUG)))
            preset_values = {}
            preset_results = apply_presets(chip, PRESETS)
            print_presets(preset_results)
            preset_values = {item['name']: item['value'] for item in PRESETS}
            hook = E5052BMeasurementHook(inst, capture_options, flow)
            session = TestSession(chip, hook, runtime_policy=policy)
            for idx, combo in enumerate(combos):
                print_progress(idx, len(combos), combo)
                print_debug_info('STEP CONTEXT', {'step_idx': idx + 1, 'active_values': combo}, DEBUG)
                for field_name, value in combo.items():
                    try:
                        record = session.run_field_write_read(
                            field_name,
                            value,
                            case_name=CASE_NAME,
                            preset_values=preset_values,
                            active_values=combo,
                            step_idx=idx,
                        )
                        print_record(record)
                    except Exception as exc:
                        print_case_error(CASE_NAME, 'SPI_SCAN', exc, step_idx=idx, active_values=combo)
                        register_error_record(hook, local_records, target_name=field_name, write_value=value, case_name=CASE_NAME, preset_values=preset_values, active_values=combo, step_idx=idx, stage='SPI_SCAN', exc=exc)
                        if not CONTINUE_ON_ERROR:
                            raise
            print_debug_info('EXPORT CONTEXT', {'record_count': len(hook.records), 'run_dir': str(hook.run_dir)}, DEBUG)
            merged = hook.export_merged_summary(f'merged_summary_{CASE_NAME}.xlsx')
            print_debug_info('EXPORT CONTEXT', {'merged_summary_path': merged, 'run_dir': str(hook.run_dir)}, DEBUG)
            print_block(format_output_paths({'merged_summary_path': merged, 'run_dir': str(hook.run_dir)}))
            write_run_meta(hook.run_dir, {
                'case_name': CASE_NAME, 'case_desc': CASE_DESC, 'debug': DEBUG, 'continue_on_error': CONTINUE_ON_ERROR,
                'enable_measurement': ENABLE_MEASUREMENT, 'save_screenshot': SAVE_SCREENSHOT, 'save_csv': SAVE_CSV,
                'save_excel': SAVE_EXCEL, 'delay_before_measurement_s': DELAY_BEFORE_MEASUREMENT_S,
                'presets': PRESETS if 'PRESETS' in globals() else [], 'field_specs': FIELD_SPECS,
                'elapsed_s': round(time.perf_counter() - start_ts, 3), 'merged_summary_path': merged,
            })
        records = hook.records if hook is not None else local_records
        print_case_summary(records)
        status = 'PASS' if all(r.overall_status == 'PASS' for r in records) else 'FAIL'
        print_case_done(CASE_NAME, status=status, run_dir=str(hook.run_dir) if hook else None, merged_summary_path=merged, elapsed_s=time.perf_counter() - start_ts)
    except Exception as exc:
        print_case_error(CASE_NAME, 'CASE_MAIN', exc)
        print_case_done(CASE_NAME, status='FAIL', run_dir=str(hook.run_dir) if hook else None, elapsed_s=time.perf_counter() - start_ts)
        raise


if __name__ == '__main__':
    main()
