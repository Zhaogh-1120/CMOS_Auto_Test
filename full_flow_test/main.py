from __future__ import annotations

import argparse
import os
import sys

from protocol.chip_spi import ChipSpi, ChipSpiConfig


class TermColor:
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    BLUE = "\033[34m"
    YELLOW = "\033[93m"
    ORANGE = YELLOW


class ColorArgumentParser(argparse.ArgumentParser):
    """Keep argparse usage text unchanged; color only error: and its explanation."""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: {color_text('error: ' + message, TermColor.RED)}\n")


def use_color() -> bool:
    return os.environ.get("NO_COLOR") is None


def color_text(text: str, color: str) -> str:
    if not use_color():
        return text
    return f"{color}{text}{TermColor.RESET}"


def color_result(result: str) -> str:
    color = TermColor.GREEN if result == "PASS" else TermColor.RED
    return color_text(f"result={result}", color)


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


def color_name(name: str) -> str:
    return color_text(f"name={name}", TermColor.YELLOW)


def color_value_dec(value: int) -> str:
    return color_text(f"value_dec={value}", TermColor.ORANGE)


def color_value_hex(value_hex: str) -> str:
    return color_text(f"value_hex={value_hex}", TermColor.ORANGE)


def color_value_bin(value_bin: str) -> str:
    # User-facing display convention uses 2b... (input convention remains 0b...).
    return color_text(f"value_bin={value_bin}", TermColor.ORANGE)


def parse_int(text: str) -> int:
    """Base prefixes: 0b(binary), 0x(hex); unprefixed input is decimal."""
    try:
        value = text.strip().replace("_", "")
        if not value:
            raise ValueError("empty number")
        if value.lower().startswith(("0x", "+0x", "-0x", "0b", "+0b", "-0b", "0o", "+0o", "-0o")):
            return int(value, 0)
        return int(value, 10)
    except ValueError as exc:
        raise ValueError(f"Invalid number {text!r}; use decimal (10), hex (0x0A) or binary (0b01010)") from exc


def parse_decimal(text: str) -> int:
    """Kept for legacy imports; modern CLI uses parse_int for ALL values."""
    return parse_int(text)


def pass_fail(expected: int, actual: int) -> str:
    return "PASS" if expected == actual else "FAIL"


def build_chip(args) -> ChipSpi:
    cfg = ChipSpiConfig(
        clock_hz=args.clock,
        control_mode=args.control_mode,
        cpol=args.cpol,
        cpha=args.cpha,
        address_cmd=args.address_cmd,
        read_response_index=args.response_index,
    )
    return ChipSpi(cfg)


def format_bin(value: int, width: int = 8) -> str:
    return f"2b{value:0{width}b}"


def preflight(parser: argparse.ArgumentParser, args, chip: ChipSpi) -> dict:
    """Reject invalid inputs BEFORE opening hardware or issuing any write frames."""
    action = args.action
    field_actions = {"field-read", "field-write", "field-write-read", "field-sweep"}
    reg_actions = {"write", "write-read", "sweep"}
    writing_actions = {"write", "write-read", "sweep", "field-write", "field-write-read", "field-sweep"}
    data = {}
    if args.dry_run and action not in writing_actions:
        parser.error("--dry-run applies to write/write-read/sweep/field-write/field-write-read/field-sweep only")
    if args.dry_run and args.use_shadow:
        parser.error("--dry-run cannot be combined with --use-shadow; previews always read the real register")
    if args.response_index not in (0, 1):
        parser.error("--response-index must be 0 or 1 (normal read response is at index 1)")
    if not 0 <= args.address_cmd <= 0xFF or (args.address_cmd & 0xE0):
        parser.error("--address-cmd must use the 000x xxxx Set Address encoding (e.g. 0x00 or 0x1F)")
    if action == "field-list":
        return data
    if action == "read":
        if (args.reg is None) == (not args.name):
            parser.error("read requires exactly one selector: --reg 0x20 OR --name REG20 OR --name FIELD_NAME")
        if args.reg is not None:
            data["address"] = chip.validate_address(args.reg)
        else:
            address = chip.regmap.resolve_register_name(args.name)
            if address is not None:
                data["address"] = chip.validate_address(address)
                data["register_name"] = args.name
            else:
                data["field"] = chip.get_field(args.name)
        return data
    if action in field_actions:
        if not args.name:
            parser.error(f"--name is required for {action}")
        field = chip.get_field(args.name)
        data["field"] = field
    if action in reg_actions:
        if args.reg is None:
            parser.error(f"--reg is required for {action}")
        data["address"] = chip.validate_address(args.reg)
    if action in {"write", "write-read", "field-write", "field-write-read"}:
        if args.value is None:
            parser.error(f"--value is required for {action}")
        value = parse_int(args.value)
        if action in field_actions:
            chip.validate_field_value(data["field"], value)
        else:
            chip.validate_reg_value(value)
        data["value"] = value
    if action in {"sweep", "field-sweep"}:
        if args.start is None or args.stop is None:
            parser.error(f"--start and --stop are required for {action}")
        start, stop, step = (parse_int(v) for v in (args.start, args.stop, args.step))
        max_value = data["field"].max_decimal if action == "field-sweep" else 0xFF
        data["values"] = chip.validate_sweep(start, stop, step, max_value)
    return data


