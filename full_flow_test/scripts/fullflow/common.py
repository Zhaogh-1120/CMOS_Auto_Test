from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.formatter import (
    format_case_done,
    format_case_error,
    format_case_start,
    format_case_summary,
    format_debug_info,
    format_e5052b_summary,
    format_flow_header,
    format_mapping_section,
    format_output_paths,
    format_preset_results,
    format_progress,
    format_spi_result,
    print_block,
)
from core.measurement_hook import FlowOptions
from core.result_model import FullFlowRecord
from instruments.e5052b.client import E5052BClient
from instruments.e5052b.models import E5052BCaptureOptions
from utils.runtime_policy import build_runtime_policy

DEFAULT_KEY_OFFSETS = [100.0, 1e3, 1e4, 1e5, 4e5, 1e6, 1e7, 2e7, 4e7]


def build_capture_options(cfg: dict[str, Any], *, save_screenshot: bool | None = None) -> E5052BCaptureOptions:
    return E5052BCaptureOptions(
        save_screenshot=cfg.get('save_screenshot', True) if save_screenshot is None else save_screenshot,
        save_csv=cfg.get('save_csv', True),
        save_excel=cfg.get('save_excel', True),
        delay_before_capture_s=cfg.get('delay_before_capture_s', 0.0),
        freeze_before_capture=cfg.get('freeze_before_capture', True),
        resume_after_capture=cfg.get('resume_after_capture', True),
        key_offsets_hz=tuple(cfg.get('key_offsets_hz', DEFAULT_KEY_OFFSETS)),
    )


def make_client_from_config(cfg: dict[str, Any]) -> E5052BClient:
    return E5052BClient(cfg['host'], cfg.get('port', 5025), cfg.get('timeout_s', 15.0))


def now_str() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def build_case_policy(case_overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return build_runtime_policy(case_overrides)


def print_instrument_debug(cfg: Mapping[str, Any], client: E5052BClient, enabled: bool = False) -> None:
    if not enabled:
        return
    instrument_id = ''
    try:
        instrument_id = client.identify()
    except Exception as exc:
        instrument_id = f'<identify failed: {exc}>'
    data = {
        'instrument_name': instrument_id,
        'host': cfg.get('host'),
        'port': cfg.get('port', 5025),
        'timeout_s': cfg.get('timeout_s', 15.0),
    }
    print_block(format_debug_info('INSTRUMENT INFO', data))


def print_case_start(case_name: str, *, case_desc: str = '', debug: bool = False, continue_on_error: bool = False) -> None:
    meta = {'start_time': now_str()}
    if case_desc:
        meta['case_desc'] = case_desc
    print_block(format_case_start(case_name, meta))




def print_debug_info(title: str, data: Mapping[str, object], enabled: bool = False) -> None:
    if not enabled:
        return
    print_block(format_debug_info(title, data))

def print_flow_config(case_name: str, flow_options: FlowOptions) -> None:
    print_block(format_flow_header(case_name, {
        'enable_measurement': flow_options.enable_measurement,
        'save_screenshot': flow_options.save_screenshot,
        'save_csv': flow_options.save_csv,
        'save_excel': flow_options.save_excel,
        'delay_before_measurement_s': flow_options.delay_before_measurement_s,
        'output_dir': flow_options.output_dir,
    }))


def print_progress(step_idx: int, step_total: int | None = None, active_values: Mapping[str, object] | None = None) -> None:
    print_block(format_progress(step_idx, step_total, None))


def print_record(record) -> None:
    print_block(format_spi_result(record.spi_result))
    if record.measurement_result is not None:
        print_block(format_e5052b_summary(record.measurement_result))
        print_block(format_output_paths({
            'run_dir': record.measurement_result.run_dir,
            'screenshot_path': record.measurement_result.screenshot_path,
            'raw_csv_path': record.measurement_result.raw_csv_path,
            'excel_path': record.measurement_result.excel_path,
            'merged_summary_path': record.measurement_result.merged_summary_path,
        }))


def print_presets(results: list[dict]) -> None:
    if results:
        print_block(format_preset_results(results))


def print_case_error(case_name: str, stage: str, exc: Exception, *, step_idx: int | None = None, active_values: Mapping[str, object] | None = None) -> None:
    meta = {}
    if step_idx is not None:
        meta['step_idx'] = step_idx
    if active_values:
        meta['active_values'] = ', '.join(f'{k}={v}' for k, v in active_values.items())
    print_block(format_case_error(case_name, stage, exc, meta))


def summarize_records(records: Iterable[FullFlowRecord]) -> dict[str, object]:
    records = list(records)
    total = len(records)
    pass_steps = sum(1 for r in records if r.overall_status == 'PASS')
    fail_steps = total - pass_steps
    measurement_steps = sum(1 for r in records if r.measurement_result is not None)
    return {
        'total_steps': total,
        'pass_steps': pass_steps,
        'fail_steps': fail_steps,
        'measurement_steps': measurement_steps,
    }


def print_case_summary(records: Iterable[FullFlowRecord]) -> None:
    return None


def print_case_done(case_name: str, *, status: str = 'PASS', run_dir: str | None = None, merged_summary_path: str | None = None, elapsed_s: float | None = None) -> None:
    meta = {}
    if elapsed_s is not None:
        meta['elapsed_s'] = round(elapsed_s, 3)
    if run_dir is not None:
        meta['run_dir'] = run_dir
    if merged_summary_path is not None:
        meta['merged_summary_path'] = merged_summary_path
    print_block(format_case_done(case_name, status, meta))


def write_run_meta(run_dir: str | Path, meta: Mapping[str, Any]) -> Path:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / 'run_meta.json'
    serializable = {}
    for k, v in meta.items():
        if isinstance(v, Path):
            serializable[k] = str(v)
        else:
            serializable[k] = v
    path.write_text(json.dumps(serializable, indent=2, ensure_ascii=False), encoding='utf-8')
    return path


def register_error_record(hook, records: list[FullFlowRecord], *, target_name: str, write_value: int | None = None, case_name: str = '', preset_values: dict | None = None, active_values: dict | None = None, step_idx: int | None = None, stage: str = '', exc: Exception | None = None):
    record = FullFlowRecord.from_error(
        target_name=target_name,
        write_value=write_value,
        case_name=case_name,
        preset_values=preset_values,
        active_values=active_values,
        step_idx=step_idx,
        error_stage=stage,
        exc=exc,
    )
    if hook is not None:
        hook.register_error_record(record)
    else:
        records.append(record)
    return record
