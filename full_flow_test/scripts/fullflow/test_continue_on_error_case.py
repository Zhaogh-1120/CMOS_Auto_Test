from __future__ import annotations

import time

from protocol.chip_spi import ChipSpi
from core.measurement_hook import E5052BMeasurementHook, FlowOptions
from core.result_model import FullFlowRecord
from core.session import TestSession
from scripts.fullflow.common import (
    build_capture_options,
    build_case_policy,
    make_client_from_config,
    print_block,
    print_case_done,
    print_case_error,
    print_case_start,
    print_debug_info,
    print_instrument_debug,
    print_flow_config,
    print_progress,
    print_record,
    register_error_record,
    write_run_meta,
)
from utils.e5052b_config import load_e5052b_config
from utils.value_spec import iter_value_spec
from core.formatter import format_output_paths


CASE_NAME = "test_continue_on_error_case"
CASE_DESC = "validate continue_on_error behavior with manual injected step error"

DEBUG = False
CONTINUE_ON_ERROR = False

CASE_POLICY = {
    "DEBUG": DEBUG,
    "CONTINUE_ON_ERROR": CONTINUE_ON_ERROR,
    "SPI_RETRY_ON_FAIL": False,
    "SPI_RETRY_COUNT": 1,
    "SPI_RETRY_DELAY_S": 0.05,
    "STRICT_SPI_LINK_CHECK": False,
    "MAX_CONSECUTIVE_SPI_FAILS": 3,
    "CONTINUE_ON_DEVICE_LOSS": False,
    "RAISE_ON_SPI_VERIFY_FAIL": False,
}

ENABLE_MEASUREMENT = True
SAVE_SCREENSHOT = False
SAVE_CSV = True
SAVE_EXCEL = True
DELAY_BEFORE_MEASUREMENT_S = 0.0

FIELD_NAME = "CFG_OSC2_TEST_BUF_IBIAS"
VALUE_SPEC = {"values": [0, 3, 4, 7]}
PRESETS = []

ENABLE_MANUAL_TEST_ERROR = True
MANUAL_ERROR_STAGE = "SPI_SCAN"
MANUAL_ERROR_TRIGGER_VALUE = 4


