from __future__ import annotations

import os


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


def format_field_read(info: dict) -> str:
    return (
        f"FIELD_READ  "
        f"name={info['field_name']}  "
        f"addr={info['address_hex']}  "
        f"bits={info['bits']}  "
        f"{color_reg_hex(info['reg_value_hex'])}  "
        f"{color_value_dec(info['field_value_decimal'])}  "
        f"{color_value_hex(info['field_value_hex'])}"
    )


def format_field_write(info: dict) -> str:
    return (
        f"FIELD_WRITE  "
        f"name={info['field_name']}  "
        f"addr={info['address_hex']}  "
        f"bits={info['bits']}  "
        f"{color_write_dec(info['write_field_decimal'])}  "
        f"before_reg={info['before_reg_hex']}  "
        f"after_reg={info['after_reg_hex']}"
    )


def format_field_verify(info: dict) -> str:
    return (
        f"FIELD_VERIFY  "
        f"name={info['field_name']}  "
        f"addr={info['address_hex']}  "
        f"bits={info['bits']}  "
        f"{color_write_dec(info['write_field_decimal'])}  "
        f"{color_read_dec(info['read_field_decimal'])}  "
        f"{color_result(info['verify_result'])}  "
        f"before_reg={info['before_reg_hex']}  "
        f"after_reg={info['after_reg_hex']}"
    )


def format_reg_write(reg_addr: int, value: int) -> str:
    return f"WRITE  reg=0x{reg_addr:02X}  {color_write_hex(f'0x{value:02X}')}  status=DONE"


def format_reg_read(reg_addr: int, raw_rx: bytes, value: int) -> str:
    return f"READ   reg=0x{reg_addr:02X}  raw_rx={raw_rx.hex(' ')}  {color_read_hex(f'0x{value:02X}')}"


def format_reg_verify(reg_addr: int, write_value: int, raw_rx: bytes, read_value: int, result: str) -> str:
    return (
        f"VERIFY reg=0x{reg_addr:02X}  "
        f"{color_write_hex(f'0x{write_value:02X}')}  "
        f"raw_rx={raw_rx.hex(' ')}  "
        f"{color_read_hex(f'0x{read_value:02X}')}  "
        f"{color_result(result)}"
    )
