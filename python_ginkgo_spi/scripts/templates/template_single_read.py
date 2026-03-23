from protocol.chip_spi import ChipSpi
from core.formatter import format_field_read


def main():
    with ChipSpi() as chip:
        info = chip.read_field("CFG_OSC2_GMP_NUM")
        print(format_field_read(info))


if __name__ == "__main__":
    main()
