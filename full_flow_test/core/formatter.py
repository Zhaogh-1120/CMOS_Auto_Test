from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Mapping


class TermColor:
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    BLUE = "\033[34m"
    ORANGE = "\033[93m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"
    MAGENTA = "\033[95m"


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


def color_status_value(status: str) -> str:
    if status == 'PASS':
        return color_text(status, TermColor.GREEN)
    if status in {'FAIL', 'ERROR', 'TIMEOUT'}:
        return color_text(status, TermColor.RED)
    return color_text(status, TermColor.ORANGE)


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


def section_title(title: str) -> str:
    return color_text(f"[{title}]", TermColor.CYAN)


def lifecycle_title(title: str) -> str:
    return color_text(f"[{title}]", TermColor.MAGENTA)


def key_label(name: str) -> str:
    return color_text(name, TermColor.BLUE)


def muted_path(path: str | None) -> str:
    if not path:
        return 'None'
    return color_text(str(path), TermColor.GRAY)


def print_block(text: str) -> None:
    print(text + "\n")


def format_field_read(info: dict) -> str:
    return (
        f"FIELD_READ "
        f"name={info['field_name']} "
        f"addr={info['address_hex']} "
        f"bits={info['bits']} "
        f"{color_reg_hex(info['reg_value_hex'])} "
        f"{color_value_dec(info['field_value_decimal'])} "
        f"{color_value_hex(info['field_value_hex'])}"
    )


def format_field_write(info: dict) -> str:
    return (
        f"FIELD_WRITE "
        f"name={info['field_name']} "
        f"addr={info['address_hex']} "
        f"bits={info['bits']} "
        f"{color_write_dec(info['write_field_decimal'])} "
        f"before_reg={info['before_reg_hex']} "
        f"after_reg={info['after_reg_hex']}"
    )


def format_field_verify(info: dict) -> str:
    return (
        f"FIELD_VERIFY "
        f"name={info['field_name']} "
        f"addr={info['address_hex']} "
        f"bits={info['bits']} "
        f"{color_write_dec(info['write_field_decimal'])} "
        f"{color_read_dec(info['read_field_decimal'])} "
        f"{color_result(info['verify_result'])} "
        f"before_reg={info['before_reg_hex']} "
        f"after_reg={info['after_reg_hex']}"
    )


def format_reg_write(reg_addr: int, value: int) -> str:
    return f"WRITE  reg=0x{reg_addr:02X}  {color_write_hex(f'0x{value:02X}')}  status=DONE"


def format_reg_read(reg_addr: int, raw_rx: bytes, value: int) -> str:
    return f"READ   reg=0x{reg_addr:02X}  raw_rx={raw_rx.hex(' ')}  {color_read_hex(f'0x{value:02X}') }"


def format_reg_verify(reg_addr: int, write_value: int, raw_rx: bytes, read_value: int, result: str) -> str:
    return (
        f"VERIFY reg=0x{reg_addr:02X}  "
        f"{color_write_hex(f'0x{write_value:02X}')}  "
        f"raw_rx={raw_rx.hex(' ')}  "
        f"{color_read_hex(f'0x{read_value:02X}')}  "
        f"{color_result(result)}"
    )


def _render_mapping_lines(title_func, title: str, config: Mapping[str, object]) -> str:
    rows = [title_func(title)]
    for k, v in config.items():
        rows.append(f"{key_label(str(k))}={v}")
    return "\n".join(rows)




def format_debug_info(title: str, data: Mapping[str, object]) -> str:
    rows = [lifecycle_title(f"DEBUG INFO: {title}")]
    for k, v in data.items():
        rows.append(f"{key_label(str(k))}={v}")
    return "\n".join(rows)

def format_flow_header(case_name: str, config: Mapping[str, object]) -> str:
    rows = [section_title('FLOW CONFIG')]
    for k, v in config.items():
        rows.append(f"{key_label(str(k))}={v}")
    return "\n".join(rows)


