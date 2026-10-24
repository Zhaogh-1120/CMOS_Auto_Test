"""SAW OSC IBIAS × SWCAP phase-noise sweep for CMOS_Auto_Test v0.2.0.

Run from full_flow_test directory:
  python -m scripts.fullflow.case_ibias_swcap_pn_sweep --plan
  python -m scripts.fullflow.case_ibias_swcap_pn_sweep --check-point
  python -m scripts.fullflow.case_ibias_swcap_pn_sweep --run

No SPI writes at import time or in --plan mode. --run/--check-point are
explicit hardware actions. Scan stops immediately on a failed readback or
instrument acquisition, and attempts to restore original REG20/REG21.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

CASE_NAME = "case_ibias_swcap_pn_sweep"
IBIAS_NAME = "CFG_OSC2_IDAC_IBIAS"
SWCAP_NAME = "CFG_OSC2_SWCAP"
REG20 = 0x20
REG21 = 0x21

# Matlab start:step:stop: an unreachable stop is NOT added automatically.
DEFAULT_IBIAS = list(range(0, 31 + 1, 6))      # 0,6,12,18,24,30
DEFAULT_SWCAP = list(range(0, 15 + 1, 4))     # 0,4,8,12

SUMMARY_FIELDS = [
    "step", "ibias_dec", "swcap_dec", "reg20_written_hex", "reg21_written_hex",
    "reg20_read_hex", "reg21_read_hex", "spi_verify", "capture_status",
    "capture_time", "carrier_hz", "carrier_mhz", "output_power_dbm",
    "PN_100Hz", "PN_1kHz", "PN_10kHz", "PN_100kHz", "PN_400kHz",
    "PN_1MHz", "PN_10MHz", "PN_20MHz", "PN_40MHz",
    "integral_start_hz", "integral_stop_hz", "jitter_fs", "rms_rad",
    "integrated_phase_noise_dbc", "residual_fm_hz", "raw_csv_path",
    "point_excel_path", "screenshot_path", "error_message",
]


@dataclass(frozen=True)
class ScanPoint:
    step: int
    ibias: int
    swcap: int


def scan_points(include_endpoints: bool = False) -> list[ScanPoint]:
    a = DEFAULT_IBIAS.copy()
    b = DEFAULT_SWCAP.copy()
    if include_endpoints:
        if 31 not in a:
            a.append(31)
        if 15 not in b:
            b.append(15)
    return [ScanPoint(i + 1, ai, bi) for i, (ai, bi) in
            enumerate((x, y) for x in a for y in b)]


def make_register_values(chip: Any, before20: int, before21: int,
                         ibias: int, swcap: int) -> tuple[int, int]:
    """Preserve REG20[2:0] and REG21[3:0] with the project's real field map."""
    f_i = chip.get_field(IBIAS_NAME)
    f_s = chip.get_field(SWCAP_NAME)
    if (f_i.address, f_i.mask, f_s.address, f_s.mask) != (REG20, 0xF8, REG21, 0xF0):
        raise RuntimeError("Field mapping differs from expected REG20[7:3]/REG21[7:4]")
    return (chip.compose_field_value(before20, f_i, ibias),
            chip.compose_field_value(before21, f_s, swcap))


def verify_register(chip: Any, addr: int, expected: int) -> int:
    read = chip.read_reg(addr)
    if read != expected:
        raise RuntimeError(f"SPI VERIFY FAIL REG{addr:02X}: expected 0x{expected:02X}, got 0x{read:02X}")
    return read


def write_point(chip: Any, target20: int, target21: int) -> tuple[int, int]:
    # One RMW write per REG, not a measurement after each Field write.
    chip.write_reg(REG20, target20)
    r20 = verify_register(chip, REG20, target20)
    chip.write_reg(REG21, target21)
    r21 = verify_register(chip, REG21, target21)
    return r20, r21


def restore_snapshot(chip: Any, snapshot: dict[str, int]) -> None:
    """Best effort: attempt BOTH regs even if one restore fails."""
    failures = []
    for addr, name in ((REG20, "REG20"), (REG21, "REG21")):
        try:
            chip.write_reg(addr, snapshot[name])
            verify_register(chip, addr, snapshot[name])
            print(f"[RESTORE PASS] {name} = 0x{snapshot[name]:02X}")
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            print(f"[RESTORE FAIL] {name}: {exc}", file=sys.stderr)
    if failures:
        raise RuntimeError("Restore failed: " + "; ".join(failures))


