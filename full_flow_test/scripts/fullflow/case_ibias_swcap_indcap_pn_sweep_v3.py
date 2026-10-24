"""SAW OSC IBIAS × SWCAP × IND_CAP phase-noise sweep for CMOS_Auto_Test v0.2.0.

Run from full_flow_test directory:
  python -m scripts.fullflow.case_ibias_swcap_indcap_pn_sweep_v3
  python -m scripts.fullflow.case_ibias_swcap_indcap_pn_sweep_v3 --plan
  python -m scripts.fullflow.case_ibias_swcap_indcap_pn_sweep_v3 --check-point

DEFAULT WITH NO ARGUMENTS: real 140-point sweep + individual screenshots,
individual Excel reports, raw trace CSVs and analysis summary Excel.
All files remain under outputs/fullflow/case_ibias_swcap_indcap_pn_sweep/run_*/.
No SPI writes on import or in --plan/--report-only. Hardware failures abort
and a best-effort snapshot restoration follows.
"""
from __future__ import annotations

import argparse
import os
import re
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

# Colored terminal output. Only the terminal contains ANSI escapes; run_log.txt is plain text.
ANSI = {
    "green": "\033[92m", "red": "\033[91m", "blue": "\033[94m",
    "yellow": "\033[93m", "cyan": "\033[96m", "gray": "\033[90m",
    "bold": "\033[1m", "reset": "\033[0m",
}
LOG_HANDLE = None
COLOR_ON = False


def initialize_colors(disable_color: bool = False) -> None:
    global COLOR_ON
    COLOR_ON = bool(sys.stdout.isatty() and not disable_color and "NO_COLOR" not in os.environ)
    if COLOR_ON and os.name == "nt":
        try:
            from colorama import just_fix_windows_console
            just_fix_windows_console()
        except ImportError:
            pass  # VS Code integrated terminal normally understands ANSI sequences.


def emit(*segments: tuple[str, str | None] | str, err: bool = False) -> None:
    """Colored screen message and synchronized plain-text log entry."""
    plain_parts, screen_parts = [], []
    for segment in segments:
        raw, color = (segment, None) if isinstance(segment, str) else segment
        raw = str(raw)
        plain_parts.append(raw)
        screen_parts.append(f"{ANSI[color]}{raw}{ANSI['reset']}" if COLOR_ON and color else raw)
    target = sys.stderr if err else sys.stdout
    print("".join(screen_parts), file=target, flush=True)
    if LOG_HANDLE is not None:
        LOG_HANDLE.write("".join(plain_parts) + "\n")
        LOG_HANDLE.flush()


