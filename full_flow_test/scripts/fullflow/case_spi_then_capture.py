from __future__ import annotations

import time

from protocol.chip_spi import ChipSpi
from core.measurement_hook import E5052BMeasurementHook, FlowOptions
from core.result_model import FullFlowRecord
from core.session import TestSession
from scripts.fullflow.common import (
    build_capture_options, build_case_policy,
    make_client_from_config,
    print_case_done,
    print_case_error,
    print_case_start,
    print_debug_info, print_instrument_debug,
    print_case_summary,
    print_flow_config,
    print_progress,
    print_record,
    register_error_record,
    write_run_meta,
)
from utils.e5052b_config import load_e5052b_config

# =========================================================
# User config section
# =========================================================
CASE_NAME = 'case_spi_then_capture'
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

CASE_DESC = 'single SPI write/read then capture E5052B with screenshot'

# ----- Full-flow switches -----
ENABLE_MEASUREMENT = True
SAVE_SCREENSHOT = True
SAVE_CSV = True
SAVE_EXCEL = True
DELAY_BEFORE_MEASUREMENT_S = 0.0

# ----- SPI action setup -----
FIELD_NAME = 'CFG_OSC2_GMP_NUM'
FIELD_VALUE = 5


def main():
    start_ts = time.perf_counter()
    local_records: list[FullFlowRecord] = []
    cfg = load_e5052b_config()
    policy = build_case_policy(CASE_POLICY)
    capture_options = build_capture_options(cfg, save_screenshot=SAVE_SCREENSHOT)
    flow = FlowOptions(
        enable_measurement=ENABLE_MEASUREMENT,
        delay_before_measurement_s=DELAY_BEFORE_MEASUREMENT_S,
        save_screenshot=SAVE_SCREENSHOT,
        save_csv=SAVE_CSV and cfg.get('save_csv', True),
        save_excel=SAVE_EXCEL and cfg.get('save_excel', True),
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

    hook = None
    try:
        with ChipSpi() as chip, make_client_from_config(cfg) as inst:
            print_instrument_debug(cfg, inst, bool(policy.get('DEBUG', DEBUG)))
            hook = E5052BMeasurementHook(inst, capture_options, flow)
            session = TestSession(chip, hook, runtime_policy=policy)
            print_progress(0, 1, {FIELD_NAME: FIELD_VALUE})
            try:
                record = session.run_field_write_read(
                    FIELD_NAME,
                    FIELD_VALUE,
                    case_name=CASE_NAME,
                    active_values={FIELD_NAME: FIELD_VALUE},
                )
                local_records.append(record)
                print_record(record)
            except Exception as exc:
                print_case_error(CASE_NAME, 'SPI_SCAN', exc, step_idx=0, active_values={FIELD_NAME: FIELD_VALUE})
                record = register_error_record(hook, local_records, target_name=FIELD_NAME, write_value=FIELD_VALUE, case_name=CASE_NAME, active_values={FIELD_NAME: FIELD_VALUE}, step_idx=0, stage='SPI_SCAN', exc=exc)
                if not CONTINUE_ON_ERROR:
                    raise

        records = hook.records if hook is not None else local_records
        print_case_summary(records)
        run_dir = None
        merged = None
        if hook is not None:
            run_dir = str(hook.run_dir)
            if hook.records and any(r.measurement_result is not None for r in hook.records):
                run_meta = write_run_meta(hook.run_dir, {
                    'case_name': CASE_NAME,
                    'case_desc': CASE_DESC,
                    'debug': DEBUG,
                    'continue_on_error': CONTINUE_ON_ERROR,
                    'enable_measurement': ENABLE_MEASUREMENT,
                    'save_screenshot': SAVE_SCREENSHOT,
                    'save_csv': SAVE_CSV,
                    'save_excel': SAVE_EXCEL,
                    'delay_before_measurement_s': DELAY_BEFORE_MEASUREMENT_S,
                    'field_name': FIELD_NAME,
                    'field_value': FIELD_VALUE,
                    'elapsed_s': round(time.perf_counter() - start_ts, 3),
                })
        status = 'PASS' if all(r.overall_status == 'PASS' for r in records) else 'FAIL'
        print_case_done(CASE_NAME, status=status, run_dir=run_dir, merged_summary_path=merged, elapsed_s=time.perf_counter() - start_ts)
    except Exception as exc:
        print_case_error(CASE_NAME, 'CASE_MAIN', exc)
        print_case_done(CASE_NAME, status='FAIL', elapsed_s=time.perf_counter() - start_ts)
        raise


if __name__ == '__main__':
    main()