def validate_capture(result: Any, *, min_carrier_dbm: float | None = None,
                     freq_min_mhz: float | None = None,
                     freq_max_mhz: float | None = None) -> None:
    xs = result.offsets_hz
    ys = result.phase_noise_dbc_hz
    if len(xs) < 2 or len(xs) != len(ys):
        raise RuntimeError("Invalid E5052B trace: empty or X/Y lengths differ")
    if not all(math.isfinite(float(x)) and x > 0 for x in xs):
        raise RuntimeError("Invalid E5052B offset frequencies")
    if not all(xs[i] < xs[i+1] for i in range(len(xs)-1)):
        raise RuntimeError("E5052B offset frequencies are not increasing")
    if not all(math.isfinite(float(y)) for y in ys):
        raise RuntimeError("E5052B phase noise contains NaN or Inf")
    if not math.isfinite(float(result.output_frequency_hz)) or result.output_frequency_hz <= 0:
        raise RuntimeError("Invalid carrier frequency returned by E5052B")
    f_mhz = float(result.output_frequency_hz) / 1e6
    if freq_min_mhz is not None and f_mhz < freq_min_mhz:
        raise RuntimeError(f"Carrier {f_mhz:.6f} MHz below minimum {freq_min_mhz} MHz")
    if freq_max_mhz is not None and f_mhz > freq_max_mhz:
        raise RuntimeError(f"Carrier {f_mhz:.6f} MHz above maximum {freq_max_mhz} MHz")
    if min_carrier_dbm is not None:
        if result.output_power_dbm is None or float(result.output_power_dbm) < min_carrier_dbm:
            raise RuntimeError(f"Carrier power {result.output_power_dbm} dBm below threshold {min_carrier_dbm} dBm")


def result_row(p: ScanPoint) -> dict[str, Any]:
    return {"step": p.step, "ibias_dec": p.ibias, "swcap_dec": p.swcap,
            "spi_verify": "PENDING", "capture_status": "NOT_STARTED"}


def attach_capture(row: dict[str, Any], result: Any) -> None:
    row.update({
        "capture_status": "PASS", "capture_time": result.capture_time,
        "carrier_hz": result.output_frequency_hz,
        "carrier_mhz": result.output_frequency_hz / 1e6,
        "output_power_dbm": result.output_power_dbm,
        "integral_start_hz": result.integral_start_hz,
        "integral_stop_hz": result.integral_stop_hz,
        "jitter_fs": result.jitter_fs,
        "rms_rad": result.rms_rad,
        "integrated_phase_noise_dbc": result.integrated_phase_noise_dbc,
        "residual_fm_hz": result.residual_fm_hz,
        "raw_csv_path": result.raw_csv_path,
        "point_excel_path": result.excel_path,
        "screenshot_path": result.screenshot_path,
    })
    row.update(result.key_point_dict())


def append_trace_long(writer: csv.writer, handle: Any, p: ScanPoint, result: Any) -> None:
    for x, y in zip(result.offsets_hz, result.phase_noise_dbc_hz):
        writer.writerow([p.step, p.ibias, p.swcap, x, y])
    handle.flush()


