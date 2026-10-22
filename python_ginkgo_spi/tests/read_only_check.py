"""Read one SPI register without sending any Write Data instruction.

Usage: python -m tests.read_only_check --reg 0x20
"""
from __future__ import annotations

import argparse
from protocol.chip_spi import ChipSpi, ChipSpiConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Non-destructive SPI register read check")
    parser.add_argument("--reg", type=lambda s: int(s, 0), default=0x20)
    parser.add_argument("--address-cmd", type=lambda s: int(s, 0), default=0x00)
    args = parser.parse_args()
    if not 0 <= args.reg <= 0xFF:
        parser.error("--reg must be an 8-bit register address")
    if args.address_cmd not in (0x00, 0x1F):
        parser.error("use a documented Set Address instruction: 0x00 or 0x1F")

    with ChipSpi(ChipSpiConfig(address_cmd=args.address_cmd)) as chip:
        rx = chip.read_reg_raw(args.reg)
        value = chip.decode_read_value(rx)
        print(f"SET_ADDRESS tx={args.address_cmd:02X} {args.reg:02X} (CS released afterward)")
        print("READ_DATA  tx=80 00 (new CS frame)")
        print(f"READ_DATA  raw_rx={rx.hex(' ')}  reg=0x{args.reg:02X}  value=0x{value:02X} ({value})")
        print("No SPI Write Data command was issued.")


if __name__ == "__main__":
    main()
