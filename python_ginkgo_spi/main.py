from __future__ import annotations

import argparse
import os

from protocol.chip_spi import ChipSpi, ChipSpiConfig


class TermColor:
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    BLUE = "\033[34m"
    ORANGE = "\033[93m"   # terminal-friendly orange


def use_color() -> bool:
    return os.environ.get("NO_COLOR") is None


def color_text(text: str, color: str) -> str:
    if not use_color():
        return text
    return f"{color}{text}{TermColor.RESET}"


def color_result(result: str) -> str:
    if result == "PASS":
        return color_text(f"result={result}", TermColor.GREEN)
    return color_text(f"result={result}", TermColor.RED)


def color_write_hex(value_hex: str) -> str:
    return color_text(f"write={value_hex}", TermColor.BLUE)


def color_write_dec(value: int) -> str:
    return color_text(f"write_dec={value}", TermColor.BLUE)


def color_read_hex(value_hex: str) -> str:
    return color_text(f"read={value_hex}", TermColor.ORANGE)


def color_read_dec(value: int) -> str:
    return color_text(f"read_dec={value}", TermColor.ORANGE)


def color_reg_hex(reg_hex: str) -> str:
    return color_text(f"reg={reg_hex}", TermColor.ORANGE)


def color_value_dec(value: int) -> str:
    return color_text(f"value_dec={value}", TermColor.ORANGE)


def color_value_hex(value_hex: str) -> str:
    return color_text(f"value_hex={value_hex}", TermColor.ORANGE)


def parse_int(text: str) -> int:
    return int(text, 0)


def parse_decimal(text: str) -> int:
    return int(text, 10)


def pass_fail(expected: int, actual: int) -> str:
    return "PASS" if (expected & 0xFF) == (actual & 0xFF) else "FAIL"


