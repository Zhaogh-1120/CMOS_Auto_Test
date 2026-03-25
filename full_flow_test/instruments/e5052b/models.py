from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class E5052BKeyPoint:
    label: str
    target_offset_hz: float
    actual_offset_hz: Optional[float]
    value_dbc_hz: Optional[float]


@dataclass
class E5052BCaptureOptions:
    save_screenshot: bool = True
    save_csv: bool = True
    save_excel: bool = True
    freeze_before_capture: bool = True
    resume_after_capture: bool = True
    delay_before_capture_s: float = 0.0
    integration_start_hz: Optional[float] = None
    integration_stop_hz: Optional[float] = None
    temperature_c: Optional[float] = None
    shot_name: Optional[str] = None
    key_offsets_hz: tuple[float, ...] = (100.0, 1e3, 1e4, 1e5, 4e5, 1e6, 1e7, 2e7, 4e7)


@dataclass
class E5052BCaptureResult:
    capture_time: str
    shot_id: str
    instrument_idn: str
    output_frequency_hz: float
    output_power_dbm: Optional[float]
    offsets_hz: list[float]
    phase_noise_dbc_hz: list[float]
    key_points: list[E5052BKeyPoint] = field(default_factory=list)
    integral_start_hz: Optional[float] = None
    integral_stop_hz: Optional[float] = None
    jitter_fs: Optional[float] = None
    rms_rad: Optional[float] = None
    integrated_phase_noise_dbc: Optional[float] = None
    residual_fm_hz: Optional[float] = None
    temperature_c: Optional[float | str] = None
    screenshot_path: Optional[str] = None
    raw_csv_path: Optional[str] = None
    excel_path: Optional[str] = None
    merged_summary_path: Optional[str] = None
    run_dir: Optional[str] = None
    case_name: Optional[str] = None
    step_idx: Optional[int] = None
    field_names: list[str] = field(default_factory=list)
    field_alias_names: list[str] = field(default_factory=list)
    preset_values: Optional[dict[str, int]] = None
    active_values: Optional[dict[str, int]] = None

    def key_point_dict(self) -> dict[str, Optional[float]]:
        return {item.label: item.value_dbc_hz for item in self.key_points}

    def to_summary_dict(self) -> dict:
        data = {
            'capture_time': self.capture_time,
            'shot_id': self.shot_id,
            'instrument_idn': self.instrument_idn,
            'case_name': self.case_name,
            'step_idx': self.step_idx,
            'field_names': json.dumps(self.field_names, ensure_ascii=False) if self.field_names else '',
            'field_alias_names': json.dumps(self.field_alias_names, ensure_ascii=False) if self.field_alias_names else '',
            'preset_values': self.preset_values or {},
            'active_values': self.active_values or {},
            'output_frequency_hz': self.output_frequency_hz,
            'output_power_dbm': self.output_power_dbm,
            'integral_start_hz': self.integral_start_hz,
            'integral_stop_hz': self.integral_stop_hz,
            'jitter_fs': self.jitter_fs,
            'rms_rad': self.rms_rad,
            'integrated_phase_noise_dbc': self.integrated_phase_noise_dbc,
            'residual_fm_hz': self.residual_fm_hz,
            'temperature_c': self.temperature_c,
            'screenshot_path': self.screenshot_path,
            'raw_csv_path': self.raw_csv_path,
            'excel_path': self.excel_path,
            'merged_summary_path': self.merged_summary_path,
            'run_dir': self.run_dir,
        }
        data.update(self.key_point_dict())
        return data
