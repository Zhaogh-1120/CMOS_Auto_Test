from __future__ import annotations

import time

from protocol.chip_spi import ChipSpi
from core.formatter import format_field_verify
from scripts.fullflow.common import print_block, print_case_done, print_case_error, print_case_start, print_case_summary, print_progress
from core.result_model import FullFlowRecord, SPIActionResult

# =========================================================
# User config section
# =========================================================
CASE_NAME = 'field_sweep_demo'
# DEBUG:
# False = standard terminal output only
# True  = print extra internal debug details for troubleshooting
DEBUG = False

# CONTINUE_ON_ERROR:
# False = stop the whole case immediately when one step fails
# True  = record the failure and continue remaining steps
CONTINUE_ON_ERROR = False

CASE_DESC = 'single SPI sweep demo without measurement'
DEBUG = False
CONTINUE_ON_ERROR = False
ENABLE_MEASUREMENT = False
FIELD_NAME = 'CFG_OSC2_GMP_NUM'
START_VALUE = 0
STOP_VALUE = 7
STEP_VALUE = 1


def main():
    start_ts = time.perf_counter()
    records=[]
    values=list(range(START_VALUE, STOP_VALUE+1, STEP_VALUE))
    print_case_start(CASE_NAME, case_desc=CASE_DESC, debug=DEBUG, continue_on_error=CONTINUE_ON_ERROR)
    try:
        with ChipSpi() as chip:
            for idx, info in enumerate(chip.sweep_field(FIELD_NAME, START_VALUE, STOP_VALUE, STEP_VALUE)):
                active={FIELD_NAME: info.get('write_field_decimal')}
                print_progress(idx, len(values), active)
                print_block(format_field_verify(info))
                records.append(FullFlowRecord(spi_result=SPIActionResult.from_field_info(info), case_name=CASE_NAME, active_values=active, step_idx=idx))
        print_case_summary(records)
        print_case_done(CASE_NAME, status='PASS', elapsed_s=time.perf_counter()-start_ts)
    except Exception as exc:
        print_case_error(CASE_NAME, 'SPI_SCAN', exc)
        print_case_done(CASE_NAME, status='FAIL', elapsed_s=time.perf_counter()-start_ts)
        raise


if __name__ == '__main__':
    main()