def save_summary_xlsx(out_dir: Path, rows: list[dict[str, Any]],
                      trace_long_csv: Path, a_values: list[int], b_values: list[int]) -> Path:
    """Plot-friendly: Summary + long-format PN traces + two 2D maps."""
    import xlsxwriter  # already required by full_flow_test/exporter.py

    path = out_dir / "summary_ibias_swcap.xlsx"
    book = xlsxwriter.Workbook(str(path))
    hdr = book.add_format({"bold": True, "font_color": "white", "bg_color": "#183756",
                           "border": 1, "align": "center"})
    num = book.add_format({"num_format": "0.000000"})
    err = book.add_format({"font_color": "#B91C1C"})
    sheet = book.add_worksheet("Summary")
    sheet.freeze_panes(1, 3)
    sheet.autofilter(0, 0, max(1, len(rows)), len(SUMMARY_FIELDS)-1)
    sheet.set_column(0, 0, 8)
    sheet.set_column(1, 2, 13)
    sheet.set_column(3, 7, 20)
    sheet.set_column(8, len(SUMMARY_FIELDS)-2, 21)
    sheet.set_column(len(SUMMARY_FIELDS)-1, len(SUMMARY_FIELDS)-1, 54)
    for col, field in enumerate(SUMMARY_FIELDS):
        sheet.write(0, col, field, hdr)
    for ridx, row in enumerate(rows, 1):
        for col, field in enumerate(SUMMARY_FIELDS):
            value = row.get(field)
            if value is None or value == "":
                continue
            style = err if field == "error_message" else num if isinstance(value, float) else None
            sheet.write(ridx, col, value, style)
    sheet.set_row(0, 30)

    # Matrix sheet suitable for Excel color-scales and 2-D parameter plots.
    for title, key in (("PN_1MHz_Map", "PN_1MHz"), ("Freq_MHz_Map", "carrier_mhz")):
        ws = book.add_worksheet(title)
        ws.freeze_panes(1, 1)
        ws.set_column(0, 0, 16)
        ws.set_column(1, len(b_values), 14)
        ws.write(0, 0, "IBIAS / SWCAP", hdr)
        for j, b in enumerate(b_values, 1):
            ws.write(0, j, b, hdr)
        data_by_combo = {(int(r['ibias_dec']), int(r['swcap_dec'])): r for r in rows}
        for i, a in enumerate(a_values, 1):
            ws.write(i, 0, a, hdr)
            for j, b in enumerate(b_values, 1):
                value = data_by_combo.get((a, b), {}).get(key)
                if isinstance(value, (int, float)) and math.isfinite(value):
                    ws.write_number(i, j, value, num)
        if a_values and b_values:
            ws.conditional_format(1, 1, len(a_values), len(b_values), {"type": "3_color_scale"})

    # Do not depend on aligned X axes between captures; use long-format data.
    # Excel's max row count is 1,048,576; all raw curves are always retained in CSV.
    wsl = book.add_worksheet("Trace_Long")
    headers = ["step", "ibias_dec", "swcap_dec", "offset_hz", "phase_noise_dbc_hz"]
    for col, name in enumerate(headers):
        wsl.write(0, col, name, hdr)
    wsl.freeze_panes(1, 0)
    wsl.set_column(0, 4, 19)
    with trace_long_csv.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for i, rec in enumerate(reader, 1):
            if i > 1_048_575:
                print("[NOTE] Trace_Long exceeded Excel limit, full trace retained in CSV")
                break
            for j, key in enumerate(headers):
                wsl.write_number(i, j, float(rec[key]))
    book.close()
    return path


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def run_sweep(chip: Any, inst: Any, points: list[ScanPoint], out_dir: Path,
              capture_fn: Callable[..., Any], capture_options: Any, *,
              settle_s: float, acquisition_s: float, restore: bool = True,
              min_carrier_dbm: float | None = None,
              freq_min_mhz: float | None = None, freq_max_mhz: float | None = None) -> dict[str, Any]:
    """Run on already-open devices; injection-friendly for offline fake-device tests."""
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot = {"REG20": chip.read_reg(REG20), "REG21": chip.read_reg(REG21)}
    write_json(out_dir / "initial_register_snapshot.json", {
        "capture_local_time": datetime.now().isoformat(timespec="seconds"),
        "REG20_hex": f"0x{snapshot['REG20']:02X}",
        "REG21_hex": f"0x{snapshot['REG21']:02X}",
        "REG20_dec": snapshot["REG20"],
        "REG21_dec": snapshot["REG21"],
        "notes": "Actual silicon readback; no default-register initialization performed",
    })
    print(f"[SNAPSHOT] REG20=0x{snapshot['REG20']:02X}, REG21=0x{snapshot['REG21']:02X}")
    rows: list[dict[str, Any]] = []
    status = "PASS"
    error: BaseException | None = None
    restore_error: Exception | None = None
    a_values = sorted(set(p.ibias for p in points))
    b_values = sorted(set(p.swcap for p in points))
    trace_long_csv = out_dir / "all_traces_long.csv"
    summary_csv = out_dir / "summary_ibias_swcap.csv"

    with summary_csv.open("w", encoding="utf-8-sig", newline="") as sf, \
         trace_long_csv.open("w", encoding="utf-8-sig", newline="") as lf:
        swriter = csv.DictWriter(sf, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
        lwriter = csv.writer(lf)
        swriter.writeheader()
        lwriter.writerow(["step", "ibias_dec", "swcap_dec", "offset_hz", "phase_noise_dbc_hz"])
        sf.flush()
        lf.flush()
        try:
            for p in points:
                row = result_row(p)
                rows.append(row)
                try:
                    new20, new21 = make_register_values(chip, snapshot['REG20'],
                                                         snapshot['REG21'], p.ibias, p.swcap)
                    row["reg20_written_hex"] = f"0x{new20:02X}"
                    row["reg21_written_hex"] = f"0x{new21:02X}"
                    print(f"\n[{p.step}/{len(points)}] IBIAS={p.ibias}, SWCAP={p.swcap}, "
                          f"REG20=0x{new20:02X}, REG21=0x{new21:02X}")
                    r20, r21 = write_point(chip, new20, new21)
                    row["reg20_read_hex"] = f"0x{r20:02X}"
                    row["reg21_read_hex"] = f"0x{r21:02X}"
                    row["spi_verify"] = "PASS"
                    print("[SPI PASS] Both full 8-bit register readbacks match")
                    if settle_s:
                        time.sleep(settle_s)
                    # Ask the instrument to resume/restart its measurement after configuration.
                    # The explicit acquisition wait MUST be tuned to its actual sweep/averaging time.
                    inst.resume_display()
                    if acquisition_s:
                        time.sleep(acquisition_s)
                    capture_options.delay_before_capture_s = 0.0
                    basename = f"step{p.step:03d}_IBIAS{p.ibias:02d}_SWCAP{p.swcap:02d}"
                    try:
                        result = capture_fn(
                            client=inst, options=capture_options, out_dir=out_dir,
                            shot_name=basename, case_name=CASE_NAME, step_idx=p.step-1,
                            field_names=[IBIAS_NAME, SWCAP_NAME],
                            active_values={IBIAS_NAME: p.ibias, SWCAP_NAME: p.swcap},
                        )
                    finally:
                        # Existing capture implementation can leave the instrument frozen on exceptions.
                        if capture_options.freeze_before_capture:
                            inst.resume_display()
                    validate_capture(result, min_carrier_dbm=min_carrier_dbm,
                                     freq_min_mhz=freq_min_mhz, freq_max_mhz=freq_max_mhz)
                    attach_capture(row, result)
                    append_trace_long(lwriter, lf, p, result)
                    print(f"[PN PASS] f={result.output_frequency_hz/1e6:.6f} MHz, "
                          f"PN@1MHz={row.get('PN_1MHz', 'NA')}, "
                          f"jitter_fs={result.jitter_fs}")
                except BaseException as exc:
                    status = "ABORTED" if isinstance(exc, KeyboardInterrupt) else "FAIL"
                    row["capture_status"] = "ABORTED" if isinstance(exc, KeyboardInterrupt) else "FAIL"
                    row["spi_verify"] = "FAIL" if row["spi_verify"] != "PASS" else "PASS"
                    row["error_message"] = f"{type(exc).__name__}: {exc}"
                    print(f"[STOP] {row['error_message']}", file=sys.stderr)
                    error = exc
                finally:
                    swriter.writerow(row)
                    sf.flush()
                if error is not None:
                    break
        finally:
            if restore:
                try:
                    restore_snapshot(chip, snapshot)
                except Exception as exc:
                    restore_error = exc
                    status = "FAIL"
            else:
                print("[WARNING] --no-restore: chip remains at last written configuration")
            try:
                summary_xlsx = save_summary_xlsx(out_dir, rows, trace_long_csv, a_values, b_values)
                print(f"[EXCEL] {summary_xlsx}")
            except Exception as exc:
                status = "FAIL"
                if error is None:
                    error = exc
                print(f"[EXCEL FAIL] {exc}", file=sys.stderr)
            write_json(out_dir / "run_result.json", {
                "status": status, "completed_points": sum(r.get('capture_status') == 'PASS' for r in rows),
                "planned_points": len(points), "restore_requested": restore,
                "restore_result": "FAIL" if restore_error else "PASS" if restore else "SKIPPED",
                "error": str(error) if error else None,
                "restore_error": str(restore_error) if restore_error else None,
                "summary_csv": str(summary_csv), "long_csv": str(trace_long_csv),
            })
    print(f"[CASE {status}] completed {sum(r.get('capture_status')=='PASS' for r in rows)}/{len(points)}")
    if error is not None:
        if isinstance(error, KeyboardInterrupt):
            raise KeyboardInterrupt from error
        raise RuntimeError("Sweep stopped on first error: " + str(error)) from error
    if restore_error is not None:
        raise RuntimeError("Scan completed but snapshot restore failed") from restore_error
    return {"status": status, "rows": rows, "out_dir": str(out_dir)}


def plan_only(points: list[ScanPoint]) -> None:
    print(f"IBIAS values : {list(dict.fromkeys(p.ibias for p in points))}")
    print(f"SWCAP values: {list(dict.fromkeys(p.swcap for p in points))}")
    print(f"Total combinations: {len(points)} (IBIAS outer, SWCAP inner)")
    print("step,IBIAS_DEC,SWCAP_DEC")
    for p in points:
        print(f"{p.step:03d},{p.ibias},{p.swcap}")
    print("[PLAN ONLY] No instruments or SPI devices opened, no chip writes")


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="IBIAS × SWCAP sweep with E5052B acquisition")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--plan", action="store_true", help="Print plan only; never access hardware")
    action.add_argument("--check-point", action="store_true", help="Real hardware, one baseline point IBIAS=15 SWCAP=7")
    action.add_argument("--run", action="store_true", help="Real hardware, full sweep")
    parser.add_argument("--include-endpoints", action="store_true", help="Also append 31 and 15 if step does not reach them")
    parser.add_argument("--settle-s", type=float, default=2.0, help="Wait for oscillator after SPI configuration")
    parser.add_argument("--acquire-s", type=float, default=12.0, help="Wait for NEW E5052B sweep/averaging; tune to actual instrument")
    parser.add_argument("--screenshot", action="store_true", help="Save instrument screenshot for every point")
    parser.add_argument("--point-excel", action="store_true", help="Also save a separate XLSX per point")
    parser.add_argument("--no-restore", action="store_true", help="Do not restore snapshot (NOT recommended)")
    parser.add_argument("--min-carrier-dbm", type=float, default=None, help="Optional minimum acceptable E5052B carrier power")
    parser.add_argument("--freq-min-mhz", type=float, default=None, help="Optional minimum acceptable carrier frequency")
    parser.add_argument("--freq-max-mhz", type=float, default=None, help="Optional maximum acceptable carrier frequency")
    parser.add_argument("--output-dir", default=f"outputs/fullflow/{CASE_NAME}")
    args = parser.parse_args(argv)
    if args.settle_s < 0 or args.acquire_s < 0:
        parser.error("--settle-s and --acquire-s must be non-negative")
    if args.freq_min_mhz is not None and args.freq_max_mhz is not None and args.freq_min_mhz >= args.freq_max_mhz:
        parser.error("--freq-min-mhz must be less than --freq-max-mhz")

    points = ( [ScanPoint(1, 15, 7)] if args.check_point else
              scan_points(include_endpoints=args.include_endpoints) )
    if args.plan:
        plan_only(points)
        return 0

    # Only real hardware actions import Windows-specific Ginkgo DLL.
    from protocol.chip_spi import ChipSpi
    from instruments.e5052b.capture import capture_phase_noise_once
    from scripts.fullflow.common import build_capture_options, make_client_from_config
    from utils.e5052b_config import load_e5052b_config
    from utils.path_helper import create_run_dir, ensure_output_tree

    cfg = load_e5052b_config()
    options = build_capture_options(cfg, save_screenshot=args.screenshot)
    options.save_screenshot = args.screenshot
    options.save_csv = True
    options.save_excel = args.point_excel
    options.freeze_before_capture = True
    options.resume_after_capture = True
    run_dir = create_run_dir(Path(args.output_dir))
    ensure_output_tree(run_dir)
    write_json(run_dir / "run_plan.json", {
        "case": CASE_NAME, "points": [vars(p) for p in points],
        "settle_s": args.settle_s, "acquire_s": args.acquire_s,
        "save_screenshot": args.screenshot, "save_point_excel": args.point_excel,
        "restore": not args.no_restore,
        "min_carrier_dbm": args.min_carrier_dbm,
        "freq_min_mhz": args.freq_min_mhz, "freq_max_mhz": args.freq_max_mhz,
        "instrument_host": cfg['host'], "instrument_port": cfg.get('port', 5025),
        "note": "No programmed initialization; real readback snapshot before first write",
    })
    print(f"[RUN DIR] {run_dir}")
    print(f"[CONFIG] {len(points)} combinations; settle={args.settle_s}s, acquisition={args.acquire_s}s")
    print("[WARNING] Confirm E5052B sweep/average time is shorter than --acquire-s")
    try:
        with make_client_from_config(cfg) as inst:
            print("[E5052B]", inst.identify())
            with ChipSpi() as chip:
                run_sweep(chip, inst, points, run_dir, capture_phase_noise_once, options,
                          settle_s=args.settle_s, acquisition_s=args.acquire_s,
                          restore=not args.no_restore,
                          min_carrier_dbm=args.min_carrier_dbm,
                          freq_min_mhz=args.freq_min_mhz, freq_max_mhz=args.freq_max_mhz)
    except KeyboardInterrupt:
        print("[ABORTED] Ctrl+C; restore attempted if chip was connected and snapshot was available")
        return 130
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print("[PASS] Ready for Excel plotting")
    return 0


if __name__ == "__main__":
    sys.exit(cli())
