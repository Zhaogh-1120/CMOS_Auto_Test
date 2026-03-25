from protocol.chip_spi import ChipSpi
from core.formatter import print_block, format_field_write


def main():
    with ChipSpi() as chip:
        info = chip.write_field("CFG_OSC2_GMP_NUM", 5)
        print_block(format_field_write(info))


if __name__ == "__main__":
    main()
