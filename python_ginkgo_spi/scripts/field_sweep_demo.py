from protocol.chip_spi import ChipSpi
from core.formatter import format_field_verify


def main():
    with ChipSpi() as chip:
        for info in chip.sweep_field("CFG_OSC2_GMP_NUM", 0, 7, 1):
            print(format_field_verify(info))


if __name__ == "__main__":
    main()
