from __future__ import annotations

from protocol.chip_spi import ChipSpi

REG = 0x20
VALUES = [0x00, 0x01, 0x03, 0x05, 0x07]

with ChipSpi() as chip:
    for value in VALUES:
        read_value, raw = chip.write_then_read(REG, value)
        result = "PASS" if read_value == value else "FAIL"
        print(
            f"VERIFY reg=0x{REG:02X}, write=0x{value:02X}, raw_rx={raw.hex(' ')}, read=0x{read_value:02X}, result={result}"
        )
