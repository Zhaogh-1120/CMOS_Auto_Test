from protocol.chip_spi import ChipSpi
from core.formatter import format_reg_verify
from utils.range_helper import inclusive_range


def main():
    with ChipSpi() as chip:
        reg = 0x20
        for write_value in inclusive_range(0, 7, 1):
            read_value, raw_rx = chip.write_then_read(reg, write_value)
            result = "PASS" if read_value == write_value else "FAIL"
            print(format_reg_verify(reg, write_value, raw_rx, read_value, result))


if __name__ == "__main__":
    main()
