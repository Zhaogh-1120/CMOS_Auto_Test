from __future__ import annotations

from protocol.chip_spi import ChipSpi
from core.session import TestSession
from core.measurement_hook import FlowOptions
from scripts.fullflow.common import print_flow_config, print_record

# =========================================================
# User config section
# =========================================================
CASE_NAME = 'template_spi_case'

# ----- Flow switches -----
ENABLE_MEASUREMENT = False
SAVE_SCREENSHOT = False
SAVE_CSV = False
SAVE_EXCEL = False
DELAY_BEFORE_MEASUREMENT_S = 0.0

# ----- SPI action setup -----
FIELD_NAME = 'CFG_OSC2_GMP_NUM'
FIELD_VALUE = 5


def main():
    flow = FlowOptions(
        enable_measurement=ENABLE_MEASUREMENT,
        save_screenshot=SAVE_SCREENSHOT,
        save_csv=SAVE_CSV,
        save_excel=SAVE_EXCEL,
        delay_before_measurement_s=DELAY_BEFORE_MEASUREMENT_S,
        output_dir=f'outputs/fullflow/{CASE_NAME}',
        case_name=CASE_NAME,
    )
    print_flow_config(CASE_NAME, flow)

    with ChipSpi() as chip:
        session = TestSession(chip)
        record = session.run_field_write_read(
            FIELD_NAME,
            FIELD_VALUE,
            case_name=CASE_NAME,
            active_values={FIELD_NAME: FIELD_VALUE},
        )
        print_record(record)


if __name__ == '__main__':
    main()
