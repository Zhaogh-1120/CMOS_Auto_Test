from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from core.result_model import FullFlowRecord, SPIActionResult
from instruments.e5052b.capture import capture_phase_noise_once
from instruments.e5052b.client import E5052BClient
from instruments.e5052b.models import E5052BCaptureOptions
from instruments.e5052b.exporter import export_merged_summary
from utils.field_alias import alias_for
from utils.path_helper import create_run_dir, ensure_output_tree


class MeasurementHook:
    def before_spi_action(self, context: dict | None = None):
        return None

    def after_spi_action(
        self,
        spi_result: SPIActionResult,
        *,
        case_name: str = '',
        preset_values: dict | None = None,
        active_values: dict | None = None,
        step_idx: int | None = None,
    ):
        return None

    def on_error(self, exc: Exception, context: dict | None = None):
        return None


@dataclass
class FlowOptions:
    verify_spi: bool = True
    enable_measurement: bool = False
    delay_before_measurement_s: float = 0.0
    save_screenshot: bool = True
    save_csv: bool = True
    save_excel: bool = True
    stop_on_spi_fail: bool = True
    measure_on_spi_fail: bool = False
    output_dir: str = 'outputs/fullflow'
    case_name: str = 'case'
    case_desc: str = ''
    debug: bool = False
    continue_on_error: bool = False


class E5052BMeasurementHook(MeasurementHook):
    def __init__(self, client: E5052BClient, capture_options: E5052BCaptureOptions, flow_options: Optional[FlowOptions] = None):
        self.client = client
        self.capture_options = capture_options
        self.flow_options = flow_options or FlowOptions(enable_measurement=True)
        self.records: list[FullFlowRecord] = []
        self.run_dir = create_run_dir(self.flow_options.output_dir)
        self.output_tree = ensure_output_tree(self.run_dir)
        self.merged_summary_path: Optional[str] = None
        self._next_step_idx = 0

    def _should_measure(self, spi_result: SPIActionResult) -> bool:
        if not self.flow_options.enable_measurement:
            return False
        if spi_result.verify_result == 'PASS':
            return True
        if spi_result.verify_result != 'PASS' and self.flow_options.measure_on_spi_fail:
            return True
        return False

    def _resolve_step_idx(self, step_idx: int | None) -> int:
        if step_idx is None:
            step_idx = self._next_step_idx
        self._next_step_idx = max(self._next_step_idx, step_idx + 1)
        return step_idx

    def _build_basename(self, spi_result: SPIActionResult, active_values: dict | None, step_idx: int) -> str:
        step_tag = f'step{step_idx:03d}'
        if active_values:
            keys = list(active_values.keys())
            vals = list(active_values.values())
            if len(keys) == 1:
                return f"{keys[0]}_{step_tag}_val{vals[0]}"
            alias_names = [alias_for(k) for k in keys[:3]]
            alias_tag = '__'.join(alias_names)
            value_tag = '-'.join(str(v) for v in vals[:3])
            if len(keys) > 3:
                alias_tag += '__etc'
                if len(vals) > 3:
                    value_tag += '-' + '-'.join(str(v) for v in vals[3:])
            return f"{alias_tag}_{step_tag}_val{value_tag}"
        value = 'NA' if spi_result.write_value is None else str(spi_result.write_value)
        return f"{spi_result.target_name}_{step_tag}_val{value}"

    def register_error_record(self, record: FullFlowRecord) -> None:
        self.records.append(record)

    def after_spi_action(
        self,
        spi_result: SPIActionResult,
        *,
        case_name: str = '',
        preset_values: dict | None = None,
        active_values: dict | None = None,
        step_idx: int | None = None,
    ):
        real_step_idx = self._resolve_step_idx(step_idx)
        record = FullFlowRecord(
            spi_result=spi_result,
            case_name=case_name or self.flow_options.case_name,
            preset_values=preset_values,
            active_values=active_values,
            step_idx=real_step_idx,
            measurement_status='SKIP' if not self.flow_options.enable_measurement else 'PENDING',
            export_status='PENDING' if self.flow_options.enable_measurement else 'SKIP',
        )
        if not self._should_measure(spi_result):
            record.measurement_status = 'SKIP'
            record.export_status = 'SKIP'
            record.finalize_statuses()
            self.records.append(record)
            return record
        if spi_result.verify_result != 'PASS' and self.flow_options.stop_on_spi_fail and not self.flow_options.measure_on_spi_fail:
            record.measurement_status = 'SKIP'
            record.export_status = 'SKIP'
            record.finalize_statuses()
            self.records.append(record)
            return record

        if self.flow_options.delay_before_measurement_s > 0:
            time.sleep(self.flow_options.delay_before_measurement_s)

        self.capture_options.save_screenshot = self.flow_options.save_screenshot
        self.capture_options.save_csv = self.flow_options.save_csv
        self.capture_options.save_excel = self.flow_options.save_excel

        result = capture_phase_noise_once(
            client=self.client,
            options=self.capture_options,
            out_dir=self.run_dir,
            shot_name=self._build_basename(spi_result, active_values, real_step_idx),
            case_name=record.case_name,
            step_idx=real_step_idx,
            field_names=list((active_values or {spi_result.target_name: spi_result.write_value}).keys()),
            preset_values=preset_values,
            active_values=active_values,
        )
        result.merged_summary_path = self.merged_summary_path
        record.measurement_result = result
        record.measurement_status = 'PASS'
        record.export_status = 'PENDING'
        record.finalize_statuses()
        self.records.append(record)
        return record

    def export_merged_summary(self, filename: str = 'merged_summary.xlsx') -> Optional[str]:
        if not self.records:
            return None
        path = self.output_tree['merged'] / filename
        export_merged_summary([r.to_summary_dict() for r in self.records], path)
        self.merged_summary_path = str(path)
        for rec in self.records:
            rec.export_status = 'PASS'
            rec.finalize_statuses()
            if rec.measurement_result is not None:
                rec.measurement_result.merged_summary_path = self.merged_summary_path
        return self.merged_summary_path
