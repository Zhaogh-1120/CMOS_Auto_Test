from protocol.chip_spi import ChipSpi

with ChipSpi() as chip:
    results = chip.sweep_reg(0x20, 0, 7, 1)
    for write_val, read_val in results:
        print(f"write=0x{write_val:02X}, read=0x{read_val:02X}")
