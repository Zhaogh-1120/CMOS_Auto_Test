from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Optional, Sequence

import xlsxwriter

from .metrics import choose_x_axis_range, choose_y_axis_range
from .models import E5052BCaptureResult


def export_trace_csv(result: E5052BCaptureResult, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['offset_hz', 'phase_noise_dbc_hz'])
        for x, y in zip(result.offsets_hz, result.phase_noise_dbc_hz):
            w.writerow([x, y])
    return path


def _formats(workbook):
    return {
        'header': workbook.add_format({'font_name': 'DengXian', 'font_size': 10, 'bold': True, 'font_color': 'white', 'bg_color': '#1F4E78', 'border': 1, 'align': 'center', 'valign': 'vcenter'}),
        'cell': workbook.add_format({'font_name': 'DengXian', 'font_size': 10, 'border': 1, 'align': 'center', 'valign': 'vcenter'}),
        'frequency_mhz': workbook.add_format({'font_name': 'DengXian', 'font_size': 10, 'border': 1, 'align': 'center', 'valign': 'vcenter', 'num_format': '0.000000'}),
        'cell_num': workbook.add_format({'font_name': 'DengXian', 'font_size': 10, 'border': 1, 'align': 'center', 'valign': 'vcenter', 'num_format': '0.000000'}),
        'note_hdr': workbook.add_format({'font_name': 'DengXian', 'font_size': 10, 'bold': True, 'bg_color': '#D9EAF7', 'border': 1}),
        'note': workbook.add_format({'font_name': 'DengXian', 'font_size': 10, 'bg_color': '#FCE4D6', 'border': 1, 'text_wrap': True}),
        'subhdr': workbook.add_format({'font_name': 'DengXian', 'font_size': 10, 'bold': True, 'bg_color': '#D9EAF7', 'border': 1, 'align': 'center', 'valign': 'vcenter'}),
        'title': workbook.add_format({'font_name': 'DengXian', 'font_size': 20, 'bold': True, 'font_color': 'white', 'bg_color': '#1F4E78', 'border': 1, 'align': 'center', 'valign': 'vcenter'}),
        'path': workbook.add_format({'font_name': 'DengXian', 'font_size': 12, 'bg_color': '#D9EAF7', 'border': 1, 'align': 'center', 'valign': 'vcenter'}),
        'box': workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter'}),
    }


def _write_context_block(ws, fmt, result: E5052BCaptureResult, start_row: int = 4):
    context_headers = ['case_name', 'step_idx', 'field_names', 'field_alias_names', 'active_values', 'preset_values']
    context_values = [
        result.case_name,
        result.step_idx,
        json.dumps(result.field_names, ensure_ascii=False) if result.field_names else '',
        json.dumps(result.field_alias_names, ensure_ascii=False) if result.field_alias_names else '',
        json.dumps(result.active_values, ensure_ascii=False) if result.active_values else '',
        json.dumps(result.preset_values, ensure_ascii=False) if result.preset_values else '',
    ]
    for c, h in enumerate(context_headers):
        ws.write(start_row, c, h, fmt['header'])
        ws.write(start_row + 1, c, context_values[c], fmt['cell'])
    ws.set_row(start_row, 22)
    ws.set_row(start_row + 1, 28)


