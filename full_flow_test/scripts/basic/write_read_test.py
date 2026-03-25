from protocol.chip_spi import ChipSpi
from core.formatter import print_block, format_field_verify


def main():
    with ChipSpi() as chip:
        info = chip.write_field_then_read("CFG_OSC2_IDAC_IBIAS", 8)
        print_block(format_field_verify(info))


if __name__ == "__main__":
    main()
