from protocol.chip_spi import ChipSpi
from core.formatter import format_field_verify
from utils.range_helper import inclusive_range


def main():
    with ChipSpi() as chip:
        for gm in inclusive_range(0, 7, 1):
            for ibias in inclusive_range(0, 15, 1):
                info_gm = chip.write_field_then_read("CFG_OSC2_GMP_NUM", gm)
                info_ibias = chip.write_field_then_read("CFG_OSC2_TEST_BUF_IBIAS", ibias)
                print(format_field_verify(info_gm))
                print(format_field_verify(info_ibias))


if __name__ == "__main__":
    main()
