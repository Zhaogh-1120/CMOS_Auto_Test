from protocol.chip_spi import ChipSpi

with ChipSpi() as chip:
    chip.write_reg(0x20, 0x05)
    value = chip.read_reg(0x20)
    print(f"REG20 readback = 0x{value:02X}")