def _write_summary_sheet(workbook, result: E5052BCaptureResult):
    ws = workbook.add_worksheet('Summary')
    ws.hide_gridlines(2)
    fmt = _formats(workbook)

    summary = result.to_summary_dict()
    headers = [
        'capture_time', 'shot_id', 'temperature_c', 'output_frequency_mhz', 'output_power_dbm',
        'PN_100Hz', 'PN_1kHz', 'PN_10kHz', 'PN_100kHz', 'PN_400kHz', 'PN_1MHz', 'PN_10MHz', 'PN_20MHz', 'PN_40MHz',
        'integral_start_hz', 'integral_stop_hz', 'jitter_fs', 'rms_rad', 'integrated_phase_noise_dbc', 'residual_fm_hz',
        'screenshot_path', 'instrument_idn'
    ]
    values = []
    for h in headers:
        if h == 'output_frequency_mhz':
            hz = summary.get('output_frequency_hz')
            values.append(hz / 1e6 if hz is not None else None)
        else:
            values.append(summary.get(h))
    for c, h in enumerate(headers):
        ws.write(0, c, h, fmt['header'])
    for c, v in enumerate(values):
        ws.write(1, c, v, fmt['frequency_mhz'] if headers[c] == 'output_frequency_mhz' else fmt['cell'])
    ws.set_row(0, 22)
    ws.set_row(1, 22)
    ws.freeze_panes(1, 0)
    ws.set_column(0, len(headers) - 1, 16)

    _write_context_block(ws, fmt, result, start_row=4)

    ws.write(7, 0, 'Notes', fmt['note_hdr'])
    ws.merge_range(8, 0, 8, 11, 'Temperature writes NA if omitted. 图使用完整抓取 trace 作图。左下角表格保留重点频点 PN 数据。', fmt['note'])

    table_row0 = 10
    ws.merge_range(table_row0, 0, table_row0, 2, 'Key Phase-Noise Points', fmt['header'])
    ws.write(table_row0 + 1, 0, 'Point', fmt['subhdr'])
    ws.write(table_row0 + 1, 1, 'Offset_Hz', fmt['subhdr'])
    ws.write(table_row0 + 1, 2, 'PN_dBc_Hz', fmt['subhdr'])
    for r, kp in enumerate(result.key_points, start=table_row0 + 2):
        ws.write(r, 0, kp.label, fmt['cell'])
        ws.write_number(r, 1, kp.target_offset_hz, fmt['cell'])
        if kp.value_dbc_hz is None:
            ws.write_blank(r, 2, None, fmt['cell'])
        else:
            ws.write_number(r, 2, kp.value_dbc_hz, fmt['cell'])

    ws.set_column(0, 0, 16)
    ws.set_column(1, 2, 18)

    chart_col_x, chart_col_y = 24, 25
    ws.write(10, chart_col_x, 'offset_hz', fmt['header'])
    ws.write(10, chart_col_y, 'phase_noise_dBc_Hz', fmt['header'])
    for i, (xv, yv) in enumerate(zip(result.offsets_hz, result.phase_noise_dbc_hz), start=11):
        ws.write_number(i, chart_col_x, xv, fmt['cell_num'])
        ws.write_number(i, chart_col_y, yv, fmt['cell_num'])

    x_min, x_max = choose_x_axis_range(result.offsets_hz)
    y_min, y_max = choose_y_axis_range(result.phase_noise_dbc_hz)

    chart = workbook.add_chart({'type': 'scatter', 'subtype': 'straight'})
    chart.add_series({
        'name': 'Phase Noise',
        'categories': ['Summary', 11, chart_col_x, 10 + len(result.offsets_hz), chart_col_x],
        'values': ['Summary', 11, chart_col_y, 10 + len(result.phase_noise_dbc_hz), chart_col_y],
        'line': {'color': '#4472C4', 'width': 1.75},
        'marker': {'type': 'none'},
    })
    chart.set_title({'name': 'Phase Noise vs Offset Frequency', 'name_font': {'name': 'DengXian', 'bold': True, 'size': 13}})
    chart.set_x_axis({
        'name': 'Offset Frequency (Hz)',
        'name_font': {'name': 'DengXian', 'bold': True, 'size': 11},
        'num_font': {'name': 'DengXian', 'size': 10},
        'log_base': 10,
        'min': x_min,
        'max': x_max,
        'major_tick_mark': 'inside',
        'minor_tick_mark': 'inside',
        'line': {'color': 'black', 'width': 1.0},
    })
    chart.set_y_axis({
        'name': 'Phase Noise (dBc/Hz)',
        'name_font': {'name': 'DengXian', 'bold': True, 'size': 11},
        'num_font': {'name': 'DengXian', 'size': 10},
        'min': y_min,
        'max': y_max,
        'major_tick_mark': 'inside',
        'minor_tick_mark': 'inside',
        'line': {'color': 'black', 'width': 1.0},
    })
    chart.set_legend({'none': True})
    chart.set_chartarea({'border': {'none': False, 'color': '#7F7F7F'}})
    chart.set_plotarea({'border': {'none': False, 'color': '#BFBFBF'}})
    ws.insert_chart('E11', chart, {'x_scale': 1.35, 'y_scale': 1.40})


def _write_rawtrace_sheet(workbook, offsets_hz: Sequence[float], pn_dbc_hz: Sequence[float]):
    ws = workbook.add_worksheet('RawTrace')
    ws.hide_gridlines(2)
    fmt = _formats(workbook)
    ws.write(0, 0, 'offset_hz', fmt['header'])
    ws.write(0, 1, 'phase_noise_dbc_hz', fmt['header'])
    for i, (x, y) in enumerate(zip(offsets_hz, pn_dbc_hz), start=1):
        ws.write_number(i, 0, x, fmt['cell_num'])
        ws.write_number(i, 1, y, fmt['cell_num'])
    ws.freeze_panes(1, 0)
    ws.set_column(0, 1, 18)


