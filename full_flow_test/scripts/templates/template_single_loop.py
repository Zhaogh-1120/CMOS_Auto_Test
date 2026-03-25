from protocol.chip_spi import ChipSpi
from core.formatter import print_block, format_field_verify
from utils.range_helper import inclusive_range


def main():
    with ChipSpi() as chip:
        for value in inclusive_range(0, 7, 1):
            info = chip.write_field_then_read("CFG_OSC2_GMP_NUM", value)
            print_block(format_field_verify(info))


if __name__ == "__main__":
    main()