def format_mapping_section(title: str, data: Mapping[str, object] | None) -> str:
    rows = [section_title(title)]
    if not data:
        rows.append('None')
        return "\n".join(rows)
    for k, v in data.items():
        rows.append(f"{key_label(str(k))}={v}")
    return "\n".join(rows)


def format_case_start(case_name: str, meta: Mapping[str, object]) -> str:
    rows = [lifecycle_title('CASE START'), f"{key_label('case_name')}={case_name}"]
    for k, v in meta.items():
        rows.append(f"{key_label(str(k))}={v}")
    return '\n'.join(rows)


def format_progress(step_idx: int, step_total: int | None, active_values: Mapping[str, object] | None = None) -> str:
    rows = [lifecycle_title('PROGRESS')]
    if step_total:
        progress = ((step_idx + 1) / step_total) * 100.0
        rows.append(f"{key_label('step_idx')}={step_idx + 1}/{step_total}")
        rows.append(f"{key_label('progress')}={progress:.1f}%")
    else:
        rows.append(f"{key_label('step_idx')}={step_idx}")
    return '\n'.join(rows)


def format_case_summary(summary: Mapping[str, object]) -> str:
    return _render_mapping_lines(lifecycle_title, 'CASE SUMMARY', summary)


def format_case_done(case_name: str, status: str, meta: Mapping[str, object]) -> str:
    rows = [lifecycle_title('CASE DONE'), f"{key_label('case_name')}={case_name}", f"{key_label('status')}={color_status_value(status)}"]
    for k, v in meta.items():
        rows.append(f"{key_label(str(k))}={v}")
    return '\n'.join(rows)


def format_case_error(case_name: str, stage: str, exc: Exception, meta: Mapping[str, object] | None = None) -> str:
    rows = [lifecycle_title('CASE ERROR'), f"{key_label('case_name')}={case_name}", f"{key_label('stage')}={stage}", f"{key_label('status')}={color_status_value('FAIL')}", f"{key_label('error_type')}={type(exc).__name__}", f"{key_label('error_message')}={exc}"]
    for k, v in (meta or {}).items():
        rows.append(f"{key_label(str(k))}={v}")
    return '\n'.join(rows)


def format_spi_result(spi_result) -> str:
    info = spi_result.raw_info or {}
    if info and spi_result.action_type == 'field-write-read':
        body = format_field_verify(info)
    else:
        body = (
            f"target={spi_result.target_name} "
            f"{color_write_dec(spi_result.write_value or 0) if spi_result.write_value is not None else 'write_dec=NA'} "
            f"{color_read_dec(spi_result.read_value or 0) if spi_result.read_value is not None else 'read_dec=NA'} "
            f"{color_result(spi_result.verify_result or 'FAIL')}"
        )
    return section_title('SPI RESULT') + "\n" + body


def format_e5052b_summary(result) -> str:
    if result is None:
        return section_title('E5052B SUMMARY') + "\nmeasurement=None"
    summary = result.to_summary_dict()
    order = [
        'output_frequency_hz', 'output_power_dbm', 'jitter_fs', 'rms_rad',
        'integrated_phase_noise_dbc', 'residual_fm_hz',
        'PN_100Hz', 'PN_1kHz', 'PN_10kHz', 'PN_100kHz', 'PN_400kHz', 'PN_1MHz', 'PN_10MHz', 'PN_20MHz', 'PN_40MHz'
    ]
    rows = [section_title('E5052B SUMMARY')]
    for key in order:
        if key in summary:
            rows.append(f"{key_label(key)}={summary[key]}")
    return "\n".join(rows)


def format_output_paths(paths: Mapping[str, str | None]) -> str:
    rows = [section_title('OUTPUT PATHS')]
    for key, value in paths.items():
        rows.append(f"{key_label(str(key))}={muted_path(value)}")
    return "\n".join(rows)


def format_preset_results(results: Iterable[dict]) -> str:
    lines = [section_title('PRESET RESULTS')]
    for info in results:
        lines.append(format_field_verify(info))
    return "\n".join(lines)
