from protocol.chip_spi import ChipSpi
from core.formatter import format_reg_read


def main():
    with ChipSpi() as chip:
        reg = 0x20
        raw_rx = chip.read_reg_raw(reg)
        value = chip.decode_read_value(raw_rx)
        print(format_reg_read(reg, raw_rx, value))


if __name__ == "__main__":
    main()
