from protocol.chip_spi import ChipSpi
from core.formatter import print_block, format_reg_write


def main():
    with ChipSpi() as chip:
        reg = 0x20
        value = 0x05
        chip.write_reg(reg, value)
        print_block(format_reg_write(reg, value))


if __name__ == "__main__":
    main()