def _write_screenshot_sheet(workbook, screenshot_path: Optional[Path], shot_id: str):
    ws = workbook.add_worksheet('Screenshot')
    ws.hide_gridlines(2)
    fmt = _formats(workbook)
    for col in range(14):
        ws.set_column(col, col, 12.0)
    ws.merge_range(0, 0, 0, 13, f'Instrument Screenshot {shot_id}', fmt['title'])
    ws.merge_range(1, 0, 1, 13, str(screenshot_path) if screenshot_path else 'Capture failed / no screenshot saved', fmt['path'])
    ws.merge_range(4, 0, 41, 13, '', fmt['box'])
    if screenshot_path and screenshot_path.exists():
        options = {'object_position': 2}
        try:
            from PIL import Image as PILImage
            with PILImage.open(screenshot_path) as img:
                w_px, _ = img.size
            target_width_px = 14 * 84
            scale = min(1.0, target_width_px / max(1, w_px))
            options['x_scale'] = scale
            options['y_scale'] = scale
        except Exception:
            pass
        ws.insert_image(4, 0, str(screenshot_path), options)


def export_excel_report(result: E5052BCaptureResult, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(str(path))
    try:
        _write_summary_sheet(workbook, result)
        _write_rawtrace_sheet(workbook, result.offsets_hz, result.phase_noise_dbc_hz)
        screenshot = Path(result.screenshot_path) if result.screenshot_path else None
        _write_screenshot_sheet(workbook, screenshot, result.shot_id)
    finally:
        workbook.close()
    return path


def _parse_mapping(value):
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _flatten_config_columns(records: Sequence[dict]) -> tuple[list[str], list[dict]]:
    config_keys: list[str] = []
    normalized: list[dict] = []
    for rec in records:
        preset = _parse_mapping(rec.get('preset_values'))
        active = _parse_mapping(rec.get('active_values'))
        combined = {}
        combined.update(preset)
        combined.update(active)
        for k in combined.keys():
            if k not in config_keys:
                config_keys.append(k)
        normalized.append(combined)
    return config_keys, normalized


def export_merged_summary(records: Sequence[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(str(path))
    try:
        ws = workbook.add_worksheet('MergedSummary')
        ws.hide_gridlines(2)
        fmt = _formats(workbook)

        base_headers = []
        for rec in records:
            for k in rec.keys():
                if k not in base_headers:
                    base_headers.append(k)

        # Replace frequency column header to MHz for Excel exports only.
        if 'e5052b_output_frequency_hz' in base_headers:
            idx = base_headers.index('e5052b_output_frequency_hz')
            base_headers[idx] = 'e5052b_output_frequency_mhz'
        elif 'output_frequency_hz' in base_headers:
            idx = base_headers.index('output_frequency_hz')
            base_headers[idx] = 'output_frequency_mhz'

        config_keys, normalized_cfgs = _flatten_config_columns(records)

        insert_after = 'active_values' if 'active_values' in base_headers else ('preset_values' if 'preset_values' in base_headers else None)
        if insert_after and insert_after in base_headers:
            at = base_headers.index(insert_after) + 1
            headers = base_headers[:at] + config_keys + base_headers[at:]
        else:
            headers = base_headers + config_keys

        seen = set()
        dedup_headers = []
        for h in headers:
            if h not in seen:
                seen.add(h)
                dedup_headers.append(h)
        headers = dedup_headers

        for c, h in enumerate(headers):
            ws.write(0, c, h, fmt['header'])

        for r, rec in enumerate(records, start=1):
            cfg_map = normalized_cfgs[r-1]
            for c, h in enumerate(headers):
                if h in cfg_map:
                    value = cfg_map.get(h)
                elif h == 'e5052b_output_frequency_mhz':
                    hz = rec.get('e5052b_output_frequency_hz')
                    value = hz / 1e6 if isinstance(hz, (int, float)) else hz
                elif h == 'output_frequency_mhz':
                    hz = rec.get('output_frequency_hz')
                    value = hz / 1e6 if isinstance(hz, (int, float)) else hz
                else:
                    value = rec.get(h)
                if isinstance(value, (dict, list, tuple)):
                    value = json.dumps(value, ensure_ascii=False)
                ws.write(r, c, value, fmt['frequency_mhz'] if h in ('e5052b_output_frequency_mhz', 'output_frequency_mhz') else fmt['cell'])

        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, len(records), len(headers) - 1)
        ws.set_column(0, len(headers) - 1, 18)
    finally:
        workbook.close()
    return path
