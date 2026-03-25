from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from utils.field_alias import alias_for
from utils.path_helper import create_run_dir, ensure_output_tree
from .client import E5052BClient
from .exporter import export_excel_report, export_trace_csv
from .metrics import compute_integrals, nearest_value, parse_ascii_array, parse_date, parse_time
from .models import E5052BCaptureOptions, E5052BCaptureResult, E5052BKeyPoint


def get_capture_time(client: E5052BClient) -> str:
    date_str = None
    time_str = None
    try:
        date_str = parse_date(client.query_text(':SYST:DATE?'))
    except Exception:
        pass
    try:
        time_str = parse_time(client.query_text(':SYST:TIME?'))
    except Exception:
        pass
    if date_str and time_str:
        return f'{date_str} {time_str}'
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _read_integration_range_if_available(client: E5052BClient, start_hz: Optional[float], stop_hz: Optional[float]) -> tuple[Optional[float], Optional[float]]:
    if start_hz is not None and stop_hz is not None:
        return start_hz, stop_hz
    try:
        bstart = float(client.query_text(':CALC:PN1:TRAC1:BDM:X:STAR?'))
        bstop = float(client.query_text(':CALC:PN1:TRAC1:BDM:X:STOP?'))
        return start_hz if start_hz is not None else bstart, stop_hz if stop_hz is not None else bstop
    except Exception:
        return start_hz, stop_hz


def capture_phase_noise_once(
    client: E5052BClient,
    options: E5052BCaptureOptions,
    out_dir: str | Path | None = None,
    shot_name: Optional[str] = None,
    *,
    case_name: Optional[str] = None,
    step_idx: Optional[int] = None,
    field_names: list[str] | None = None,
    preset_values: dict[str, int] | None = None,
    active_values: dict[str, int] | None = None,
) -> E5052BCaptureResult:
    if options.delay_before_capture_s > 0:
        time.sleep(options.delay_before_capture_s)

    base_path = Path(out_dir or 'outputs/e5052b/capture_once')
    if base_path.name.startswith('run_'):
        tree = ensure_output_tree(base_path)
    else:
        run_dir = create_run_dir(base_path)
        tree = ensure_output_tree(run_dir)

    client.set_ascii_format()
    freeze_ok = False
    if options.freeze_before_capture:
        freeze_ok = client.freeze_display()

    shot_id = datetime.now().strftime('SHOT_%Y%m%d_%H%M%S')
    file_stem = shot_name or shot_id
    capture_time = get_capture_time(client)
    instrument_idn = client.identify()

    carrier_items = parse_ascii_array(client.query_text(':CALC:PN1:DATA:CARR?'))
    if not carrier_items:
        raise RuntimeError('Failed to read carrier information from :CALC:PN1:DATA:CARR?')
    output_frequency_hz = carrier_items[0]
    output_power_dbm = carrier_items[1] if len(carrier_items) >= 2 else None

    offsets_hz = parse_ascii_array(client.query_text(':CALC:PN1:DATA:XDAT?'))
    pn_dbc_hz = parse_ascii_array(client.query_text(':CALC:PN1:TRAC1:DATA:FDAT?'))
    if not offsets_hz or not pn_dbc_hz:
        raise RuntimeError('E5052B returned empty trace data')
    n = min(len(offsets_hz), len(pn_dbc_hz))
    offsets_hz = offsets_hz[:n]
    pn_dbc_hz = pn_dbc_hz[:n]

    screenshot_path = None
    if options.save_screenshot:
        remote_shot = client.request_screenshot_save(shot_id)
        local_path = tree['screenshots'] / f'img_{file_stem}.png'
        screenshot = client.fetch_remote_file(remote_shot, local_path)
        screenshot_path = str(screenshot) if screenshot else None

    if options.resume_after_capture and options.freeze_before_capture:
        client.resume_display()

    integ_start, integ_stop = _read_integration_range_if_available(client, options.integration_start_hz, options.integration_stop_hz)
    if integ_start is None:
        integ_start = offsets_hz[0]
    if integ_stop is None:
        integ_stop = offsets_hz[-1]

    integ_dbc, rms_rad, jitter_s, residual_fm_hz = compute_integrals(offsets_hz, pn_dbc_hz, integ_start, integ_stop, output_frequency_hz)
    jitter_fs = jitter_s * 1e15 if jitter_s is not None else None

    key_points: list[E5052BKeyPoint] = []
    for target in options.key_offsets_hz:
        nearest = nearest_value(offsets_hz, pn_dbc_hz, target)
        if target < 1e3:
            label = f'PN_{int(target):d}Hz'
        elif target < 1e6:
            label = f'PN_{int(target/1e3):d}kHz'
        else:
            label = f'PN_{int(target/1e6):d}MHz'
        if int(target) == 400000:
            label = 'PN_400kHz'
        if nearest is None:
            key_points.append(E5052BKeyPoint(label=label, target_offset_hz=target, actual_offset_hz=None, value_dbc_hz=None))
        else:
            key_points.append(E5052BKeyPoint(label=label, target_offset_hz=target, actual_offset_hz=nearest[0], value_dbc_hz=nearest[1]))

    result = E5052BCaptureResult(
        capture_time=capture_time,
        shot_id=shot_id,
        instrument_idn=instrument_idn,
        output_frequency_hz=output_frequency_hz,
        output_power_dbm=output_power_dbm,
        offsets_hz=offsets_hz,
        phase_noise_dbc_hz=pn_dbc_hz,
        key_points=key_points,
        integral_start_hz=integ_start,
        integral_stop_hz=integ_stop,
        jitter_fs=jitter_fs,
        rms_rad=rms_rad,
        integrated_phase_noise_dbc=integ_dbc,
        residual_fm_hz=residual_fm_hz,
        temperature_c=options.temperature_c if options.temperature_c is not None else 'NA',
        screenshot_path=screenshot_path,
        run_dir=str(tree['run']),
        case_name=case_name,
        step_idx=step_idx,
        field_names=field_names or [],
        field_alias_names=[alias_for(name) for name in (field_names or [])],
        preset_values=preset_values,
        active_values=active_values,
    )

    if options.save_csv:
        csv_path = export_trace_csv(result, tree['traces'] / f'raw_{file_stem}.csv')
        result.raw_csv_path = str(csv_path)

    if options.save_excel:
        xlsx_path = export_excel_report(result, tree['summary'] / f'pn_{file_stem}.xlsx')
        result.excel_path = str(xlsx_path)

    if not options.resume_after_capture and options.freeze_before_capture and freeze_ok:
        pass

    return result
