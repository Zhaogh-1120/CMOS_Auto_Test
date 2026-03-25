from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from instruments.e5052b.models import E5052BCaptureResult


@dataclass
class VerifyResult:
    name: str
    write_value: int
    read_value: int
    result: str


@dataclass
class SPIActionResult:
    action_type: str
    target_name: str
    target_address_hex: Optional[str]
    write_value: Optional[int]
    read_value: Optional[int]
    verify_result: Optional[str]
    before_reg_hex: Optional[str] = None
    after_reg_hex: Optional[str] = None
    raw_info: Optional[dict[str, Any]] = None
    spi_attempt_count: int = 1
    spi_recovered: bool = False
    session_lost: bool = False
    spi_status_detail: str = ''

    @classmethod
    def from_field_info(cls, info: dict[str, Any]) -> 'SPIActionResult':
        return cls(
            action_type='field-write-read',
            target_name=info.get('field_name', ''),
            target_address_hex=info.get('address_hex'),
            write_value=info.get('write_field_decimal'),
            read_value=info.get('read_field_decimal'),
            verify_result=info.get('verify_result'),
            before_reg_hex=info.get('before_reg_hex'),
            after_reg_hex=info.get('after_reg_hex'),
            raw_info=info,
            spi_attempt_count=int(info.get('spi_attempt_count', 1) or 1),
            spi_recovered=bool(info.get('spi_recovered', False)),
            session_lost=bool(info.get('session_lost', False)),
            spi_status_detail=info.get('spi_status_detail', ''),
        )


def _resolve_overall_status(spi_verify_result: str | None, measurement_status: str, export_status: str) -> str:
    if spi_verify_result not in (None, 'PASS'):
        return 'FAIL'
    if measurement_status in ('FAIL', 'TIMEOUT', 'ERROR'):
        return 'FAIL'
    if export_status in ('FAIL', 'ERROR'):
        return 'FAIL'
    return 'PASS'


@dataclass
class FullFlowRecord:
    spi_result: SPIActionResult
    measurement_result: Optional[E5052BCaptureResult] = None
    note: str = ''
    case_name: str = ''
    preset_values: Optional[dict[str, int]] = None
    active_values: Optional[dict[str, int]] = None
    step_idx: Optional[int] = None
    measurement_status: str = 'SKIP'
    export_status: str = 'SKIP'
    overall_status: str = 'PASS'
    error_stage: str = ''
    error_type: str = ''
    error_message: str = ''

    @classmethod
    def from_error(
        cls,
        *,
        target_name: str,
        write_value: int | None = None,
        case_name: str = '',
        preset_values: dict | None = None,
        active_values: dict | None = None,
        step_idx: int | None = None,
        error_stage: str = '',
        exc: Exception | None = None,
        note: str = '',
    ) -> 'FullFlowRecord':
        spi_result = SPIActionResult(
            action_type='field-write-read',
            target_name=target_name,
            target_address_hex=None,
            write_value=write_value,
            read_value=None,
            verify_result='FAIL',
        )
        return cls(
            spi_result=spi_result,
            case_name=case_name,
            preset_values=preset_values,
            active_values=active_values,
            step_idx=step_idx,
            note=note,
            measurement_status='ERROR' if error_stage.startswith('MEAS') else 'SKIP',
            export_status='ERROR' if error_stage.startswith('EXPORT') else 'SKIP',
            overall_status='FAIL',
            error_stage=error_stage,
            error_type=type(exc).__name__ if exc else '',
            error_message=str(exc) if exc else '',
        )

    def finalize_statuses(self) -> None:
        self.overall_status = _resolve_overall_status(
            self.spi_result.verify_result, self.measurement_status, self.export_status
        )

    def to_summary_dict(self) -> dict[str, Any]:
        self.finalize_statuses()
        data = {
            'case_name': self.case_name,
            'step_idx': self.step_idx,
            'spi_action_type': self.spi_result.action_type,
            'spi_target_name': self.spi_result.target_name,
            'spi_target_address_hex': self.spi_result.target_address_hex,
            'spi_write_value': self.spi_result.write_value,
            'spi_read_value': self.spi_result.read_value,
            'spi_verify_result': self.spi_result.verify_result,
            'spi_before_reg_hex': self.spi_result.before_reg_hex,
            'spi_after_reg_hex': self.spi_result.after_reg_hex,
            'spi_attempt_count': self.spi_result.spi_attempt_count,
            'spi_recovered': self.spi_result.spi_recovered,
            'session_lost': self.spi_result.session_lost,
            'spi_status_detail': self.spi_result.spi_status_detail,
            'note': self.note,
            'preset_values': self.preset_values or {},
            'active_values': self.active_values or {},
            'measurement_status': self.measurement_status,
            'export_status': self.export_status,
            'overall_status': self.overall_status,
            'error_stage': self.error_stage,
            'error_type': self.error_type,
            'error_message': self.error_message,
        }
        if self.measurement_result is not None:
            data.update({f'e5052b_{k}': v for k, v in self.measurement_result.to_summary_dict().items()})
        return data