def print_field_read(chip: ChipSpi, name: str) -> None:
    info = chip.read_field(name)
    print(
        f"FIELD_READ  {color_name(info['field_name'])}  addr={info['address_hex']}  bits={info['bits']}  "
        f"{color_reg_hex(info['reg_value_hex'])}  "
        f"{color_value_hex(info['field_value_hex'])}  "
        f"{color_value_bin(info['field_value_bin'])}  "
        f"{color_value_dec(info['field_value_decimal'])}"
    )


def print_reg_read(chip: ChipSpi, addr: int, name: str | None = None) -> None:
    rx = chip.read_reg_raw(addr)
    value = chip.decode_read_value(rx)
    # Keep the software shadow aligned with what was actually read.
    chip.shadow_registers[addr] = value
    # Show a stable REG name even if the user selected it by numeric address.
    register_name = f"REG{addr:02X}"
    print(f"READ   {color_name(register_name)}  reg=0x{addr:02X}  raw_rx={rx.hex(' ')}  "
          f"{color_read_hex(f'0x{value:02X}')}  "
          f"{color_value_hex(f'0x{value:02X}')}  "
          f"{color_value_bin(format_bin(value))}  "
          f"{color_value_dec(value)}")


def print_field_verify(info: dict) -> None:
    print(f"FIELD_VERIFY  name={info['field_name']}  addr={info['address_hex']}  bits={info['bits']}  "
          f"{color_write_dec(info['write_field_decimal'])}  {color_read_dec(info['read_field_decimal'])}  "
          f"{color_result(info['verify_result'])}  before_reg={info['before_reg_hex']}  "
          f"after_reg={info['after_reg_hex']}")


def print_preview(before: int, after: int, addr: int, field: str | None = None, value: int | None = None) -> None:
    target = f"name={field}  " if field else ""
    field_info = f"  field_value={value}" if field else ""
    print(f"DRY_RUN  {target}reg=0x{addr:02X}{field_info}  "
          f"before_reg=0x{before:02X}  after_reg=0x{after:02X}  "
          f"after_bin={format_bin(after)}  status=NO_REGISTER_WRITE")


