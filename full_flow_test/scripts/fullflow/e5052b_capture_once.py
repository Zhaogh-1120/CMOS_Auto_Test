from __future__ import annotations

import time

from instruments.e5052b.capture import capture_phase_noise_once
from scripts.fullflow.common import build_capture_options, build_case_policy, make_client_from_config, print_block, print_case_done, print_case_error, print_case_start, print_debug_info, print_instrument_debug, write_run_meta
from utils.e5052b_config import load_e5052b_config
from core.formatter import format_e5052b_summary, format_flow_header, format_output_paths

# =========================================================
# User config section
# =========================================================
CASE_NAME = 'e5052b_capture_once'
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

CASE_DESC = 'single E5052B capture without SPI actions'

# ----- Full-flow switches -----
ENABLE_MEASUREMENT = True
SAVE_SCREENSHOT = True
#SAVE_SCREENSHOT = False
SAVE_CSV = True
SAVE_EXCEL = True
DELAY_BEFORE_CAPTURE_S = None  # None -> use config file default
OUTPUT_DIR = 'outputs/e5052b/capture_once'


def main():
    start_ts = time.perf_counter()
    cfg = load_e5052b_config()
    policy = build_case_policy(CASE_POLICY)
    save_screenshot = SAVE_SCREENSHOT if SAVE_SCREENSHOT is not None else cfg.get('save_screenshot', True)
    options = build_capture_options(cfg, save_screenshot=save_screenshot)
    if DELAY_BEFORE_CAPTURE_S is not None:
        options.delay_before_capture_s = DELAY_BEFORE_CAPTURE_S
    options.save_csv = SAVE_CSV and options.save_csv
    options.save_excel = SAVE_EXCEL and options.save_excel

    print_case_start(CASE_NAME, case_desc=CASE_DESC, debug=DEBUG, continue_on_error=CONTINUE_ON_ERROR)
    print_block(format_flow_header(CASE_NAME, {
        'case_desc': CASE_DESC,
        'enable_measurement': ENABLE_MEASUREMENT,
        'save_screenshot': options.save_screenshot,
        'save_csv': options.save_csv,
        'save_excel': options.save_excel,
        'delay_before_capture_s': options.delay_before_capture_s,
        'output_dir': OUTPUT_DIR,
        'debug': DEBUG,
        'continue_on_error': CONTINUE_ON_ERROR,
    }))
    print_debug_info('CASE CONFIG', {
        'debug': DEBUG,
        'continue_on_error': CONTINUE_ON_ERROR,
        'enable_measurement': ENABLE_MEASUREMENT,
        'save_screenshot': options.save_screenshot,
        'save_csv': options.save_csv,
        'save_excel': options.save_excel,
        'delay_before_capture_s': options.delay_before_capture_s,
        'output_dir': OUTPUT_DIR,
        'host': cfg.get('host'),
        'port': cfg.get('port', 5025),
        'timeout_s': cfg.get('timeout_s', 15.0),
    }, DEBUG)

    try:
        with make_client_from_config(cfg) as inst:
            print_debug_info('MEASUREMENT CONTEXT', {'host': cfg.get('host'), 'port': cfg.get('port', 5025), 'timeout_s': cfg.get('timeout_s', 15.0), 'output_dir': OUTPUT_DIR}, DEBUG)
            result = capture_phase_noise_once(inst, options, out_dir=OUTPUT_DIR, shot_name=None)
            print_block(format_e5052b_summary(result))
            print_debug_info('EXPORT CONTEXT', {'run_dir': result.run_dir, 'excel_path': result.excel_path, 'raw_csv_path': result.raw_csv_path, 'screenshot_path': result.screenshot_path}, DEBUG)
            print_block(format_output_paths({
                'run_dir': result.run_dir,
                'screenshot_path': result.screenshot_path,
                'raw_csv_path': result.raw_csv_path,
                'excel_path': result.excel_path,
            }))
            if result.run_dir:
                write_run_meta(result.run_dir, {
                    'case_name': CASE_NAME, 'case_desc': CASE_DESC, 'debug': DEBUG, 'continue_on_error': CONTINUE_ON_ERROR,
                    'save_screenshot': options.save_screenshot, 'save_csv': options.save_csv, 'save_excel': options.save_excel,
                    'delay_before_capture_s': options.delay_before_capture_s, 'elapsed_s': round(time.perf_counter()-start_ts, 3),
                })
            print_case_done(CASE_NAME, status='PASS', run_dir=result.run_dir, elapsed_s=time.perf_counter() - start_ts)
    except Exception as exc:
        print_case_error(CASE_NAME, 'MEASURE_CAPTURE', exc)
        print_case_done(CASE_NAME, status='FAIL', elapsed_s=time.perf_counter() - start_ts)
        raise


if __name__ == '__main__':
    main()