def build_chip(args) -> ChipSpi:
    cfg = ChipSpiConfig(
        clock_hz=args.clock,
        control_mode=args.control_mode,
        cpol=args.cpol,
        cpha=args.cpha,
        read_response_index=args.response_index,
    )
    return ChipSpi(cfg)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ginkgo SPI automation with register and field-name operations")
    parser.add_argument("action", choices=["write", "read", "write-read", "sweep", "field-list", "field-read", "field-write", "field-write-read", "field-sweep"])
    parser.add_argument("--reg", type=parse_int, help="register address, supports 0x20")
    parser.add_argument("--name", help="field name, supports exact name or alias without <bits>")
    parser.add_argument("--value", help="write value. field actions use decimal by default")
    parser.add_argument("--start", help="sweep start. field actions use decimal by default")
    parser.add_argument("--stop", help="sweep stop. field actions use decimal by default")
    parser.add_argument("--step", help="sweep step. field actions use decimal by default", default="1")
    parser.add_argument("--clock", type=int, default=500_000, help="SPI clock in Hz")
    parser.add_argument("--control-mode", type=int, default=0, help="0=hardware control")
    parser.add_argument("--cpol", type=int, default=0, help="validated on your setup: idle low")
    parser.add_argument("--cpha", type=int, default=0, help="validated on your setup: rising-edge sample")
    parser.add_argument("--response-index", type=int, default=1, help="which received byte contains register data during read")
    parser.add_argument("--use-shadow", action="store_true", help="modify fields using software shadow instead of reading the whole register first")
    args = parser.parse_args()

    with build_chip(args) as chip:
        if args.action == "field-list":
            for line in chip.regmap.list_lines():
                print(line)
            return

        if args.action == "write":
            if args.reg is None:
                raise SystemExit("--reg is required for write")
            if args.value is None:
                raise SystemExit("--value is required for write")
            value = parse_int(args.value)
            chip.write_reg(args.reg, value)
            print(f"WRITE  reg=0x{args.reg:02X}  {color_write_hex(f'0x{value:02X}')}  status=DONE")
        elif args.action == "read":
            if args.reg is None:
                raise SystemExit("--reg is required for read")
            rx = chip.read_reg_raw(args.reg)
            value = rx[args.response_index]
            print(f"READ   reg=0x{args.reg:02X}  raw_rx={rx.hex(' ')}  {color_read_hex(f'0x{value:02X}')}")
        elif args.action == "write-read":
            if args.reg is None:
                raise SystemExit("--reg is required for write-read")
            if args.value is None:
                raise SystemExit("--value is required for write-read")
            value = parse_int(args.value)
            actual, raw = chip.write_then_read(args.reg, value)
            result = pass_fail(value, actual)
            print(f"VERIFY reg=0x{args.reg:02X}  {color_write_hex(f'0x{value:02X}')}  raw_rx={raw.hex(' ')}  {color_read_hex(f'0x{actual:02X}')}  {color_result(result)}")
        elif args.action == "sweep":
            if args.reg is None:
                raise SystemExit("--reg is required for sweep")
            if args.start is None or args.stop is None:
                raise SystemExit("--start and --stop are required for sweep")
            start = parse_int(args.start); stop = parse_int(args.stop); step = parse_int(args.step)
            for write_val, read_val, raw in chip.sweep_reg(args.reg, start, stop, step, return_raw=True):
                result = pass_fail(write_val, read_val)
                print(f"VERIFY reg=0x{args.reg:02X}  {color_write_hex(f'0x{write_val:02X}')}  raw_rx={raw.hex(' ')}  {color_read_hex(f'0x{read_val:02X}')}  {color_result(result)}")
        elif args.action == "field-read":
            if not args.name:
                raise SystemExit("--name is required for field-read")
            info = chip.read_field(args.name)

            reg_part = color_reg_hex(info["reg_value_hex"])
            value_part = color_value_dec(info["field_value_decimal"])
            value_hex_part = color_value_hex(info["field_value_hex"])

            print(
                f"FIELD_READ  "
                f"name={info['field_name']}  "
                f"addr={info['address_hex']}  "
                f"bits={info['bits']}  "
                f"{reg_part}  "
                f"{value_part}  "
                f"{value_hex_part}"
                #f"value_hex={info['field_value_hex']}"
            )
        elif args.action == "field-write":
            if not args.name:
                raise SystemExit("--name is required for field-write")
            if args.value is None:
                raise SystemExit("--value is required for field-write")
            info = chip.write_field(args.name, parse_decimal(args.value), verify=False, use_shadow=args.use_shadow)
            print(f"FIELD_WRITE  name={info['field_name']}  addr={info['address_hex']}  bits={info['bits']}  {color_write_dec(info['write_field_decimal'])}  before_reg={info['before_reg_hex']}  after_reg={info['after_reg_hex']}")
        elif args.action == "field-write-read":
            if not args.name:
                raise SystemExit("--name is required for field-write-read")
            if args.value is None:
                raise SystemExit("--value is required for field-write-read")
            info = chip.write_field_then_read(args.name, parse_decimal(args.value), use_shadow=args.use_shadow)
            print(f"FIELD_VERIFY  name={info['field_name']}  addr={info['address_hex']}  bits={info['bits']}  {color_write_dec(info['write_field_decimal'])}  {color_read_dec(info['read_field_decimal'])}  {color_result(info['verify_result'])}  before_reg={info['before_reg_hex']}  after_reg={info['after_reg_hex']}")
        elif args.action == "field-sweep":
            if not args.name:
                raise SystemExit("--name is required for field-sweep")
            if args.start is None or args.stop is None:
                raise SystemExit("--start and --stop are required for field-sweep")
            start = parse_decimal(args.start); stop = parse_decimal(args.stop); step = parse_decimal(args.step)
            for info in chip.sweep_field(args.name, start, stop, step, use_shadow=args.use_shadow):
                print(f"FIELD_VERIFY  name={info['field_name']}  addr={info['address_hex']}  bits={info['bits']}  {color_write_dec(info['write_field_decimal'])}  {color_read_dec(info['read_field_decimal'])}  {color_result(info['verify_result'])}  before_reg={info['before_reg_hex']}  after_reg={info['after_reg_hex']}")


if __name__ == "__main__":
    main()