def elapsed_text(seconds: float) -> str:
    total = max(0, round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def display_value(value: Any, precision: int = 2) -> str:
    try:
        x = float(value)
        return f"{x:.{precision}f}" if math.isfinite(x) else "--"
    except (TypeError, ValueError):
        return "--"


def basename_if_saved(value: Any) -> str:
    return Path(str(value)).name if value else "--"


def show_step_start(p: "ScanPoint", total: int, started: float) -> None:
    elapsed = time.monotonic() - started
    done = p.step - 1
    eta = (elapsed / done) * (total - done) if done else None
    emit("\n" + "─" * 77)
    emit((datetime.now().strftime("[%Y-%m-%d %H:%M:%S] "), "gray"),
         (f"[{p.step}/{total}] ", "bold"),
         (f"{100 * p.step / total:.1f}%", "cyan"))
    emit((f"IBIAS={p.ibias}  SWCAP={p.swcap}  IND_CAP={p.ind_cap}", "yellow"))
    emit((f"Elapsed={elapsed_text(elapsed)}  ETA={elapsed_text(eta) if eta is not None else '--:--:--'}", "gray"))


def show_registers(reg_data: dict[int, tuple[int, int | None]], *, success: bool) -> None:
    emit((("[SPI PASS]" if success else "[SPI ERROR]"), "green" if success else "red"),
         (" 3/3 registers verified" if success else " readback/communication failure"))
    for addr in (REG20, REG21, REG22):
        if addr not in reg_data:
            continue
        wanted, got = reg_data[addr]
        ok = got == wanted
        emit((f"REG{addr:02X}: ", "bold"),
             (f"Write=0x{wanted:02X}", "blue"), "  ",
             (f"Read=0x{got:02X}" if got is not None else "Read=--", "yellow"), "  ",
             ("PASS" if ok else "ERROR", "green" if ok else "red"))


def show_phase_noise(row: dict[str, Any]) -> None:
    emit(("[PN PASS]", "green"))
    emit(f"Freq        = {display_value(row.get('carrier_mhz'), 6)} MHz"
         f"    PN@1MHz   = {display_value(row.get('PN_1MHz'))} dBc/Hz")
    emit(f"Power       = {display_value(row.get('output_power_dbm'))} dBm"
         f"     PN@10MHz  = {display_value(row.get('PN_10MHz'))} dBc/Hz")
    emit(f"PN@1kHz     = {display_value(row.get('PN_1kHz'))} dBc/Hz"
         f"   Jitter    = {display_value(row.get('jitter_fs'))} fs")
    emit(f"PN@10kHz    = {display_value(row.get('PN_10kHz'))} dBc/Hz"
         f"   Integration = {display_value(row.get('integral_start_hz'), 0)}"
         f"–{display_value(row.get('integral_stop_hz'), 0)} Hz")
    emit(f"PN@100kHz   = {display_value(row.get('PN_100kHz'))} dBc/Hz")


def show_saved(row: dict[str, Any]) -> None:
    emit(("[SAVE PASS]", "green"))
    emit("Summary CSV : Updated")
    emit("Raw PN      : " + basename_if_saved(row.get("raw_csv_path")))
    screenshot = row.get("screenshot_path")
    if screenshot:
        scr = Path(str(screenshot))
        status = "Saved" if scr.is_file() else "Path returned (verify file)"
        emit(f"Screenshot  : {status}: {scr.name}")
    else:
        emit("Screenshot  : Not requested / unavailable")
    if row.get('point_excel_path'):
        emit("Point Excel : " + basename_if_saved(row['point_excel_path']))
    emit(("[STEP PASS]", "green"))


class SPIReadbackError(RuntimeError):
    def __init__(self, addr: int, expected: int, actual: int):
        self.addr, self.expected, self.actual = addr, expected, actual
        super().__init__(f"SPI VERIFY FAIL REG{addr:02X}: expected 0x{expected:02X}, got 0x{actual:02X}")


CASE_NAME = "case_ibias_swcap_indcap_pn_sweep"
IBIAS_NAME = "CFG_OSC2_IDAC_IBIAS"
SWCAP_NAME = "CFG_OSC2_SWCAP"
IND_P_NAME = "CFG_IND_SWCAP_P"
IND_N_NAME = "CFG_IND_SWCAP_N"
REG20 = 0x20
REG21 = 0x21
REG22 = 0x22

# All sweep ranges include their endpoints even when the step misses the stop.
def inclusive_values(start: int, stop: int, step: int) -> list[int]:
    if step == 0 or (stop - start) * step < 0:
        raise ValueError("Invalid sweep direction or zero step")
    values = list(range(start, stop + (1 if step > 0 else -1), step))
    if not values:
        values = [start]
    if values[-1] != stop:
        values.append(stop)
    return values

DEFAULT_IBIAS = inclusive_values(0, 31, 6)   # 0,6,12,18,24,30,31
DEFAULT_SWCAP = inclusive_values(0, 15, 4)  # 0,4,8,12,15
DEFAULT_IND_CAP = inclusive_values(0, 7, 3) # 0,3,6,7 (P=N)

SUMMARY_FIELDS = [
    "step", "ibias_dec", "swcap_dec", "ind_cap_dec",
    "ind_p_dec", "ind_n_dec", "reg20_written_hex", "reg21_written_hex",
    "reg22_written_hex", "reg20_read_hex", "reg21_read_hex", "reg22_read_hex", "spi_verify", "capture_status",
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
    ind_cap: int


def scan_points() -> list[ScanPoint]:
    return [ScanPoint(i + 1, a, b, c) for i, (a, b, c) in enumerate(
        (x, y, z) for x in DEFAULT_IBIAS for y in DEFAULT_SWCAP for z in DEFAULT_IND_CAP
    )]


def make_register_values(chip: Any, before20: int, before21: int, before22: int,
                         ibias: int, swcap: int, ind_cap: int) -> tuple[int, int, int]:
    """Build REG20/21/22, preserving every unselected bit.

    P and N both reside in REG22; one complete write updates them together.
    """
    f_i = chip.get_field(IBIAS_NAME)
    f_s = chip.get_field(SWCAP_NAME)
    f_p = chip.get_field(IND_P_NAME)
    f_n = chip.get_field(IND_N_NAME)
    expected_map = (
        (f_i.address, f_i.mask, f_i.lsb),
        (f_s.address, f_s.mask, f_s.lsb),
        (f_p.address, f_p.mask, f_p.lsb),
        (f_n.address, f_n.mask, f_n.lsb),
    )
    if expected_map != ((REG20, 0xF8, 3), (REG21, 0xF0, 4),
                        (REG22, 0x38, 3), (REG22, 0x07, 0)):
        raise RuntimeError(f"Unexpected register Field mapping: {expected_map!r}")
    reg20 = chip.compose_field_value(before20, f_i, ibias)
    reg21 = chip.compose_field_value(before21, f_s, swcap)
    reg22 = chip.compose_field_value(before22, f_p, ind_cap)
    reg22 = chip.compose_field_value(reg22, f_n, ind_cap)
    return reg20, reg21, reg22


def verify_register(chip: Any, addr: int, expected: int) -> int:
    read = chip.read_reg(addr)
    if read != expected:
        raise SPIReadbackError(addr, expected, read)
    return read


def write_point(chip: Any, target20: int, target21: int, target22: int,
                on_verified: Callable[[int, int, int], None] | None = None) -> tuple[int, int, int]:
    # REG22 updates both IND_P and IND_N in a SINGLE 8-bit SPI write.
    # Fail immediately on any mismatched full-register readback.
    chip.write_reg(REG20, target20)
    r20 = verify_register(chip, REG20, target20)
    if on_verified is not None:
        on_verified(REG20, target20, r20)
    chip.write_reg(REG21, target21)
    r21 = verify_register(chip, REG21, target21)
    if on_verified is not None:
        on_verified(REG21, target21, r21)
    chip.write_reg(REG22, target22)
    r22 = verify_register(chip, REG22, target22)
    if on_verified is not None:
        on_verified(REG22, target22, r22)
    return r20, r21, r22


def restore_snapshot(chip: Any, snapshot: dict[str, int]) -> None:
    """Best effort: attempt all three, even if one restore step fails."""
    failures = []
    for addr, name in ((REG20, "REG20"), (REG21, "REG21"), (REG22, "REG22")):
        try:
            chip.write_reg(addr, snapshot[name])
            verify_register(chip, addr, snapshot[name])
            emit((f"[RESTORE PASS]", "green"), f" {name} = 0x{snapshot[name]:02X}")
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            emit((f"[RESTORE ERROR]", "red"), (f" {name}: {exc}", "red"), err=True)
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
            "ind_cap_dec": p.ind_cap, "ind_p_dec": p.ind_cap, "ind_n_dec": p.ind_cap,
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
        writer.writerow([p.step, p.ibias, p.swcap, p.ind_cap, p.ind_cap, p.ind_cap, x, y])
    handle.flush()


# ---------------------------------------------------------------------------
# Excel analysis pages are generated from the SAME measured Summary rows.
# They require no separate template, no separate Python script, and no hardware.
# The established Summary / PN_1MHz_IND* / Freq_MHz_IND* / Trace_Long formats
# are retained. Failed points are excluded from rankings and plotted as blanks.
# ---------------------------------------------------------------------------
PERFORMANCE_METRICS = [
    ("Jitter_fs", "Jitter (fs)", "jitter_fs", "low"),
    ("PN_1kHz", "PN @ 1 kHz (dBc/Hz)", "PN_1kHz", "low"),
    ("PN_10kHz", "PN @ 10 kHz (dBc/Hz)", "PN_10kHz", "low"),
    ("PN_100kHz", "PN @ 100 kHz (dBc/Hz)", "PN_100kHz", "low"),
    ("PN_1MHz", "PN @ 1 MHz (dBc/Hz)", "PN_1MHz", "low"),
    ("Freq_MHz", "Carrier Frequency (MHz)", "carrier_mhz", "low"),
]
RANK_METRICS = ["Jitter_fs", "PN_1kHz", "PN_10kHz", "PN_100kHz",
                "PN_1MHz", "Frequency_Low", "Frequency_High"]
RANK_COLUMNS = ["Rank", "Step", "IBIAS", "SWCAP", "IND_CAP", "Jitter_fs",
                "PN_1kHz", "PN_10kHz", "PN_100kHz", "PN_1MHz",
                "Freq_MHz", "Power_dBm", "REG20", "REG21", "REG22"]


def _safe_numeric(val: Any) -> float | None:
    try:
        if val is None or isinstance(val, bool):
            return None
        x = float(val)
        return x if math.isfinite(x) else None
    except (ValueError, TypeError):
        return None


def _completed_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("spi_verify") == "PASS"
            and r.get("capture_status") == "PASS"]


def _rank_rows(rows: list[dict[str, Any]], metric: str, limit: int = 30) -> list[dict[str, Any]]:
    field = ("carrier_mhz" if metric in ("Frequency_Low", "Frequency_High") else
             "jitter_fs" if metric == "Jitter_fs" else metric)
    eligible = [r for r in _completed_rows(rows) if _safe_numeric(r.get(field)) is not None]
    return sorted(eligible, key=lambda r: (
        -float(r[field]) if metric == "Frequency_High" else float(r[field]), int(r["step"])) )[:limit]


def add_analytics_sheets(book: Any, rows: list[dict[str, Any]],
                         a_values: list[int], b_values: list[int],
                         c_values: list[int], out_dir: Path) -> None:
    """Create dashboard + 3 interactive Fixed_* pages + full performance Top 30."""
    from xlsxwriter.utility import xl_col_to_name

    navy = "#142740"
    navy2 = "#193D58"
    teal = "#007A85"
    light = "#EAF5F9"
    pale = "#F0F5FA"
    gold = "#FFF0B9"
    slate = "#536A7D"
    green = "#18794E"
    red = "#B42318"
    palette = ["#147DA4", "#D9822B", "#198C70", "#8D6BB8", "#CB6D86"]
    fm_title = book.add_format({"bold": True, "font_size": 17, "font_color": "white",
                                "bg_color": navy, "valign": "vcenter"})
    fm_sub = book.add_format({"bold": True, "font_size": 11, "font_color": navy2,
                              "bg_color": light, "valign": "vcenter"})
    fm_col = book.add_format({"bold": True, "font_color": "white", "bg_color": teal,
                              "align": "center", "border": 1, "border_color": "#D5E1E8"})
    fm_label = book.add_format({"bold": True, "font_color": navy2})
    fm_note = book.add_format({"font_color": slate, "italic": True, "text_wrap": True})
    fm_warning = book.add_format({"font_color": red, "bg_color": "#FFF0ED", "text_wrap": True})
    fm_input = book.add_format({"bold": True, "font_color": navy, "bg_color": gold,
                                "border": 1, "border_color": "#DBB557", "align": "center"})
    fm_num = book.add_format({"num_format": "0.000", "border": 1,
                              "border_color": "#E5EBF0", "align": "center"})
    fm_int = book.add_format({"num_format": "0", "border": 1,
                              "border_color": "#E5EBF0", "align": "center"})
    fm_plain = book.add_format({"border": 1, "border_color": "#E5EBF0",
                                "align": "center"})
    fm_ok = book.add_format({"font_color": green, "bold": True})
    fm_err = book.add_format({"font_color": red, "bold": True})
    fm_kpi = book.add_format({"font_size": 16, "bold": True, "font_color": navy})
    fm_small = book.add_format({"font_color": slate, "font_size": 9})

    all_pass = _completed_rows(rows)
    by_combo = {(int(r["ibias_dec"]), int(r["swcap_dec"]), int(r["ind_cap_dec"])): r
                for r in all_pass}
    a_values = sorted(a_values)
    b_values = sorted(b_values)
    c_values = sorted(c_values)

    # Easier-to-plot typed table; the original Summary remains identical.
    data_cols = ["Step", "IBIAS", "SWCAP", "IND_CAP", "Jitter_fs", "PN_1kHz",
                 "PN_10kHz", "PN_100kHz", "PN_1MHz", "Freq_MHz", "Power_dBm",
                 "Status", "PN_100Hz", "REG20", "REG21", "REG22", "Capture_Time"]
    data_src = ["step", "ibias_dec", "swcap_dec", "ind_cap_dec", "jitter_fs",
                "PN_1kHz", "PN_10kHz", "PN_100kHz", "PN_1MHz", "carrier_mhz",
                "output_power_dbm", "capture_status", "PN_100Hz", "reg20_read_hex",
                "reg21_read_hex", "reg22_read_hex", "capture_time"]
    data = book.add_worksheet("Data")
    data.freeze_panes(1, 4)
    data.set_tab_color(teal)
    data.set_column(0, 3, 12)
    data.set_column(4, 10, 16)
    data.set_column(11, 15, 15)
    data.set_column(16, 16, 23)
    for j, head in enumerate(data_cols):
        data.write(0, j, head, fm_col)
    for i, row in enumerate(rows, 1):
        for j, field in enumerate(data_src):
            val = row.get(field)
            if val is None or val == "":
                continue
            data.write(i, j, val, fm_int if j < 4 else
                       fm_num if isinstance(val, float) else fm_plain)
    if rows:
        data.autofilter(0, 0, len(rows), len(data_cols)-1)

    # Keep previous dashboard's Original_Summary as a familiar reference copy.
    orig = book.add_worksheet("Original_Summary")
    orig.freeze_panes(1, 4)
    orig.set_column(0, 5, 14)
    orig.set_column(6, len(SUMMARY_FIELDS)-1, 20)
    for j, name in enumerate(SUMMARY_FIELDS):
        orig.write(0, j, name, fm_col)
    for i, row in enumerate(rows, 1):
        for j, field in enumerate(SUMMARY_FIELDS):
            value = row.get(field)
            if value is not None and value != "":
                orig.write(i, j, value)
    if rows:
        orig.autofilter(0, 0, len(rows), len(SUMMARY_FIELDS)-1)

    # Top ranking cache permits immediate recalculation in Excel/WPS when B6 or D162 changes.
    # Key = Fixed_IND|3|Jitter_fs|1, etc. No external macros/add-ins needed.
    index = book.add_worksheet("Rank_Lists")
    cache_columns = ["Lookup_Key", "Step", "IBIAS", "SWCAP", "IND_CAP",
                     "Jitter_fs", "PN_1kHz", "PN_10kHz", "PN_100kHz", "PN_1MHz",
                     "Freq_MHz", "Power_dBm", "REG20", "REG21", "REG22"]
    for j, head in enumerate(cache_columns):
        index.write(0, j, head, fm_col)
    cache_count = 0
    rank_lookup: dict[str, dict[str, Any]] = {}
    configs = [("Fixed_IBIAS", "ibias_dec", a_values),
               ("Fixed_SWCAP", "swcap_dec", b_values),
               ("Fixed_IND", "ind_cap_dec", c_values)]
    for name, field, codes in configs:
        for code in codes:
            subset = [r for r in all_pass if int(r[field]) == code]
            for metric in RANK_METRICS:
                for rank, r in enumerate(_rank_rows(subset, metric), 1):
                    key = f"{name}|{code}|{metric}|{rank}"
                    values = [key, r.get("step"), r.get("ibias_dec"), r.get("swcap_dec"),
                              r.get("ind_cap_dec"), r.get("jitter_fs"), r.get("PN_1kHz"),
                              r.get("PN_10kHz"), r.get("PN_100kHz"), r.get("PN_1MHz"),
                              r.get("carrier_mhz"), r.get("output_power_dbm"),
                              r.get("reg20_read_hex"), r.get("reg21_read_hex"), r.get("reg22_read_hex")]
                    cache_count += 1
                    rank_lookup[key] = dict(zip(cache_columns, values))
                    for col, v in enumerate(values):
                        if v is not None:
                            index.write(cache_count, col, v)
    cache_end = max(2, cache_count + 1)
    index.hide()

    # Fixed parameter drill-down pages: six side-by-side tables/charts and Top 30.
    role_settings = [
        ("Fixed_IBIAS", "IBIAS", "SWCAP", "IND_CAP", a_values, b_values, c_values),
        ("Fixed_SWCAP", "SWCAP", "IBIAS", "IND_CAP", b_values, a_values, c_values),
        ("Fixed_IND", "IND_CAP", "IBIAS", "SWCAP", c_values, a_values, b_values),
    ]
    ccol = {"IBIAS": "B", "SWCAP": "C", "IND_CAP": "D", "Status": "L"}
    metrics_data_col = {"Jitter_fs": "E", "PN_1kHz": "F", "PN_10kHz": "G",
                        "PN_100kHz": "H", "PN_1MHz": "I", "Freq_MHz": "J"}
    data_end = max(2, len(rows)+1)
    for name, fixed, axis, series, fvals, yvals, zvals in role_settings:
        ws = book.add_worksheet(name)
        ws.set_tab_color("#1A89A2")
        ws.hide_gridlines(2)
        ws.set_zoom(85)
        ws.set_landscape()
        ws.fit_to_pages(1, 0)
        ws.set_column("A:A", 14)
        ws.set_column("B:G", 13)
        ws.set_column("H:I", 4)
        ws.set_column("J:R", 11)
        ws.set_default_row(19)
        ws.freeze_panes(8, 1)
        ws.merge_range("A2:R3", f"{name.upper()}  |  {fixed} fixed, {axis} × {series}", fm_title)
        ws.merge_range("A5:R5", "Yellow selector changes all six metric tables and curves; only SPI+PN PASS points are plotted.", fm_sub)
        ws.write("A6", f"Fixed {fixed}", fm_label)
        value = fvals[0] if fvals else 0
        # Prefer previous board's normal current level where available.
        if fixed == "IBIAS" and 12 in fvals:
            value = 12
        elif fixed == "SWCAP" and 8 in fvals:
            value = 8
        elif fixed == "IND_CAP" and 3 in fvals:
            value = 3
        ws.write_number("B6", value, fm_input)
        ws.data_validation("B6", {"validate": "list", "source": fvals, "input_title": "Fixed code",
                                  "input_message": f"Select an available {fixed} code"})
        ws.write("D6", "Metric tables + trend plots", fm_small)
        ws.write("A7", "Lower PN/Jitter is better. Frequency colors indicate variation, not goodness.", fm_note)
        for metric_i, (mkey, title, row_field, smaller) in enumerate(PERFORMANCE_METRICS):
            top = 9 + metric_i * 25  # zero-based worksheet row
            ws.merge_range(top, 0, top, 6, f"{title}  |  {axis} vs {series}", fm_sub)
            hdr_row = top+2
            ws.write(hdr_row, 0, axis, fm_col)
            for z_i, z in enumerate(zvals, 1):
                ws.write_number(hdr_row, z_i, z, fm_col)
            for y_i, y in enumerate(yvals, 1):
                line = hdr_row + y_i
                ws.write_number(line, 0, y, fm_int)
                for z_i, z in enumerate(zvals, 1):
                    current = {fixed: value, axis: y, series: z}
                    expected_row = by_combo.get((current['IBIAS'], current['SWCAP'], current['IND_CAP']))
                    cached = (_safe_numeric(expected_row.get(row_field))
                              if expected_row is not None else None)
                    # Each value is always resolved from Data, never a static chart copy.
                    criteria = [("B", current.get("IBIAS")), ("C", current.get("SWCAP")),
                                ("D", current.get("IND_CAP"))]
                    conditions = []
                    for code, _ in criteria:
                        if code == ccol[fixed]:
                            target_ref = "$B$6"
                        elif code == ccol[axis]:
                            target_ref = f"$A{line+1}"
                        else:
                            target_ref = f"{xl_col_to_name(z_i)}${hdr_row+1}"
                        conditions.extend([f"Data!${code}$2:${code}${data_end}", target_ref])
                    cond = ",".join(conditions)
                    status_filter = f",Data!$L$2:$L${data_end},\"PASS\""
                    data_rng = f"Data!${metrics_data_col[mkey]}$2:${metrics_data_col[mkey]}${data_end}"
                    formula = (f'=IF(COUNTIFS({cond}{status_filter})=0,"",'
                               f'SUMIFS({data_rng},{cond}{status_filter}))')
                    ws.write_formula(line, z_i, formula, fm_num, cached if cached is not None else "")
            if yvals and zvals:
                end_row = hdr_row + len(yvals)
                # For lower-is-better metrics: green for low; for frequency neutral blue scale.
                if mkey == "Freq_MHz":
                    colors = ("#E6F5FF", "#88C9ED", "#14628B")
                else:
                    colors = ("#BCE5C3", "#F9E7A0", "#F5B8A5")
                ws.conditional_format(hdr_row+1, 1, end_row, len(zvals),
                                      {"type": "3_color_scale", "min_color": colors[0],
                                       "mid_color": colors[1], "max_color": colors[2]})
                chart = book.add_chart({"type": "scatter", "subtype": "straight_with_markers"})
                for z_i, z in enumerate(zvals, 1):
                    chart.add_series({
                        "name": [name, hdr_row, z_i],
                        "categories": [name, hdr_row+1, 0, end_row, 0],
                        "values": [name, hdr_row+1, z_i, end_row, z_i],
                        "line": {"color": palette[(z_i-1) % len(palette)], "width": 1.8},
                        "marker": {"type": "circle", "size": 4},
                        "empty_cells": "gap",
                    })
                chart.set_title({"name": title})
                chart.set_x_axis({"name": f"{axis} Code", "major_gridlines": {"visible": False}})
                chart.set_y_axis({"name": title, "major_gridlines": {"visible": True,
                                "line": {"color": "#E2EDF4"}}})
                chart.set_legend({"position": "bottom", "font": {"size": 9}})
                chart.set_chartarea({"border": {"none": True}, "fill": {"color": "#FFFFFF"}})
                chart.set_plotarea({"border": {"none": True}})
                chart.set_size({"width": 655, "height": 310})
                ws.insert_chart(top+1, 9, chart, {"x_offset": 4, "y_offset": 2})
        # Keep the exact selector location the user is accustomed to: D162.
        ws.merge_range("A160:R160", f"TOP 30 | {fixed} fixed — full performance ranking", fm_title)
        ws.write("A162", "Fixed code:", fm_label)
        ws.write_formula("B162", "=$B$6", fm_input, value)
        ws.write("C162", "Rank by:", fm_label)
        ws.write("D162", "Jitter_fs", fm_input)
        ws.data_validation("D162", {"validate": "list", "source": RANK_METRICS})
        ws.merge_range("F162:R162", "Choose metric at D162; each row shows all metrics. Fewer than 30 available points remain blank.", fm_note)
        top_hdr = 164  # Excel row 165
        for j, head in enumerate(RANK_COLUMNS):
            ws.write(top_hdr, j, head, fm_col)
        for rank in range(1, 31):
            rr = top_hdr + rank
            ws.write_number(rr, 0, rank, fm_int)
            for jj in range(1, len(RANK_COLUMNS)):
                # Rank_Lists lookup is precomputed for all valid selector/metric combinations.
                lookup = (f'"{name}|"&$B$6&"|"&$D$162&"|"&$A{rr+1}')
                formula = f'=IFERROR(VLOOKUP({lookup},Rank_Lists!$A$2:$O${cache_end},{jj+1},FALSE),"")'
                key = f"{name}|{value}|Jitter_fs|{rank}"
                cache = rank_lookup.get(key)
                output_value = cache.get(cache_columns[jj]) if cache else None
                ws.write_formula(rr, jj, formula, fm_num if 5 <= jj <= 11 else fm_plain,
                                 output_value if output_value is not None else "")
        ws.autofilter(top_hdr, 0, top_hdr+30, len(RANK_COLUMNS)-1)
        ws.write("A198", "Ranking excludes failed/incomplete captures. PN@1kHz is flagged in Quality_Check for verification.", fm_note)

    # Global seven rank tables, 30 rows each, with all metrics on every row.
    opt = book.add_worksheet("Optimization_Top30")
    opt.set_tab_color("#C48B2B")
    opt.hide_gridlines(2)
    opt.set_zoom(80)
    opt.set_column("A:A", 9)
    opt.set_column("B:E", 12)
    opt.set_column("F:K", 17)
    opt.set_column("L:L", 15)
    opt.set_column("M:O", 13)
    opt.set_column("P:AA", 10)
    opt.freeze_panes(5, 0)
    opt.merge_range("A2:O3", "OPTIMIZATION | Full Performance TOP 30", fm_title)
    opt.merge_range("A4:O4", "Each ranking uses one metric but retains all six measured performance values and register codes.", fm_sub)
    ranking_names = {"Jitter_fs": "Lowest Jitter", "PN_1kHz": "Lowest PN @ 1 kHz",
                     "PN_10kHz": "Lowest PN @ 10 kHz", "PN_100kHz": "Lowest PN @ 100 kHz",
                     "PN_1MHz": "Lowest PN @ 1 MHz", "Frequency_Low": "Lowest Frequency",
                     "Frequency_High": "Highest Frequency"}
    for t, metric in enumerate(RANK_METRICS):
        start = 6 + t*35
        opt.merge_range(start, 0, start, 14, f"TOP 30  /  {ranking_names[metric]}", fm_sub)
        for j, name in enumerate(RANK_COLUMNS):
            opt.write(start+1, j, name, fm_col)
        subset = _rank_rows(all_pass, metric)
        for rank, r in enumerate(subset, 1):
            values = [rank, r.get("step"), r.get("ibias_dec"), r.get("swcap_dec"),
                      r.get("ind_cap_dec"), r.get("jitter_fs"), r.get("PN_1kHz"),
                      r.get("PN_10kHz"), r.get("PN_100kHz"), r.get("PN_1MHz"),
                      r.get("carrier_mhz"), r.get("output_power_dbm"),
                      r.get("reg20_read_hex"), r.get("reg21_read_hex"), r.get("reg22_read_hex")]
            for col, val in enumerate(values):
                if val is not None:
                    opt.write(start+1+rank, col, val, fm_num if 5 <= col <= 11 else fm_plain)
        opt.write(start+32, 0, f"Available ranked points: {len(subset)}", fm_small)
    # One compact global profile graph referencing real Data; global rank tables remain readable.
    for field, heading, at_row, c in [
        ("PN_1MHz", "PN @ 1 MHz vs measurement step", 8, "#147DA4"),
        ("Jitter_fs", "Jitter vs measurement step", 28, "#198C70")]:
        chart = book.add_chart({"type": "line"})
        chart.add_series({"name": heading,
                          "categories": ["Data", 1, 0, len(rows), 0],
                          "values": ["Data", 1, data_cols.index(field), len(rows), data_cols.index(field)],
                          "line": {"color": c, "width": 1.6}, "marker": {"type": "none"}})
        chart.set_title({"name": heading})
        chart.set_x_axis({"name": "Step"})
        chart.set_y_axis({"name": field})
        chart.set_legend({"none": True})
        chart.set_size({"width": 630, "height": 305})
        opt.insert_chart(at_row, 16, chart)

    # Simple first page: data quality and test setup summaries.
    start = book.add_worksheet("Start_Here")
    start.activate()
    start.set_first_sheet()
    start.set_tab_color(navy)
    start.hide_gridlines(2)
    start.set_column("A:A", 4)
    start.set_column("B:D", 21)
    start.set_column("E:J", 18)
    start.merge_range("B2:J3", "CMOS AUTO-TEST | SAW Oscillator Performance", fm_title)
    start.merge_range("B5:J5", "IBIAS × SWCAP × IND_CAP | 6 metrics | Fixed-code charts + full Top 30", fm_sub)
    state_ok = len(all_pass)
    for rowno, label, val in [(7,"Planned combinations",len(rows)),
                              (9,"Successful captures",state_ok),
                              (11,"Failed/incomplete",len(rows)-state_ok)]:
        start.write(rowno, 1, label, fm_label)
        start.write(rowno, 4, val, fm_kpi)
    for rowno, label, key, unit, fn in [
        (14,"Best Jitter", "jitter_fs", "fs", min),
        (16,"Lowest PN@1MHz", "PN_1MHz", "dBc/Hz", min),
        (18,"Min Frequency", "carrier_mhz", "MHz", min),
        (20,"Max Frequency", "carrier_mhz", "MHz", max)]:
        vals = [_safe_numeric(r.get(key)) for r in all_pass]
        vals = [v for v in vals if v is not None]
        start.write(rowno, 1, label, fm_label)
        if vals:
            start.write_number(rowno, 4, fn(vals), fm_kpi)
            start.write(rowno, 5, unit, fm_small)
    start.merge_range("B24:J24", "WORKBOOK MAP", fm_sub)
    for rr, title, content in [
        (26,"Fixed_IBIAS", "Fixed IBIAS: SWCAP × IND_CAP; heatmaps, curves, metric Top 30"),
        (28,"Fixed_SWCAP", "Fixed SWCAP: IBIAS × IND_CAP; heatmaps, curves, metric Top 30"),
        (30,"Fixed_IND", "Fixed IND_CAP: IBIAS × SWCAP; heatmaps, curves, metric Top 30"),
        (32,"Optimization_Top30", "Seven global rankings, each row contains all six metrics"),
        (34,"Data / Summary", "Plot-ready values / unchanged original exporter columns"),
        (36,"Quality_Check", "Capture status, incomplete points, suspected PN@1kHz extraction issue"),
    ]:
        start.write(rr, 1, title, fm_label)
        start.merge_range(rr, 3, rr, 9, content, fm_small)
    start.merge_range("B40:J41", "WARNING: PN@1kHz vs PN@100Hz should be verified against raw E5052B traces before publication.", fm_warning)

    quality = book.add_worksheet("Quality_Check")
    quality.hide_gridlines(2)
    quality.set_column("A:A", 4)
    quality.set_column("B:B", 38)
    quality.set_column("C:C", 22)
    quality.set_column("D:H", 19)
    quality.merge_range("B2:H3", "DATA QUALITY | Measurement Validity", fm_title)
    both = [(r.get("PN_100Hz"), r.get("PN_1kHz")) for r in all_pass]
    both = [(float(x), float(y)) for x,y in both if _safe_numeric(x) is not None and _safe_numeric(y) is not None]
    repeat_1k = bool(both) and all(x == y for x, y in both)
    for ri, lbl, vv in [(5,"Total attempted",len(rows)), (7,"SPI+PN PASS",len(all_pass)),
                        (9,"Incomplete/failed",len(rows)-len(all_pass)),
                        (11,"Expected scan points",len(a_values)*len(b_values)*len(c_values)),
                        (13,"PN@1kHz = PN@100Hz for all valid pairs", "YES - CHECK" if repeat_1k else "NO / MIXED")]:
        quality.write(ri, 1, lbl, fm_label)
        quality.write(ri, 2, vv, fm_err if ri == 13 and repeat_1k else fm_plain)
    quality.merge_range("B17:H19", "The instrument can return a formally valid trace while using an incorrect carrier, stale sweep, or low signal. Confirm acquisition settings before drawing conclusions.", fm_note)
    quality.merge_range("B22:H24", "Ranking excludes failed captures. Frequency rankings show both highest and lowest; frequency itself is not judged 'better'.", fm_note)
    missing = [r for r in rows if r.get('capture_status') != 'PASS']
    quality.write("B27", "Failed/incomplete steps", fm_sub)
    for i, r in enumerate(missing[:40],28):
        quality.write(i, 1, r.get('step'))
        quality.write(i, 2, f"IBIAS={r['ibias_dec']} SWCAP={r['swcap_dec']} IND={r['ind_cap_dec']}")
        quality.write(i, 3, r.get('error_message', ''))

    info = book.add_worksheet("Test_Info")
    info.hide_gridlines(2)
    info.set_column("A:A", 4)
    info.set_column("B:B", 32)
    info.set_column("C:H", 25)
    info.merge_range("B2:H3", "TEST INFO | Acquisition Conditions", fm_title)
    metadata = {}
    for filename in ("run_plan.json", "initial_register_snapshot.json"):
        fp = out_dir / filename
        if fp.exists():
            try:
                metadata[filename] = json.loads(fp.read_text(encoding='utf-8'))
            except Exception:
                metadata[filename] = {}
    plan = metadata.get('run_plan.json', {})
    snapshot = metadata.get('initial_register_snapshot.json', {})
    it = [
        ("Case", CASE_NAME), ("Timestamp", datetime.now().isoformat(timespec='seconds')),
        ("IBIAS sequence", ", ".join(map(str, a_values))),
        ("SWCAP sequence", ", ".join(map(str, b_values))),
        ("IND_CAP sequence (P=N)", ", ".join(map(str, c_values))),
        ("Total planned", len(a_values)*len(b_values)*len(c_values)),
        ("Successful captures", len(all_pass)),
        ("Settle wait (s)", plan.get('settle_s', '')), ("Acquire wait (s)", plan.get('acquire_s','')),
        ("E5052B host", plan.get('instrument_host','')),
        ("Screenshot enabled", str(plan.get('save_screenshot', ''))),
        ("REG20 initial", snapshot.get('REG20_hex','')),
        ("REG21 initial", snapshot.get('REG21_hex','')),
        ("REG22 initial", snapshot.get('REG22_hex','')),
        ("Jitter integral range (Hz)", (
            f"{all_pass[0].get('integral_start_hz', '')} - {all_pass[0].get('integral_stop_hz', '')}"
            if all_pass else '')),
        ("Chip/PCB ID", "FILL MANUALLY"),
    ]
    for i, (key, val) in enumerate(it, 5):
        info.write(i, 1, key, fm_label)
        info.write(i, 2, val)

    pcb = book.add_worksheet("PCB_Compare_Template")
    pcb.hide_gridlines(2)
    pcb.set_column("A:Q", 15)
    pcb.merge_range("A2:Q3", "MULTI-BOARD COMPARISON | Future PCB01–PCB07", fm_title)
    pcb.merge_range("A5:Q5", "Append consistent summary records from every PCB and compare identical register combinations.", fm_sub)
    pcb_cols = ["PCB_ID", "Chip_ID", "Resonator_ID", "Step", "IBIAS", "SWCAP", "IND_CAP",
                "Jitter_fs", "PN_1kHz", "PN_10kHz", "PN_100kHz", "PN_1MHz",
                "Freq_MHz", "Power_dBm", "SPI_Status", "PN_Status", "Timestamp"]
    for j, key in enumerate(pcb_cols):
        pcb.write(7, j, key, fm_col)
    pcb.freeze_panes(8, 4)
    pcb.write("A10", "Template only; not populated with fabricated PCB measurements.", fm_note)



def save_summary_xlsx(out_dir: Path, rows: list[dict[str, Any]],
                      trace_long_csv: Path, a_values: list[int], b_values: list[int],
                      c_values: list[int], *, output_name: str = "summary_ibias_swcap_indcap.xlsx") -> Path:
    """Keep Summary/maps/Trace_Long and add the selected fixed-parameter/Top30 analytics."""
    import xlsxwriter

    path = out_dir / output_name
    book = xlsxwriter.Workbook(str(path))
    try:
        hdr = book.add_format({"bold": True, "font_color": "white", "bg_color": "#183756",
                               "border": 1, "align": "center"})
        num = book.add_format({"num_format": "0.000000"})
        err = book.add_format({"font_color": "#B91C1C"})
        sheet = book.add_worksheet("Summary")
        sheet.freeze_panes(1, 4)
        sheet.autofilter(0, 0, max(1, len(rows)), len(SUMMARY_FIELDS)-1)
        sheet.set_column(0, 0, 8)
        sheet.set_column(1, 5, 15)
        sheet.set_column(6, len(SUMMARY_FIELDS)-2, 21)
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

        by_combo = {(int(r["ibias_dec"]), int(r["swcap_dec"]), int(r["ind_cap_dec"])): r
                    for r in rows}
        for cap in c_values:
            for prefix, field in (("PN_1MHz", "PN_1MHz"), ("Freq_MHz", "carrier_mhz")):
                ws = book.add_worksheet(f"{prefix}_IND{cap}")
                ws.freeze_panes(1, 1)
                ws.set_column(0, 0, 18)
                ws.set_column(1, len(b_values), 14)
                ws.write(0, 0, f"IBIAS / SWCAP (IND={cap})", hdr)
                for j, swcap in enumerate(b_values, 1):
                    ws.write(0, j, swcap, hdr)
                for i, ibias in enumerate(a_values, 1):
                    ws.write(i, 0, ibias, hdr)
                    for j, swcap in enumerate(b_values, 1):
                        value = by_combo.get((ibias, swcap, cap), {}).get(field)
                        if isinstance(value, (int, float)) and math.isfinite(value):
                            ws.write_number(i, j, value, num)
                if a_values and b_values:
                    ws.conditional_format(1, 1, len(a_values), len(b_values), {"type": "3_color_scale"})

        add_analytics_sheets(book, rows, a_values, b_values, c_values, out_dir)

        wsl = book.add_worksheet("Trace_Long")
        headers = ["step", "ibias_dec", "swcap_dec", "ind_cap_dec",
                   "ind_p_dec", "ind_n_dec", "offset_hz", "phase_noise_dbc_hz"]
        for col, name in enumerate(headers):
            wsl.write(0, col, name, hdr)
        wsl.freeze_panes(1, 0)
        wsl.set_column(0, len(headers)-1, 19)
        with trace_long_csv.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for i, rec in enumerate(reader, 1):
                if i > 1_048_575:
                    emit(("[NOTE]", "gray"), " Trace_Long exceeds Excel row limit; full trace retained in CSV")
                    break
                for j, key in enumerate(headers):
                    wsl.write_number(i, j, float(rec[key]))
    finally:
        book.close()
    return path


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def create_unique_run_dir(base_dir: Path) -> Path:
    """Keep original run_YYYYMMDD_HHMMSS layout; do not overwrite same-second runs."""
    base_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for index in range(1, 1000):
        suffix = "" if index == 1 else f"_{index:02d}"
        candidate = base_dir / f"run_{stamp}{suffix}"
        try:
            candidate.mkdir(exist_ok=False)
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError("Unable to create a unique run directory")


def ensure_original_output_tree(run_dir: Path) -> None:
    """Keep exactly the original four capture subdirectories."""
    for name in ("merged", "screenshots", "summary", "traces"):
        (run_dir / name).mkdir(parents=True, exist_ok=True)


def check_capture_files(result: Any, options: Any) -> None:
    """Requested measurement artifacts must really exist, not just report a path."""
    requested = [("raw trace CSV", getattr(options, "save_csv", False), "raw_csv_path"),
                 ("point Excel", getattr(options, "save_excel", False), "excel_path"),
                 ("screenshot", getattr(options, "save_screenshot", False), "screenshot_path")]
    for name, enabled, attr in requested:
        if not enabled:
            continue
        filename = getattr(result, attr, None)
        if not filename or not Path(filename).is_file():
            raise RuntimeError(f"Required {name} was not saved: {filename or '<no path returned>'}")


def run_sweep(chip: Any, inst: Any, points: list[ScanPoint], out_dir: Path,
              capture_fn: Callable[..., Any], capture_options: Any, *,
              settle_s: float, acquisition_s: float, restore: bool = True,
              min_carrier_dbm: float | None = None,
              freq_min_mhz: float | None = None, freq_max_mhz: float | None = None) -> dict[str, Any]:
    """Run on already-open devices; injection-friendly for offline fake-device tests."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ensure_original_output_tree(out_dir)
    snapshot = {"REG20": chip.read_reg(REG20), "REG21": chip.read_reg(REG21),
                "REG22": chip.read_reg(REG22)}
    write_json(out_dir / "initial_register_snapshot.json", {
        "capture_local_time": datetime.now().isoformat(timespec="seconds"),
        "REG20_hex": f"0x{snapshot['REG20']:02X}",
        "REG21_hex": f"0x{snapshot['REG21']:02X}",
        "REG20_dec": snapshot["REG20"],
        "REG21_dec": snapshot["REG21"],
        "REG22_hex": f"0x{snapshot['REG22']:02X}",
        "REG22_dec": snapshot["REG22"],
        "notes": "Actual silicon readback; no default-register initialization performed",
    })
    emit(("[SNAPSHOT]", "cyan"), f" REG20=0x{snapshot['REG20']:02X}, "
         f"REG21=0x{snapshot['REG21']:02X}, REG22=0x{snapshot['REG22']:02X}")
    started_at = time.monotonic()
    rows: list[dict[str, Any]] = []
    status = "PASS"
    error: BaseException | None = None
    restore_error: Exception | None = None
    a_values = sorted(set(p.ibias for p in points))
    b_values = sorted(set(p.swcap for p in points))
    c_values = sorted(set(p.ind_cap for p in points))
    trace_long_csv = out_dir / "all_traces_long.csv"
    summary_csv = out_dir / "summary_ibias_swcap_indcap.csv"

    with summary_csv.open("w", encoding="utf-8-sig", newline="") as sf, \
         trace_long_csv.open("w", encoding="utf-8-sig", newline="") as lf:
        swriter = csv.DictWriter(sf, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
        lwriter = csv.writer(lf)
        swriter.writeheader()
        lwriter.writerow(["step", "ibias_dec", "swcap_dec", "ind_cap_dec",
                         "ind_p_dec", "ind_n_dec", "offset_hz", "phase_noise_dbc_hz"])
        sf.flush()
        lf.flush()
        try:
            for p in points:
                row = result_row(p)
                rows.append(row)
                reg_log: dict[int, tuple[int, int | None]] = {}
                show_step_start(p, len(points), started_at)
                try:
                    new20, new21, new22 = make_register_values(
                        chip, snapshot["REG20"], snapshot["REG21"], snapshot["REG22"],
                        p.ibias, p.swcap, p.ind_cap)
                    row["reg20_written_hex"] = f"0x{new20:02X}"
                    row["reg21_written_hex"] = f"0x{new21:02X}"
                    row["reg22_written_hex"] = f"0x{new22:02X}"
                    def verified(addr: int, expected: int, actual: int) -> None:
                        reg_log[addr] = (expected, actual)

                    r20, r21, r22 = write_point(
                        chip, new20, new21, new22, on_verified=verified)
                    row["reg20_read_hex"] = f"0x{r20:02X}"
                    row["reg21_read_hex"] = f"0x{r21:02X}"
                    row["reg22_read_hex"] = f"0x{r22:02X}"
                    row["spi_verify"] = "PASS"
                    show_registers(reg_log, success=True)
                    if settle_s:
                        time.sleep(settle_s)
                    # Ask the instrument to resume/restart its measurement after configuration.
                    # The explicit acquisition wait MUST be tuned to its actual sweep/averaging time.
                    inst.resume_display()
                    if acquisition_s:
                        time.sleep(acquisition_s)
                    capture_options.delay_before_capture_s = 0.0
                    basename = (f"step{p.step:03d}_IBIAS{p.ibias:02d}_"
                                f"SWCAP{p.swcap:02d}_IND{p.ind_cap:02d}")
                    try:
                        result = capture_fn(
                            client=inst, options=capture_options, out_dir=out_dir,
                            shot_name=basename, case_name=CASE_NAME, step_idx=p.step-1,
                            field_names=[IBIAS_NAME, SWCAP_NAME, IND_P_NAME, IND_N_NAME],
                            active_values={IBIAS_NAME: p.ibias, SWCAP_NAME: p.swcap,
                                           IND_P_NAME: p.ind_cap, IND_N_NAME: p.ind_cap},
                        )
                    finally:
                        # Existing capture implementation can leave the instrument frozen on exceptions.
                        if capture_options.freeze_before_capture:
                            inst.resume_display()
                    validate_capture(result, min_carrier_dbm=min_carrier_dbm,
                                     freq_min_mhz=freq_min_mhz, freq_max_mhz=freq_max_mhz)
                    check_capture_files(result, capture_options)
                    attach_capture(row, result)
                    append_trace_long(lwriter, lf, p, result)
                    show_phase_noise(row)
                except BaseException as exc:
                    status = "ABORTED" if isinstance(exc, KeyboardInterrupt) else "FAIL"
                    row["capture_status"] = "ABORTED" if isinstance(exc, KeyboardInterrupt) else "FAIL"
                    row["spi_verify"] = "FAIL" if row["spi_verify"] != "PASS" else "PASS"
                    row["error_message"] = f"{type(exc).__name__}: {exc}"
                    if row['spi_verify'] != 'PASS':
                        if isinstance(exc, SPIReadbackError):
                            reg_log[exc.addr] = (exc.expected, exc.actual)
                        show_registers(reg_log, success=False)
                        emit(("[SPI ERROR] ", "red"), (row["error_message"], "red"), err=True)
                        emit(("PN Capture : SKIPPED_SPI_ERROR", "red"))
                    else:
                        emit(("[PN ERROR] ", "red"), (row["error_message"], "red"), err=True)
                    emit(("[SCAN STOP] ", "red"),
                         (f"Step {p.step}; remaining {len(points)-p.step} points skipped", "red"), err=True)
                    error = exc
                finally:
                    swriter.writerow(row)
                    sf.flush()
                    if row.get('capture_status') == 'PASS':
                        show_saved(row)
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
                emit(("[WARNING] ", "red"), "--no-restore: chip remains at last written configuration")
            try:
                summary_xlsx = save_summary_xlsx(out_dir, rows, trace_long_csv, a_values, b_values, c_values)
                emit(("[EXCEL PASS] ", "green"), str(summary_xlsx))
            except Exception as exc:
                status = "FAIL"
                if error is None:
                    error = exc
                emit(("[EXCEL ERROR] ", "red"), (str(exc), "red"), err=True)
            write_json(out_dir / "run_result.json", {
                "status": status, "completed_points": sum(r.get('capture_status') == 'PASS' for r in rows),
                "planned_points": len(points), "restore_requested": restore,
                "restore_result": "FAIL" if restore_error else "PASS" if restore else "SKIPPED",
                "error": str(error) if error else None,
                "restore_error": str(restore_error) if restore_error else None,
                "summary_csv": str(summary_csv), "long_csv": str(trace_long_csv),
            })
    emit((f"[CASE {status}]", "green" if status == "PASS" else "red"),
         f" completed {sum(r.get('capture_status')=='PASS' for r in rows)}/{len(points)}"
         f" | Elapsed={elapsed_text(time.monotonic()-started_at)}")
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
    print(f"IND_CAP values (P=N): {list(dict.fromkeys(p.ind_cap for p in points))}")
    print(f"Total combinations: {len(points)} (IBIAS outer, SWCAP middle, IND_CAP inner)")
    print("step,IBIAS_DEC,SWCAP_DEC,IND_P_DEC,IND_N_DEC")
    for p in points:
        print(f"{p.step:03d},{p.ibias},{p.swcap},{p.ind_cap},{p.ind_cap}")
    print("[PLAN ONLY] No instruments or SPI devices opened, no chip writes")


def regenerate_report_from_existing(run_dir: Path) -> Path:
    """Offline test: reuse an existing sweep CSV and never access SPI/E5052B."""
    src = run_dir / "summary_ibias_swcap_indcap.csv"
    trace = run_dir / "all_traces_long.csv"
    if not src.is_file() or not trace.is_file():
        raise FileNotFoundError(f"Expected {src} and {trace}")
    integer_fields = {"step", "ibias_dec", "swcap_dec", "ind_cap_dec",
                      "ind_p_dec", "ind_n_dec"}
    numeric_fields = set(integer_fields) | {
        "carrier_hz", "carrier_mhz", "output_power_dbm", "jitter_fs", "rms_rad",
        "integral_start_hz", "integral_stop_hz", "integrated_phase_noise_dbc",
        "residual_fm_hz",
    } | {x for x in SUMMARY_FIELDS if x.startswith("PN_")}
    records = []
    with src.open(encoding="utf-8-sig", newline="") as handle:
        for rec in csv.DictReader(handle):
            for k in numeric_fields:
                v = rec.get(k)
                if v is not None and v.strip() != "":
                    rec[k] = int(v) if k in integer_fields else float(v)
                elif v == "":
                    rec[k] = None
            records.append(rec)
    if not records:
        raise RuntimeError("Summary CSV has no records")
    aa = sorted(set(int(r["ibias_dec"]) for r in records))
    bb = sorted(set(int(r["swcap_dec"]) for r in records))
    cc = sorted(set(int(r["ind_cap_dec"]) for r in records))
    return save_summary_xlsx(
        run_dir, records, trace, aa, bb, cc,
        output_name="summary_ibias_swcap_indcap_v2_preview.xlsx")


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="IBIAS × SWCAP × IND_CAP(P=N) sweep with E5052B acquisition")
    # No command-line arguments means an actual full sweep, by explicit user choice.
    action = parser.add_mutually_exclusive_group(required=False)
    action.add_argument("--plan", action="store_true", help="Print plan only; never access hardware")
    action.add_argument("--check-point", action="store_true", help="Real hardware, one baseline point IBIAS=15 SWCAP=7 IND_P=N=3")
    action.add_argument("--run", action="store_true", help="Real hardware, full sweep")
    action.add_argument("--report-only", metavar="RUN_DIR", help="Rebuild new Excel from old CSV; no hardware access")
    parser.add_argument("--settle-s", type=float, default=2.0, help="Wait for oscillator after SPI configuration")
    parser.add_argument("--acquire-s", type=float, default=12.0, help="Wait for NEW E5052B sweep/averaging; tune to actual instrument")
    parser.add_argument("--screenshot", dest="screenshot", action="store_true", default=True,
                        help="Save instrument screenshot for each point (default ON)")
    parser.add_argument("--no-screenshot", dest="screenshot", action="store_false",
                        help="Disable per-point screenshots")
    parser.add_argument("--point-excel", dest="point_excel", action="store_true", default=True,
                        help="Save an individual XLSX for each point (default ON)")
    parser.add_argument("--no-point-excel", dest="point_excel", action="store_false",
                        help="Disable per-point XLSX files")
    parser.add_argument("--no-restore", action="store_true", help="Do not restore snapshot (NOT recommended)")
    parser.add_argument("--min-carrier-dbm", type=float, default=None, help="Optional minimum acceptable E5052B carrier power")
    parser.add_argument("--freq-min-mhz", type=float, default=None, help="Optional minimum acceptable carrier frequency")
    parser.add_argument("--freq-max-mhz", type=float, default=None, help="Optional maximum acceptable carrier frequency")
    parser.add_argument("--no-color", action="store_true", help="Disable colored terminal output")
    parser.add_argument("--output-dir", default=f"outputs/fullflow/{CASE_NAME}")
    args = parser.parse_args(argv)
    initialize_colors(disable_color=args.no_color)
    if args.settle_s < 0 or args.acquire_s < 0:
        parser.error("--settle-s and --acquire-s must be non-negative")
    if args.freq_min_mhz is not None and args.freq_max_mhz is not None and args.freq_min_mhz >= args.freq_max_mhz:
        parser.error("--freq-min-mhz must be less than --freq-max-mhz")

    if args.report_only:
        try:
            generated = regenerate_report_from_existing(Path(args.report_only))
        except Exception as exc:
            emit(("[REPORT ERROR] ", "red"), (f"{type(exc).__name__}: {exc}", "red"), err=True)
            return 1
        emit(("[REPORT PASS] ", "green"), str(generated))
        emit("No Ginkgo or E5052B connection; original Excel and CSV were not overwritten.")
        return 0

    points = ([ScanPoint(1, 15, 7, 3)] if args.check_point else scan_points())
    if args.plan:
        plan_only(points)
        return 0

    # Only real hardware actions import Windows-specific Ginkgo DLL.
    from protocol.chip_spi import ChipSpi
    from instruments.e5052b.capture import capture_phase_noise_once
    from scripts.fullflow.common import build_capture_options, make_client_from_config
    from utils.e5052b_config import load_e5052b_config
    # Run folders still use the original hierarchy / name convention.

    cfg = load_e5052b_config()
    options = build_capture_options(cfg, save_screenshot=args.screenshot)
    options.save_screenshot = args.screenshot
    options.save_csv = True
    options.save_excel = args.point_excel
    options.freeze_before_capture = True
    options.resume_after_capture = True
    run_dir = create_unique_run_dir(Path(args.output_dir))
    ensure_original_output_tree(run_dir)
    write_json(run_dir / "run_plan.json", {
        "case": CASE_NAME, "points": [vars(p) for p in points],
        "settle_s": args.settle_s, "acquire_s": args.acquire_s,
        "save_screenshot": args.screenshot, "save_point_excel": args.point_excel,
        "restore": not args.no_restore,
        "min_carrier_dbm": args.min_carrier_dbm,
        "freq_min_mhz": args.freq_min_mhz, "freq_max_mhz": args.freq_max_mhz,
        "instrument_host": cfg['host'], "instrument_port": cfg.get('port', 5025),
        "note": "Endpoint-inclusive sweeps; no initialization; real snapshot before first write",
    })
    global LOG_HANDLE
    LOG_HANDLE = (run_dir / "run_log.txt").open("w", encoding="utf-8")
    emit(("[RUN DIR] ", "cyan"), str(run_dir))
    emit(("[CONFIG] ", "cyan"), f"{len(points)} combinations; settle={args.settle_s}s, acquisition={args.acquire_s}s")
    emit(("[OUTPUT] ", "cyan"), "Original run layout preserved: merged/ screenshots/ summary/ traces/")
    emit(("[FILES] ", "cyan"), f"screenshot={'ON' if args.screenshot else 'OFF'}; "
         f"point XLSX={'ON' if args.point_excel else 'OFF'}; CSV/JSON/summary XLSX=ON")
    emit(("[WARNING] ", "yellow"), "Check actual E5052B sweep/average time before the full scan")
    emit(("[WARNING] ", "yellow"), "IBIAS=0 or other settings may cause oscillation to stop; the first failed capture aborts")
    try:
        with make_client_from_config(cfg) as inst:
            emit(("[E5052B] ", "cyan"), str(inst.identify()))
            with ChipSpi() as chip:
                run_sweep(chip, inst, points, run_dir, capture_phase_noise_once, options,
                          settle_s=args.settle_s, acquisition_s=args.acquire_s,
                          restore=not args.no_restore,
                          min_carrier_dbm=args.min_carrier_dbm,
                          freq_min_mhz=args.freq_min_mhz, freq_max_mhz=args.freq_max_mhz)
    except KeyboardInterrupt:
        emit(("[ABORTED] ", "red"), "Ctrl+C; restore attempted if chip was connected and snapshot was available")
        if LOG_HANDLE is not None:
            LOG_HANDLE.close()
            LOG_HANDLE = None
        return 130
    except Exception as exc:
        emit(("[ERROR] ", "red"), (f"{type(exc).__name__}: {exc}", "red"), err=True)
        if LOG_HANDLE is not None:
            LOG_HANDLE.close()
            LOG_HANDLE = None
        return 1
    emit(("[PASS] ", "green"), "Ready for Excel plotting")
    if LOG_HANDLE is not None:
        LOG_HANDLE.close()
        LOG_HANDLE = None
    return 0


if __name__ == "__main__":
    sys.exit(cli())
