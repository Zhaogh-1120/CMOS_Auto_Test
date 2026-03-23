from protocol.chip_spi import ChipSpi
from core.formatter import format_field_verify
from utils.range_helper import inclusive_range
import time

def main():
    with ChipSpi() as chip:
        for value in inclusive_range(0, 15, 2):
            info = chip.write_field_then_read("CFG_OSC2_IDAC_IBIAS", value)
            print(format_field_verify(info))
            time.sleep(3)

if __name__ == "__main__":
    main()