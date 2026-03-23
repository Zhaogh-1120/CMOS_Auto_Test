from protocol.chip_spi import ChipSpi
from core.formatter import format_field_verify


def main():
    with ChipSpi() as chip:
        result = chip.write_field_then_read("CFG_OSC2_GMP_NUM", 5)
        print(format_field_verify(result))


if __name__ == "__main__":
    main()