def main():
    start_ts = time.perf_counter()
    local_records: list[FullFlowRecord] = []

    cfg = load_e5052b_config()
    policy = build_case_policy(CASE_POLICY)

    effective_debug = bool(policy.get("DEBUG", DEBUG))
    effective_continue_on_error = bool(policy.get("CONTINUE_ON_ERROR", CONTINUE_ON_ERROR))

    capture_options = build_capture_options(cfg, save_screenshot=SAVE_SCREENSHOT)
    flow = FlowOptions(
        enable_measurement=ENABLE_MEASUREMENT,
        delay_before_measurement_s=DELAY_BEFORE_MEASUREMENT_S,
        save_screenshot=SAVE_SCREENSHOT,
        save_csv=SAVE_CSV and cfg.get("save_csv", True),
        save_excel=SAVE_EXCEL and cfg.get("save_excel", True),
        output_dir=f"outputs/fullflow/{CASE_NAME}",
        case_name=CASE_NAME,
        case_desc=CASE_DESC,
        debug=effective_debug,
        continue_on_error=effective_continue_on_error,
    )

    print_case_start(
        CASE_NAME,
        case_desc=CASE_DESC,
        debug=effective_debug,
        continue_on_error=effective_continue_on_error,
    )
    print_flow_config(CASE_NAME, flow)

    print_debug_info(
        "CASE CONFIG",
        {
            "debug": effective_debug,
            "continue_on_error": effective_continue_on_error,
            "enable_manual_test_error": ENABLE_MANUAL_TEST_ERROR,
            "manual_error_stage": MANUAL_ERROR_STAGE,
            "manual_error_trigger_value": MANUAL_ERROR_TRIGGER_VALUE,
            "enable_measurement": ENABLE_MEASUREMENT,
            "save_screenshot": SAVE_SCREENSHOT,
            "save_csv": SAVE_CSV,
            "save_excel": SAVE_EXCEL,
            "delay_before_measurement_s": DELAY_BEFORE_MEASUREMENT_S,
        },
        effective_debug,
    )

    values = list(iter_value_spec(VALUE_SPEC))
    hook = None
    merged = None

    try:
        with ChipSpi() as chip, make_client_from_config(cfg) as inst:
            print_instrument_debug(cfg, inst, effective_debug)

            hook = E5052BMeasurementHook(inst, capture_options, flow) if ENABLE_MEASUREMENT else None
            session = TestSession(chip, hook, runtime_policy=policy)

            for idx, value in enumerate(values):
                active_values = {FIELD_NAME: value}

                print_progress(idx, len(values), active_values)
                print_debug_info(
                    "STEP CONTEXT",
                    {
                        "step_idx": idx + 1,
                        "field_name": FIELD_NAME,
                        "value": value,
                        "active_values": active_values,
                    },
                    effective_debug,
                )

                try:
                    if (
                        ENABLE_MANUAL_TEST_ERROR
                        and MANUAL_ERROR_STAGE == "SPI_SCAN"
                        and value == MANUAL_ERROR_TRIGGER_VALUE
                    ):
                        raise RuntimeError(
                            f"manual test error for continue_on_error validation, trigger value={value}"
                        )

                    record = session.run_field_write_read(
                        FIELD_NAME,
                        value,
                        case_name=CASE_NAME,
                        preset_values={},
                        active_values=active_values,
                        step_idx=idx,
                    )
                    local_records.append(record)
                    print_record(record)

                except Exception as exc:
                    print_case_error(
                        CASE_NAME,
                        "SPI_SCAN",
                        exc,
                        step_idx=idx,
                        active_values=active_values,
                    )

                    register_error_record(
                        hook,
                        local_records,
                        target_name=FIELD_NAME,
                        write_value=value,
                        case_name=CASE_NAME,
                        preset_values={},
                        active_values=active_values,
                        step_idx=idx,
                        stage="SPI_SCAN",
                        exc=exc,
                    )

                    if not effective_continue_on_error:
                        raise

                    # 关键：True 时明确进入下一轮
                    continue

            if hook is not None:
                print_debug_info(
                    "EXPORT CONTEXT",
                    {
                        "record_count": len(hook.records),
                        "run_dir": str(hook.run_dir),
                    },
                    effective_debug,
                )

                merged = hook.export_merged_summary(f"merged_summary_{CASE_NAME}.xlsx")

                print_debug_info(
                    "EXPORT CONTEXT",
                    {
                        "merged_summary_path": merged,
                        "run_dir": str(hook.run_dir),
                    },
                    effective_debug,
                )

                print_block(
                    format_output_paths(
                        {
                            "merged_summary_path": merged,
                            "run_dir": str(hook.run_dir),
                        }
                    )
                )

                write_run_meta(
                    hook.run_dir,
                    {
                        "case_name": CASE_NAME,
                        "case_desc": CASE_DESC,
                        "debug": effective_debug,
                        "continue_on_error": effective_continue_on_error,
                        "enable_measurement": ENABLE_MEASUREMENT,
                        "save_screenshot": SAVE_SCREENSHOT,
                        "save_csv": SAVE_CSV,
                        "save_excel": SAVE_EXCEL,
                        "delay_before_measurement_s": DELAY_BEFORE_MEASUREMENT_S,
                        "field_name": FIELD_NAME,
                        "value_spec": VALUE_SPEC,
                        "enable_manual_test_error": ENABLE_MANUAL_TEST_ERROR,
                        "manual_error_stage": MANUAL_ERROR_STAGE,
                        "manual_error_trigger_value": MANUAL_ERROR_TRIGGER_VALUE,
                        "elapsed_s": round(time.perf_counter() - start_ts, 3),
                        "merged_summary_path": merged,
                    },
                )

        records = hook.records if hook is not None else local_records
        status = "PASS" if records and all(r.overall_status == "PASS" for r in records) else "FAIL"

        print_case_done(
            CASE_NAME,
            status=status,
            run_dir=str(hook.run_dir) if hook else None,
            merged_summary_path=merged,
            elapsed_s=time.perf_counter() - start_ts,
        )

    except Exception as exc:
        print_case_error(CASE_NAME, "CASE_MAIN", exc)
        print_case_done(
            CASE_NAME,
            status="FAIL",
            run_dir=str(hook.run_dir) if hook else None,
            merged_summary_path=merged,
            elapsed_s=time.perf_counter() - start_ts,
        )
        raise


if __name__ == "__main__":
    main()