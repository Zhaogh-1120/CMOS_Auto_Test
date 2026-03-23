from protocol.chip_spi import ChipSpi
from core.formatter import format_field_verify
from utils.range_helper import inclusive_range


def main():
    with ChipSpi() as chip:
        for a in inclusive_range(0, 7, 1):
            info_a = chip.write_field_then_read("CFG_OSC2_GMP_NUM", a)
            print(format_field_verify(info_a))
            for b in inclusive_range(0, 15, 1):
                info_b = chip.write_field_then_read("CFG_OSC2_TEST_BUF_IBIAS", b)
                print(format_field_verify(info_b))


if __name__ == "__main__":
    main()
