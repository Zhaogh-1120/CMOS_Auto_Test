from __future__ import annotations

from protocol.chip_spi import ChipSpi

REG = 0x20
VALUE = 0x05

with ChipSpi() as chip:
    print(f"Step 1/5: write address frame -> [00 {REG:02X}]")
    chip.transfer(bytes([0x00, REG]))
    print(f"Step 2/5: write data frame    -> [40 {VALUE:02X}]")
    chip.transfer(bytes([0x40, VALUE]))
    print(f"Step 3/5: read frames         -> [00 {REG:02X}] + [80 00] (two separate CS cycles)")
    rx = chip.read_reg_raw(REG)
    print(f"Step 4/5: raw SDO bytes      -> {rx.hex(' ')}")
    read_value = chip.decode_read_value(rx)
    result = "PASS" if read_value == VALUE else "FAIL"
    print(f"Step 5/5: compare            -> write=0x{VALUE:02X}, read=0x{read_value:02X}, result={result}")