def main() -> None:
    parser = ColorArgumentParser(description="Ginkgo SPI automation: REG/field-name read, multi-base write, dry run")
    parser.add_argument("action", choices=["write", "read", "write-read", "sweep", "field-list", "field-read", "field-write", "field-write-read", "field-sweep"])
    parser.add_argument("--reg", type=parse_int, help="register address: 0x20, 32, 0b100000")
    parser.add_argument("--name", help="read: REG20 or field name; field actions: field name")
    parser.add_argument("--value", help="value: 10 (dec), 0x0A (hex), 0b01010 (bin)")
    parser.add_argument("--start", help="sweep start in decimal/hex/binary")
    parser.add_argument("--stop", help="sweep stop in decimal/hex/binary")
    parser.add_argument("--step", help="sweep step in decimal/hex/binary", default="1")
    parser.add_argument("--dry-run", action="store_true", help="read real register and show prospective write(s), WITHOUT writing register data")
    parser.add_argument("--clock", type=int, default=500_000, help="SPI clock in Hz")
    parser.add_argument("--control-mode", type=int, default=0, help="0=hardware control")
    parser.add_argument("--cpol", type=int, default=0, help="validated on your setup: idle low")
    parser.add_argument("--cpha", type=int, default=0, help="validated on your setup: rising-edge sample")
    parser.add_argument("--response-index", type=int, default=1, help="received byte containing register data, default 1")
    parser.add_argument("--address-cmd", type=parse_int, default=0x00,
                        help="Set Address instruction, default 0x00; 0x1F is an alternative")
    parser.add_argument("--use-shadow", action="store_true", help="field writes use software shadow (not permitted in dry run)")
    args = parser.parse_args()

    chip = build_chip(args)
    try:
        data = preflight(parser, args, chip)
    except (KeyError, ValueError) as exc:
        parser.error(str(exc))

    if args.action == "field-list":
        for line in chip.regmap.list_lines():
            print(line)
        return

    with chip:
        if args.action == "read":
            if "field" in data:
                print_field_read(chip, data["field"].name)
            else:
                print_reg_read(chip, data["address"], data.get("register_name"))
        elif args.action == "field-read":  # Backward-compatible alias
            print_field_read(chip, data["field"].name)
        elif args.action == "write":
            addr, value = data["address"], data["value"]
            if args.dry_run:
                info = chip.preview_reg(addr, value)
                print_preview(info["before_reg"], info["after_reg"], addr)
            else:
                chip.write_reg(addr, value)
                print(f"WRITE  reg=0x{addr:02X}  {color_write_hex(f'0x{value:02X}')}  status=DONE")
        elif args.action == "write-read":
            addr, value = data["address"], data["value"]
            if args.dry_run:
                info = chip.preview_reg(addr, value)
                print_preview(info["before_reg"], info["after_reg"], addr)
            else:
                actual, raw = chip.write_then_read(addr, value)
                print(f"VERIFY reg=0x{addr:02X}  {color_write_hex(f'0x{value:02X}')}  "
                      f"raw_rx={raw.hex(' ')}  {color_read_hex(f'0x{actual:02X}')}  "
                      f"{color_result(pass_fail(value, actual))}")
        elif args.action == "sweep":
            addr = data["address"]
            if args.dry_run:
                before = chip.read_reg(addr)  # Read once: no writes; baseline remains unchanged.
                for value in data["values"]:
                    print_preview(before, value, addr)
            else:
                values = data["values"]
                for write_val, read_val, raw in chip.sweep_reg(addr, values[0], values[-1], values.step, return_raw=True):
                    print(f"VERIFY reg=0x{addr:02X}  {color_write_hex(f'0x{write_val:02X}')}  "
                          f"raw_rx={raw.hex(' ')}  {color_read_hex(f'0x{read_val:02X}')}  "
                          f"{color_result(pass_fail(write_val, read_val))}")
        elif args.action == "field-write":
            field, value = data["field"], data["value"]
            if args.dry_run:
                info = chip.preview_field(field.name, value)
                print_preview(info["before_reg"], info["after_reg"], field.address, field.alias, value)
            else:
                info = chip.write_field(field.name, value, verify=False, use_shadow=args.use_shadow)
                print(f"FIELD_WRITE  name={info['field_name']}  addr={info['address_hex']}  "
                      f"bits={info['bits']}  {color_write_dec(info['write_field_decimal'])}  "
                      f"before_reg={info['before_reg_hex']}  after_reg={info['after_reg_hex']}")
        elif args.action == "field-write-read":
            field, value = data["field"], data["value"]
            if args.dry_run:
                info = chip.preview_field(field.name, value)
                print_preview(info["before_reg"], info["after_reg"], field.address, field.alias, value)
            else:
                print_field_verify(chip.write_field_then_read(field.name, value, use_shadow=args.use_shadow))
        elif args.action == "field-sweep":
            field = data["field"]
            if args.dry_run:
                before = chip.read_reg(field.address)
                for value in data["values"]:
                    after = chip.compose_field_value(before, field, value)
                    print_preview(before, after, field.address, field.alias, value)
            else:
                values = data["values"]
                for info in chip.sweep_field(field.name, values[0], values[-1], values.step, use_shadow=args.use_shadow):
                    print_field_verify(info)


if __name__ == "__main__":
    main()
