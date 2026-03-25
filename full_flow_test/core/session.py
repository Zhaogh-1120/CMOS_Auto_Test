from __future__ import annotations

import time
from typing import Optional

from core.measurement_hook import MeasurementHook
from core.result_model import FullFlowRecord, SPIActionResult
from protocol.chip_spi import ChipSpi
from driver.control_spi import GinkgoSPIError


def _is_session_lost_exception(exc: Exception) -> bool:
    msg = str(exc).lower()
    keywords = [
        'no ginkgo spi device found',
        'open device failed',
        'init spi failed',
        'spi write failed',
        'vsi_writereadbytes failed',
        'device',
        'handle',
        'usb',
    ]
    return isinstance(exc, GinkgoSPIError) and any(k in msg for k in keywords)


class TestSession:
    def __init__(self, chip: ChipSpi, measurement_hook: Optional[MeasurementHook] = None, runtime_policy: Optional[dict] = None):
        self.chip = chip
        self.measurement_hook = measurement_hook
        self.runtime_policy = runtime_policy or {}
        self._consecutive_spi_fails = 0
        self._spi_session_lost = False

    def _p(self, key: str, default=None):
        return self.runtime_policy.get(key, default)

    def run_field_write_read(
        self,
        name: str,
        value: int,
        use_shadow: bool = False,
        *,
        case_name: str = '',
        preset_values: dict | None = None,
        active_values: dict | None = None,
        step_idx: int | None = None,
    ) -> FullFlowRecord:
        if self._spi_session_lost and self._p('CONTINUE_ON_DEVICE_LOSS', False):
            spi_result = SPIActionResult(
                action_type='field-write-read',
                target_name=name,
                target_address_hex=None,
                write_value=value,
                read_value=None,
                verify_result='FAIL',
                spi_attempt_count=0,
                spi_recovered=False,
                session_lost=True,
                spi_status_detail='SESSION_LOST',
            )
            rec = FullFlowRecord(
                spi_result=spi_result,
                case_name=case_name,
                preset_values=preset_values,
                active_values=active_values,
                step_idx=step_idx,
                measurement_status='SKIP',
                export_status='SKIP',
                overall_status='FAIL',
                error_stage='SPI_SESSION_LOST',
                error_type='SessionLost',
                error_message='SPI session already marked as lost; hardware access skipped',
            )
            return rec

        retry_enabled = bool(self._p('SPI_RETRY_ON_FAIL', False))
        retry_count = int(self._p('SPI_RETRY_COUNT', 1) or 1) if retry_enabled else 1
        retry_delay = float(self._p('SPI_RETRY_DELAY_S', 0.05) or 0.0)
        strict_link = bool(self._p('STRICT_SPI_LINK_CHECK', False))
        max_consecutive = int(self._p('MAX_CONSECUTIVE_SPI_FAILS', 3) or 3)
        raise_on_verify_fail = bool(self._p('RAISE_ON_SPI_VERIFY_FAIL', False))

        last_exc = None
        last_info = None
        for attempt in range(1, retry_count + 1):
            try:
                info = self.chip.write_field_then_read(name, value, use_shadow=use_shadow)
                info['spi_attempt_count'] = attempt
                if info.get('verify_result') == 'PASS':
                    info['spi_recovered'] = attempt > 1
                    info['session_lost'] = False
                    info['spi_status_detail'] = 'RECOVERED_PASS' if attempt > 1 else 'PASS'
                    self._consecutive_spi_fails = 0
                    last_info = info
                    break
                # verify fail
                self._consecutive_spi_fails += 1
                info['spi_recovered'] = False
                info['session_lost'] = False
                info['spi_status_detail'] = 'VERIFY_FAIL'
                last_info = info
                if attempt < retry_count:
                    time.sleep(retry_delay)
                    continue
                if raise_on_verify_fail:
                    raise RuntimeError(f"SPI verify failed for {name}, value={value}, read={info.get('read_field_decimal')}")
                if strict_link and self._consecutive_spi_fails >= max_consecutive:
                    info['spi_status_detail'] = 'LINK_UNSTABLE'
                break
            except Exception as exc:
                last_exc = exc
                if attempt < retry_count:
                    time.sleep(retry_delay)
                    continue
                session_lost = _is_session_lost_exception(exc)
                if session_lost:
                    self._spi_session_lost = True
                raise

        if last_info is None and last_exc is not None:
            raise last_exc
        spi_result = SPIActionResult.from_field_info(last_info)
        if self.measurement_hook is None:
            return FullFlowRecord(
                spi_result=spi_result,
                case_name=case_name,
                preset_values=preset_values,
                active_values=active_values,
                step_idx=step_idx,
            )
        record = self.measurement_hook.after_spi_action(
            spi_result,
            case_name=case_name,
            preset_values=preset_values,
            active_values=active_values,
            step_idx=step_idx,
        )
        if isinstance(record, FullFlowRecord):
            return record
        return FullFlowRecord(
            spi_result=spi_result,
            case_name=case_name,
            preset_values=preset_values,
            active_values=active_values,
            step_idx=step_idx,
        )
