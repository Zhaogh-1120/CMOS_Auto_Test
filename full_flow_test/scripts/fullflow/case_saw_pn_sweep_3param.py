"""SAW OSC IBIAS × SWCAP × IND_CAP phase-noise sweep for CMOS_Auto_Test v0.2.0.

Run from full_flow_test directory:
  python -m scripts.fullflow.case_saw_pn_sweep_3param
  python -m scripts.fullflow.case_saw_pn_sweep_3param --plan
  python -m scripts.fullflow.case_saw_pn_sweep_3param --check-point

DEFAULT WITH NO ARGUMENTS: user-configured TEST_MODE (initially 48-point sweep)
with individual screenshots,
individual Excel reports, raw trace CSVs and analysis summary Excel.
All files remain under outputs/fullflow/case_saw_pn_sweep_3param/run_*/.
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
from utils.terminal_links import emit_path_link, emit_run_file_links

# ============================================================================
# USER TEST CONFIGURATION  <== ONLY EDIT THIS SECTION FOR DAILY EXPERIMENTS
# ============================================================================
# Changing this configuration NEVER writes any default initialization registers.
# No-argument launch uses TEST_MODE. PLAN_ONLY and CLI --report-only do not open hardware.
# The original run_YYYYMMDD_HHMMSS output hierarchy is preserved.
#
# 1) BOARD / EXPERIMENT METADATA (recorded, NOT acquired from instruments)
PCB_ID = "PCB01"
CHIP_ID = "CHIP01"
SAW_ID = "SAW01"
TEST_NAME = "SAW_PN_SWEEP_3PARAM"
TEST_NOTE = "Room-temperature characterization"
TEST_OPERATOR = ""                         # Optional
TEST_TEMPERATURE_C = None               # Enter measured/known value, e.g. 25.0
TEST_VDD_V = None                       # Enter measured/known VDD, e.g. 1.8

# 2) SCAN SETTINGS: RANGE = (start, stop, step), LIST = arbitrary explicit codes.
# RANGE always includes BOTH endpoints even if the step misses the stop.
# Three nested loops: IBIAS outer -> SWCAP middle -> IND_CAP inner (IND_P=N).
IBIAS_MODE = "RANGE"                    # "RANGE" or "LIST"
IBIAS_RANGE = (0, 31, 15)
IBIAS_LIST = [0, 15, 30, 31]
SWCAP_MODE = "RANGE"
SWCAP_RANGE = (0, 15, 7)
SWCAP_LIST = [0, 7, 14, 15]
IND_CAP_MODE = "RANGE"
IND_CAP_RANGE = (0, 7, 4)
IND_CAP_LIST = [0, 4, 7]
ACTIVE_SCAN_FIELDS = ("IBIAS", "SWCAP", "IND_CAP")  # Registers modified by 3Param
# IND_P and IND_N both live in REG06 and are ALWAYS synchronized by this case.

# 3) EXECUTION: no CLI options necessary. Supported modes below.
TEST_MODE = "FULL_SWEEP"                 # FULL_SWEEP / CHECK_POINT / PLAN_ONLY
CHECK_POINT_CODES = (15, 7, 4)          # IBIAS, SWCAP, IND_CAP (P=N)
SETTLE_TIME_S = 2.0                     # Wait after SPI verification
ACQUIRE_TIME_S = 12.0                   # Wait for E5052B after resume
# E5052B completion is NOT polled; confirm this wait is sufficient in practice.

# 4) MEASUREMENT / VALIDITY
E5052B_HOST_OVERRIDE = None             # None = use config/instrument/e5052b_config.json
MIN_CARRIER_DBM = None                  # e.g. -50.0; None disables threshold
FREQ_MIN_MHZ = None                     # e.g. 3400.0; None disables threshold
FREQ_MAX_MHZ = None                     # e.g. 3550.0; None disables threshold
# PN offsets and jitter integration are read from capture results, NOT forced
# via SCPI by this script. No fake measurement or undocumented SCPI reconfig.

# 5) OUTPUT FILES; directory structure stays the same as v3
SAVE_SCREENSHOT = True                 # Every point PNG in screenshots/
SAVE_POINT_EXCEL = True                # Every point XLSX in summary/
# Raw per-point CSV, all_traces_long.csv, summary CSV, summary Excel,
# run_plan.json, run_result.json, initial snapshot and run_log.txt are mandatory.
RESTORE_REGISTERS = True               # Best effort + readback verify
TERMINAL_COLOR = True                  # PASS green / ERROR red / Write blue / Read yellow
OUTPUT_BASE_DIR = "outputs/fullflow/case_saw_pn_sweep_3param"

# 6) ANALYTICS WORKBOOK
TOP_N = 30                             # Global and per-fixed-condition rankings
DEFAULT_FIXED_IBIAS = 15               # Initial Fixed_IBIAS chart selector
DEFAULT_FIXED_SWCAP = 7               # Initial Fixed_SWCAP chart selector
DEFAULT_FIXED_IND_CAP = 4             # Initial Fixed_IND chart selector
# Report includes Data, Original_Summary, 3 Fixed sheets, optimization rankings,
# quality checks and Test_Info; long raw trace remains in all_traces_long.csv.

# Additional PN report (read-only postprocessing; DOES NOT remeasure).
GENERATE_PN_COMPARISON = True          # New pn_comparison.xlsx, original Summary stays unchanged
PN_GALLERY_COLUMNS = 2                # Two original PNG screenshots per gallery row

# 7) ADVANCED: optional read-only retry after mismatch; no automatic re-write.
SPI_READ_RETRY = 0                     # 0 preserves original fail-fast behavior

# ============================================================================
# END USER TEST CONFIGURATION - DO NOT EDIT LOW-LEVEL SPI BELOW
# ============================================================================

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
    for addr in (REG07, REG05, REG06):
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
    """Print per-point saved files as links; keep the run log escape-free."""
    emit(("[SAVE PASS]", "green"))
    emit("Summary CSV : Updated")
    raw = row.get("raw_csv_path")
    if raw:
        emit_path_link("Raw PN", raw, log_handle=LOG_HANDLE)
    else:
        emit("Raw PN      : Not available")
    screenshot = row.get("screenshot_path")
    if screenshot:
        scr = Path(str(screenshot))
        if scr.is_file():
            emit_path_link("Screenshot", scr, log_handle=LOG_HANDLE)
        else:
            emit(f"Screenshot  : Path returned (verify file): {scr.name}")
    else:
        emit("Screenshot  : Not requested / unavailable")
    if row.get("point_excel_path"):
        emit_path_link("Point Excel", row["point_excel_path"], log_handle=LOG_HANDLE)
    emit(("[STEP PASS]", "green"))


class SPIReadbackError(RuntimeError):
    def __init__(self, addr: int, expected: int, actual: int):
        self.addr, self.expected, self.actual = addr, expected, actual
        super().__init__(f"SPI VERIFY FAIL REG{addr:02X}: expected 0x{expected:02X}, got 0x{actual:02X}")


CASE_NAME = "case_saw_pn_sweep_3param"
IBIAS_NAME = "CFG_OSC_IDAC_IBIAS"
SWCAP_NAME = "CFG_OSC_SWCAP"
IND_P_NAME = "CFG_OSC_IND_SWCAP_P"
IND_N_NAME = "CFG_OSC_IND_SWCAP_N"
REG07 = 0x07
REG05 = 0x05
REG06 = 0x06

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

def configured_codes(mode: str, bounds: tuple[int, int, int],
                     explicit: list[int], *, max_code: int, field: str) -> list[int]:
    """Validate user settings BEFORE opening any hardware connection."""
    mode = mode.upper()
    if mode == "RANGE":
        if len(bounds) != 3 or any(type(v) is not int for v in bounds):
            raise ValueError(f"{field}: RANGE must be (int start, int stop, int step)")
        codes = inclusive_values(*bounds)
    elif mode == "LIST":
        if not isinstance(explicit, (list, tuple)) or not explicit:
            raise ValueError(f"{field}: LIST must have at least one element")
        codes = list(explicit)
    else:
        raise ValueError(f"{field}: MODE must be RANGE or LIST, got {mode!r}")
    if any(type(v) is not int or not 0 <= v <= max_code for v in codes):
        raise ValueError(f"{field}: every code must be an integer in 0..{max_code}; got {codes}")
    if len(codes) != len(set(codes)):
        raise ValueError(f"{field}: repeated control codes are not allowed: {codes}")
    return codes


def scan_sequences() -> tuple[list[int], list[int], list[int]]:
    return (configured_codes(IBIAS_MODE, IBIAS_RANGE, IBIAS_LIST, max_code=31, field="IBIAS"),
            configured_codes(SWCAP_MODE, SWCAP_RANGE, SWCAP_LIST, max_code=15, field="SWCAP"),
            configured_codes(IND_CAP_MODE, IND_CAP_RANGE, IND_CAP_LIST, max_code=7, field="IND_CAP"))


# For legacy callers that referenced these public constants, current defaults
# are retained. Runtime scans always call scan_sequences() for fresh settings.
DEFAULT_IBIAS, DEFAULT_SWCAP, DEFAULT_IND_CAP = scan_sequences()

SUMMARY_FIELDS = [
    "step", "ibias_dec", "swcap_dec", "ind_cap_dec",
    "ind_p_dec", "ind_n_dec", "reg07_written_hex", "reg05_written_hex",
    "reg06_written_hex", "reg07_read_hex", "reg05_read_hex", "reg06_read_hex", "spi_verify", "capture_status",
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
    a_codes, b_codes, c_codes = scan_sequences()
    return [ScanPoint(i + 1, a, b, c) for i, (a, b, c) in enumerate(
        (x, y, z) for x in a_codes for y in b_codes for z in c_codes
    )]


def make_register_values(chip: Any, before07: int, before05: int, before06: int,
                         ibias: int, swcap: int, ind_cap: int) -> tuple[int, int, int]:
    """Build REG07 (IBIAS), REG05 (SWCAP), REG06 (IND_CAP), preserving every unselected bit.

    P and N both reside in REG06; one complete write updates them together.
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
    if expected_map != ((REG07, 0x1F, 0), (REG05, 0x0F, 0),
                        (REG06, 0x07, 0), (REG06, 0x38, 3)):
        raise RuntimeError(f"Unexpected register Field mapping: {expected_map!r}")
    reg07 = chip.compose_field_value(before07, f_i, ibias)
    reg05 = chip.compose_field_value(before05, f_s, swcap)
    reg06 = chip.compose_field_value(before06, f_p, ind_cap)
    reg06 = chip.compose_field_value(reg06, f_n, ind_cap)
    return reg07, reg05, reg06


def verify_register(chip: Any, addr: int, expected: int) -> int:
    # Retry READ ONLY on a value mismatch; never silently write a second time.
    for attempt in range(SPI_READ_RETRY + 1):
        read = chip.read_reg(addr)
        if read == expected:
            if attempt:
                emit(("[SPI WARNING] ", "yellow"),
                     f"REG{addr:02X} matched after {attempt} read-only retry(ies)")
            return read
        if attempt < SPI_READ_RETRY:
            emit(("[SPI WARNING] ", "yellow"),
                 f"REG{addr:02X} read 0x{read:02X} != expected 0x{expected:02X}; retrying read")
    raise SPIReadbackError(addr, expected, read)


def write_point(chip: Any, target07: int, target05: int, target06: int,
                on_verified: Callable[[int, int, int], None] | None = None,
                on_write: Callable[[int], None] | None = None) -> tuple[int, int, int]:
    # REG06 updates both IND_P and IND_N in a SINGLE 8-bit SPI write.
    # Fail immediately on any mismatched full-register readback.
    if on_write is not None:
        on_write(REG07)
    chip.write_reg(REG07, target07)
    r07 = verify_register(chip, REG07, target07)
    if on_verified is not None:
        on_verified(REG07, target07, r07)
    if on_write is not None:
        on_write(REG05)
    chip.write_reg(REG05, target05)
    r05 = verify_register(chip, REG05, target05)
    if on_verified is not None:
        on_verified(REG05, target05, r05)
    if on_write is not None:
        on_write(REG06)
    chip.write_reg(REG06, target06)
    r06 = verify_register(chip, REG06, target06)
    if on_verified is not None:
        on_verified(REG06, target06, r06)
    return r07, r05, r06


def restore_snapshot(chip: Any, snapshot: dict[str, int],
                     attempted_writes: set[int] | None = None) -> None:
    """Restore only registers actually targeted by the scan, never the entire bank.

    The list is tracked before each write attempt, so even an I/O exception
    during a write cannot silently leave a possibly modified register behind.
    """
    if attempted_writes is None:
        # Keep a safe backward-compatible fallback if called by other modules.
        active = {"IBIAS": REG07, "SWCAP": REG05, "IND_CAP": REG06}
        attempted_writes = {active[x] for x in ACTIVE_SCAN_FIELDS}
    failures = []
    emit(("[RESTORE] ", "cyan"),
         f"Restoring {len(attempted_writes)} scan-target REG(s); other registers are read-only")
    for addr in sorted(attempted_writes):
        name = f"REG{addr:02X}"
        try:
            chip.write_reg(addr, snapshot[name])
            verify_register(chip, addr, snapshot[name])
            emit(("[RESTORE PASS]", "green"), f" {name} = 0x{snapshot[name]:02X}")
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            emit(("[RESTORE ERROR]", "red"), (f" {name}: {exc}", "red"), err=True)
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
# Summary CSV, per-point CSV/Excel/PNG, and all_traces_long.csv are unchanged.
# The workbook now contains ONLY the newer analysis sheets (no legacy Summary,
# PN_1MHz_IND*, Freq_MHz_IND*, or Trace_Long tabs).
# Failed points are excluded from rankings and plotted as blanks.
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
                "Freq_MHz", "Power_dBm", "REG07", "REG05", "REG06"]


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


def _rank_rows(rows: list[dict[str, Any]], metric: str, limit: int | None = None) -> list[dict[str, Any]]:
    if limit is None:
        limit = TOP_N
    field = ("carrier_mhz" if metric in ("Frequency_Low", "Frequency_High") else
             "jitter_fs" if metric == "Jitter_fs" else metric)
    eligible = [r for r in _completed_rows(rows) if _safe_numeric(r.get(field)) is not None]
    return sorted(eligible, key=lambda r: (
        -float(r[field]) if metric == "Frequency_High" else float(r[field]), int(r["step"])) )[:limit]


def add_analytics_sheets(book: Any, rows: list[dict[str, Any]],
                         a_values: list[int], b_values: list[int],
                         c_values: list[int], out_dir: Path) -> None:
    """Create dashboard + 3 interactive Fixed_* pages + full performance Top N."""
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
    fm_freq = book.add_format({"num_format": "0.000000", "border": 1,
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
                 "Status", "PN_100Hz", "REG07", "REG05", "REG06", "Capture_Time"]
    data_src = ["step", "ibias_dec", "swcap_dec", "ind_cap_dec", "jitter_fs",
                "PN_1kHz", "PN_10kHz", "PN_100kHz", "PN_1MHz", "carrier_mhz",
                "output_power_dbm", "capture_status", "PN_100Hz", "reg07_read_hex",
                "reg05_read_hex", "reg06_read_hex", "capture_time"]
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
                       fm_freq if j == 9 and isinstance(val, (float, int)) else
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
                     "Freq_MHz", "Power_dBm", "REG07", "REG05", "REG06"]
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
                              r.get("reg07_read_hex"), r.get("reg05_read_hex"), r.get("reg06_read_hex")]
                    cache_count += 1
                    rank_lookup[key] = dict(zip(cache_columns, values))
                    for col, v in enumerate(values):
                        if v is not None:
                            index.write(cache_count, col, v)
    cache_end = max(2, cache_count + 1)
    index.hide()

    # Fixed parameter drill-down pages: six side-by-side tables/charts and Top N.
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
        # 0 = show Excel/WPS default worksheet gridlines (including blank cells).
        ws.hide_gridlines(0)
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
        # User-defined default chart selector; fall back to an actually scanned code.
        preferred = {"IBIAS": DEFAULT_FIXED_IBIAS, "SWCAP": DEFAULT_FIXED_SWCAP,
                     "IND_CAP": DEFAULT_FIXED_IND_CAP}[fixed]
        if preferred in fvals:
            value = preferred
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
                    ws.write_formula(line, z_i, formula, fm_freq if mkey == "Freq_MHz" else fm_num,
                                     cached if cached is not None else "")
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
        ws.merge_range("A160:R160", f"TOP {TOP_N} | {fixed} fixed — full performance ranking", fm_title)
        ws.write("A162", "Fixed code:", fm_label)
        ws.write_formula("B162", "=$B$6", fm_input, value)
        ws.write("C162", "Rank by:", fm_label)
        ws.write("D162", "Jitter_fs", fm_input)
        ws.data_validation("D162", {"validate": "list", "source": RANK_METRICS})
        ws.merge_range("F162:R162", f"Choose metric at D162; each row shows all metrics. Fewer than {TOP_N} points remain blank.", fm_note)
        top_hdr = 164  # Excel row 165
        for j, head in enumerate(RANK_COLUMNS):
            ws.write(top_hdr, j, head, fm_col)
        for rank in range(1, TOP_N + 1):
            rr = top_hdr + rank
            ws.write_number(rr, 0, rank, fm_int)
            for jj in range(1, len(RANK_COLUMNS)):
                # Rank_Lists lookup is precomputed for all valid selector/metric combinations.
                lookup = (f'"{name}|"&$B$6&"|"&$D$162&"|"&$A{rr+1}')
                formula = f'=IFERROR(VLOOKUP({lookup},Rank_Lists!$A$2:$O${cache_end},{jj+1},FALSE),"")'
                key = f"{name}|{value}|Jitter_fs|{rank}"
                cache = rank_lookup.get(key)
                output_value = cache.get(cache_columns[jj]) if cache else None
                ws.write_formula(rr, jj, formula, fm_freq if jj == 10 else fm_num if 5 <= jj <= 11 else fm_plain,
                                 output_value if output_value is not None else "")
        ws.autofilter(top_hdr, 0, top_hdr + TOP_N, len(RANK_COLUMNS)-1)
        ws.write(top_hdr + TOP_N + 2, 0,
                 "Ranking excludes failed/incomplete captures. PN@1kHz is flagged in Quality_Check for verification.", fm_note)

    # Global seven rank tables, TOP_N rows each, with all metrics on every row.
    opt = book.add_worksheet("Optimization_Top30")  # Legacy stable sheet name
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
    opt.merge_range("A2:O3", f"OPTIMIZATION | Full Performance TOP {TOP_N}", fm_title)
    opt.merge_range("A4:O4", "Each ranking uses one metric but retains all six measured performance values and register codes.", fm_sub)
    ranking_names = {"Jitter_fs": "Lowest Jitter", "PN_1kHz": "Lowest PN @ 1 kHz",
                     "PN_10kHz": "Lowest PN @ 10 kHz", "PN_100kHz": "Lowest PN @ 100 kHz",
                     "PN_1MHz": "Lowest PN @ 1 MHz", "Frequency_Low": "Lowest Frequency",
                     "Frequency_High": "Highest Frequency"}
    for t, metric in enumerate(RANK_METRICS):
        start = 6 + t*(TOP_N + 5)
        opt.merge_range(start, 0, start, 14, f"TOP {TOP_N}  /  {ranking_names[metric]}", fm_sub)
        for j, name in enumerate(RANK_COLUMNS):
            opt.write(start+1, j, name, fm_col)
        subset = _rank_rows(all_pass, metric)
        for rank, r in enumerate(subset, 1):
            values = [rank, r.get("step"), r.get("ibias_dec"), r.get("swcap_dec"),
                      r.get("ind_cap_dec"), r.get("jitter_fs"), r.get("PN_1kHz"),
                      r.get("PN_10kHz"), r.get("PN_100kHz"), r.get("PN_1MHz"),
                      r.get("carrier_mhz"), r.get("output_power_dbm"),
                      r.get("reg07_read_hex"), r.get("reg05_read_hex"), r.get("reg06_read_hex")]
            for col, val in enumerate(values):
                if val is not None:
                    opt.write(start+1+rank, col, val, fm_freq if col == 10 else fm_num if 5 <= col <= 11 else fm_plain)
        opt.write(start + TOP_N + 2, 0, f"Available ranked points: {len(subset)}", fm_small)
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
    start.merge_range("B5:J5", f"IBIAS × SWCAP × IND_CAP | 6 metrics | Fixed-code charts + full Top {TOP_N}", fm_sub)
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
        (26,"Fixed_IBIAS", f"Fixed IBIAS: SWCAP × IND_CAP; heatmaps, curves, metric Top {TOP_N}"),
        (28,"Fixed_SWCAP", f"Fixed SWCAP: IBIAS × IND_CAP; heatmaps, curves, metric Top {TOP_N}"),
        (30,"Fixed_IND", f"Fixed IND_CAP: IBIAS × SWCAP; heatmaps, curves, metric Top {TOP_N}"),
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
        ("REG07 initial", snapshot.get('REG07_hex','')),
        ("REG05 initial", snapshot.get('REG05_hex','')),
        ("REG06 initial", snapshot.get('REG06_hex','')),
        ("Jitter integral range (Hz)", (
            f"{all_pass[0].get('integral_start_hz', '')} - {all_pass[0].get('integral_stop_hz', '')}"
            if all_pass else '')),
        ("PCB ID", plan.get('sample', {}).get('pcb_id', PCB_ID)),
        ("CMOS chip ID", plan.get('sample', {}).get('chip_id', CHIP_ID)),
        ("SAW resonator ID", plan.get('sample', {}).get('saw_id', SAW_ID)),
        ("Test name", plan.get('sample', {}).get('test_name', TEST_NAME)),
        ("Test note", plan.get('sample', {}).get('test_note', TEST_NOTE)),
        ("Operator", plan.get('sample', {}).get('operator', TEST_OPERATOR)),
        ("Temperature (C) - user recorded", plan.get('sample', {}).get('temperature_c') if plan.get('sample', {}).get('temperature_c') is not None else ''),
        ("VDD (V) - user recorded", plan.get('sample', {}).get('vdd_v') if plan.get('sample', {}).get('vdd_v') is not None else ''),
        ("Report ranking Top N", plan.get('report_top_n', TOP_N)),
        ("Measure offsets", "From E5052B capture; not set by this case"),
    ]
    for i, (key, val) in enumerate(it, 5):
        info.write(i, 1, key, fm_label)
        info.write(i, 2, val)

    # Live register-bank audit from REG05 through REG14, including unscanned REGs.
    # Only display what was actually read; no invented default register values.
    comparison_path = out_dir / "register_comparison.json"
    if comparison_path.exists():
        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
        rr = max(38, 8 + len(it) + 3)
        info.merge_range(rr, 1, rr, 7, "REGISTER BANK: BEFORE / AFTER / WRITE SCOPE", fm_sub)
        heads = ["Register", "Before", "After", "Written", "Status", "Read error"]
        for cc, label in enumerate(heads, 1):
            info.write(rr + 2, cc, label, fm_col)
        for ii, entry in enumerate(comparison.get("registers", []), rr + 3):
            values = [entry.get("register"), entry.get("before_hex"),
                      entry.get("after_hex"), "Yes" if entry.get("written_by_scan") else "No",
                      entry.get("status"), entry.get("read_error")]
            for cc, val in enumerate(values, 1):
                if val is None:
                    continue
                fmt = (fm_ok if val == "PASS" else fm_err if val in ("ERROR", "READ_ERROR")
                       else fm_plain)
                info.write(ii, cc, val, fmt)
        info.write(rr + 5 + len(comparison.get("registers", [])), 1, "Bank audit status", fm_label)
        info.write(rr + 5 + len(comparison.get("registers", [])), 2, comparison.get("overall", ""),
                   fm_ok if comparison.get("overall") == "PASS" else fm_err)

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
    """Generate the clean, analysis-only workbook; preserve all CSV/JSON/raw files.

    Keeps: Data, Original_Summary, Fixed_IBIAS, Fixed_SWCAP, Fixed_IND,
    Optimization_Top30, Start_Here, Quality_Check, Test_Info,
    PCB_Compare_Template and the hidden Rank_Lists calculation cache.

    Removes only the redundant workbook sheets: Summary, PN_1MHz_IND*,
    Freq_MHz_IND*, and Trace_Long. The full raw phase-noise curves still exist
    in all_traces_long.csv, as well as the per-point traces/ CSV files.
    """
    import xlsxwriter

    path = out_dir / output_name
    book = xlsxwriter.Workbook(str(path))
    try:
        add_analytics_sheets(book, rows, a_values, b_values, c_values, out_dir)
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


# Complete readable register bank for this chip. Read-only snapshots never initialize registers.
# Confirm every address is safe to read on future chip revisions (e.g. no read-to-clear semantics).
SNAPSHOT_REG_START = 0x05
SNAPSHOT_REG_STOP = 0x14  # inclusive; REG05 ... REG14 (16 registers)


def snapshot_register_bank(chip: Any, *, strict: bool = True) -> tuple[dict[str, int], dict[str, str]]:
    """Read every configured register via the already-verified ChipSpi.read_reg().

    For an INITIAL snapshot, strict=True: a missing/invalid read stops the test
    before any register has been written. At the END, continue reading other
    registers if one fails and report an explicit verification error.
    """
    values: dict[str, int] = {}
    errors: dict[str, str] = {}
    for addr in range(SNAPSHOT_REG_START, SNAPSHOT_REG_STOP + 1):
        name = f"REG{addr:02X}"
        try:
            raw = chip.read_reg(addr)
            if type(raw) is not int or not 0 <= raw <= 0xFF:
                raise RuntimeError(f"invalid 8-bit readback: {raw!r}")
            values[name] = raw
        except Exception as exc:
            errors[name] = f"{type(exc).__name__}: {exc}"
            if strict:
                raise RuntimeError(f"Initial full-register snapshot failed at {name}; no SPI write was attempted: {exc}") from exc
    return values, errors


def snapshot_payload(snapshot: dict[str, int], *, stage: str,
                     errors: dict[str, str] | None = None) -> dict[str, Any]:
    """Preserve original REG07_hex etc keys for backward-compatible Test_Info."""
    payload: dict[str, Any] = {
        "capture_local_time": datetime.now().isoformat(timespec="seconds"),
        "stage": stage,
        "address_start": f"0x{SNAPSHOT_REG_START:02X}",
        "address_stop_inclusive": f"0x{SNAPSHOT_REG_STOP:02X}",
        "registers": {key: f"0x{value:02X}" for key, value in snapshot.items()},
        "read_errors": errors or {},
        "read_count": len(snapshot),
        "expected_count": SNAPSHOT_REG_STOP - SNAPSHOT_REG_START + 1,
        "notes": "Live silicon SPI readback; no default-register initialization or writes",
    }
    for key in ("REG07", "REG05", "REG06"):
        if key in snapshot:
            payload[key + "_hex"] = f"0x{snapshot[key]:02X}"
            payload[key + "_dec"] = snapshot[key]
    return payload


def register_comparison(initial: dict[str, int], final: dict[str, int],
                        read_errors: dict[str, str], attempted_writes: set[int],
                        restore_enabled: bool) -> dict[str, Any]:
    rows = []
    unexpected = []
    not_restored = []
    for addr in range(SNAPSHOT_REG_START, SNAPSHOT_REG_STOP + 1):
        name = f"REG{addr:02X}"
        written = addr in attempted_writes
        after = final.get(name)
        before = initial.get(name)
        if name in read_errors:
            state = "READ_ERROR"
            unexpected.append(name)
        elif after == before:
            state = "PASS"
        elif written and not restore_enabled:
            state = "NOT_RESTORED"
            not_restored.append(name)
        else:
            state = "ERROR"
            unexpected.append(name)
        rows.append({
            "register": name,
            "before_hex": f"0x{before:02X}" if before is not None else None,
            "after_hex": f"0x{after:02X}" if after is not None else None,
            "written_by_scan": written,
            "status": state,
            "read_error": read_errors.get(name),
        })
    overall = "ERROR" if unexpected else "NOT_RESTORED" if not_restored else "PASS"
    return {
        "overall": overall,
        "comparison_time_local": datetime.now().isoformat(timespec="seconds"),
        "restore_requested": restore_enabled,
        "written_registers": [f"REG{x:02X}" for x in sorted(attempted_writes)],
        "failed_registers": unexpected,
        "intentionally_not_restored": not_restored,
        "registers": rows,
    }


def update_plan_snapshot(out_dir: Path, snapshot: dict[str, int]) -> None:
    plan_path = out_dir / "run_plan.json"
    if not plan_path.is_file():
        return
    obj = json.loads(plan_path.read_text(encoding="utf-8"))
    obj["snapshot_register_range"] = [f"0x{SNAPSHOT_REG_START:02X}",
                                       f"0x{SNAPSHOT_REG_STOP:02X}"]
    obj["snapshot_initial_hex"] = {k: f"0x{v:02X}" for k, v in snapshot.items()}
    obj["full_register_comparison_after_run"] = True
    obj["restore_policy"] = "Write back ONLY registers actually attempted during this scan"
    write_json(plan_path, obj)


def run_sweep(chip: Any, inst: Any, points: list[ScanPoint], out_dir: Path,
              capture_fn: Callable[..., Any], capture_options: Any, *,
              settle_s: float, acquisition_s: float, restore: bool = True,
              min_carrier_dbm: float | None = None,
              freq_min_mhz: float | None = None, freq_max_mhz: float | None = None) -> dict[str, Any]:
    """Run on already-open devices; injection-friendly for offline fake-device tests."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ensure_original_output_tree(out_dir)
    # 1) Read REG05..REG14 before ANY SPI writes. Abort on any failed initial read.
    try:
        snapshot, _ = snapshot_register_bank(chip, strict=True)
    except Exception as exc:
        emit(("[SNAPSHOT ERROR] ", "red"), (str(exc), "red"), err=True)
        write_json(out_dir / "run_result.json", {
            "status": "FAIL", "completed_points": 0, "planned_points": len(points),
            "error": str(exc), "register_snapshot": "FAIL - NO SPI WRITES",
        })
        raise
    write_json(out_dir / "initial_register_snapshot.json",
               snapshot_payload(snapshot, stage="BEFORE"))
    update_plan_snapshot(out_dir, snapshot)
    emit(("[SNAPSHOT PASS] ", "green"),
         f"{len(snapshot)}/{SNAPSHOT_REG_STOP-SNAPSHOT_REG_START+1} registers read, "
         f"REG07=0x{snapshot['REG07']:02X} REG05=0x{snapshot['REG05']:02X} "
         f"REG06=0x{snapshot['REG06']:02X}")
    started_at = time.monotonic()
    rows: list[dict[str, Any]] = []
    status = "PASS"
    error: BaseException | None = None
    restore_error: Exception | None = None
    bank_verify_error: Exception | None = None
    bank_verification: dict[str, Any] | None = None
    attempted_writes: set[int] = set()
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
                    new07, new05, new06 = make_register_values(
                        chip, snapshot["REG07"], snapshot["REG05"], snapshot["REG06"],
                        p.ibias, p.swcap, p.ind_cap)
                    row["reg07_written_hex"] = f"0x{new07:02X}"
                    row["reg05_written_hex"] = f"0x{new05:02X}"
                    row["reg06_written_hex"] = f"0x{new06:02X}"
                    def verified(addr: int, expected: int, actual: int) -> None:
                        reg_log[addr] = (expected, actual)

                    r07, r05, r06 = write_point(
                        chip, new07, new05, new06, on_verified=verified,
                        on_write=attempted_writes.add)
                    row["reg07_read_hex"] = f"0x{r07:02X}"
                    row["reg05_read_hex"] = f"0x{r05:02X}"
                    row["reg06_read_hex"] = f"0x{r06:02X}"
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
                    restore_snapshot(chip, snapshot, attempted_writes)
                except Exception as exc:
                    restore_error = exc
                    status = "FAIL"
            else:
                emit(("[WARNING] ", "red"), "--no-restore: chip remains at last written configuration")
            # 4) Verify the ENTIRE register bank after restoring scan-touched registers.
            final_values, final_errors = snapshot_register_bank(chip, strict=False)
            write_json(out_dir / "final_register_snapshot.json",
                       snapshot_payload(final_values, stage="AFTER", errors=final_errors))
            bank_verification = register_comparison(
                snapshot, final_values, final_errors, attempted_writes, restore)
            write_json(out_dir / "register_comparison.json", bank_verification)
            for entry in bank_verification["registers"]:
                color = "green" if entry["status"] == "PASS" else (
                    "yellow" if entry["status"] == "NOT_RESTORED" else "red")
                emit((f"[BANK {entry['status']}] ", color),
                     f"{entry['register']} Before={entry['before_hex']} "
                     f"After={entry['after_hex']} Written={'YES' if entry['written_by_scan'] else 'NO'}")
            if bank_verification["overall"] == "ERROR":
                status = "FAIL"
                bank_verify_error = RuntimeError(
                    "Full-register comparison failed for: " +
                    ", ".join(bank_verification["failed_registers"]))
                emit(("[BANK ERROR] ", "red"), (str(bank_verify_error), "red"), err=True)
            elif bank_verification["overall"] == "NOT_RESTORED":
                emit(("[BANK WARNING] ", "yellow"),
                     "--no-restore: scan-touched registers intentionally differ from initial snapshot")
            else:
                emit(("[BANK PASS] ", "green"),
                     f"{len(bank_verification['registers'])}/{len(bank_verification['registers'])} registers match initial snapshot")
            try:
                summary_xlsx = save_summary_xlsx(out_dir, rows, trace_long_csv, a_values, b_values, c_values)
                emit(("[EXCEL PASS] ", "green"), str(summary_xlsx))
                emit_path_link("Summary Excel", summary_xlsx, log_handle=LOG_HANDLE)
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
                "bank_comparison_status": bank_verification["overall"] if bank_verification else "NOT_RUN",
                "bank_comparison_error": str(bank_verify_error) if bank_verify_error else None,
                "written_registers": [f"REG{x:02X}" for x in sorted(attempted_writes)],
                "initial_register_snapshot": "initial_register_snapshot.json",
                "final_register_snapshot": "final_register_snapshot.json",
                "register_comparison": "register_comparison.json",
                "summary_csv": str(summary_csv), "long_csv": str(trace_long_csv),
            })
    # Supplementary workbook only: read already-saved CSV/PNG; never call hardware.
    # Do this AFTER the summary/raw CSV streams and run_result.json are closed.
    if GENERATE_PN_COMPARISON:
        try:
            from utils.pn_comparison_report import generate_pn_comparison
            comparison_xlsx = generate_pn_comparison(
                out_dir, gallery_columns=PN_GALLERY_COLUMNS)
            emit(("[PN COMPARE PASS] ", "green"), str(comparison_xlsx))
        except Exception as comparison_exc:
            # Never invalidate measured PN data because an optional Excel fails.
            emit(("[PN COMPARE ERROR] ", "red"),
                 (f"{type(comparison_exc).__name__}: {comparison_exc}", "red"), err=True)
            emit(("[NOTE] ", "yellow"),
                 "Existing captured CSV, PNG and summary Excel were preserved.")
    emit((f"[CASE {status}]", "green" if status == "PASS" else "red"),
         f" completed {sum(r.get('capture_status')=='PASS' for r in rows)}/{len(points)}"
         f" | Elapsed={elapsed_text(time.monotonic()-started_at)}")
    if error is not None:
        if isinstance(error, KeyboardInterrupt):
            raise KeyboardInterrupt from error
        raise RuntimeError("Sweep stopped on first error: " + str(error)) from error
    if restore_error is not None:
        raise RuntimeError("Scan completed but snapshot restore failed") from restore_error
    if bank_verify_error is not None:
        raise RuntimeError("Scan finished but full-register verification failed") from bank_verify_error
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


def validate_user_config() -> None:
    """Validate experiment parameters before any hardware initialization."""
    scan_sequences()
    if TEST_MODE.upper() not in ("FULL_SWEEP", "CHECK_POINT", "PLAN_ONLY"):
        raise ValueError("TEST_MODE must be FULL_SWEEP, CHECK_POINT or PLAN_ONLY")
    if len(CHECK_POINT_CODES) != 3 or any(type(v) is not int for v in CHECK_POINT_CODES):
        raise ValueError("CHECK_POINT_CODES must be (int IBIAS, int SWCAP, int IND_CAP)")
    for value, limit, name in zip(CHECK_POINT_CODES, (31, 15, 7), ("IBIAS", "SWCAP", "IND_CAP")):
        if not 0 <= value <= limit:
            raise ValueError(f"CHECK_POINT_CODES: {name} must be within 0..{limit}")
    if any(not isinstance(t, (int, float)) or not math.isfinite(t) or t < 0
           for t in (SETTLE_TIME_S, ACQUIRE_TIME_S)):
        raise ValueError("SETTLE_TIME_S and ACQUIRE_TIME_S must be non-negative finite numbers")
    if not isinstance(TOP_N, int) or isinstance(TOP_N, bool) or not 1 <= TOP_N <= 140:
        raise ValueError("TOP_N must be an integer from 1 to 140")
    if not isinstance(SPI_READ_RETRY, int) or isinstance(SPI_READ_RETRY, bool) or not 0 <= SPI_READ_RETRY <= 3:
        raise ValueError("SPI_READ_RETRY must be 0..3")
    for val, name in ((MIN_CARRIER_DBM, "MIN_CARRIER_DBM"),
                      (FREQ_MIN_MHZ, "FREQ_MIN_MHZ"), (FREQ_MAX_MHZ, "FREQ_MAX_MHZ"),
                      (TEST_TEMPERATURE_C, "TEST_TEMPERATURE_C"), (TEST_VDD_V, "TEST_VDD_V")):
        if val is not None and (not isinstance(val, (int, float)) or not math.isfinite(val)):
            raise ValueError(f"{name} must be None or a finite number")
    if TEST_VDD_V is not None and TEST_VDD_V <= 0:
        raise ValueError("TEST_VDD_V must be positive when provided")
    if FREQ_MIN_MHZ is not None and FREQ_MAX_MHZ is not None and FREQ_MIN_MHZ >= FREQ_MAX_MHZ:
        raise ValueError("FREQ_MIN_MHZ must be smaller than FREQ_MAX_MHZ")
    if E5052B_HOST_OVERRIDE is not None and not str(E5052B_HOST_OVERRIDE).strip():
        raise ValueError("E5052B_HOST_OVERRIDE must be None or a nonblank address")
    if not str(OUTPUT_BASE_DIR).strip():
        raise ValueError("OUTPUT_BASE_DIR must not be blank")


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="IBIAS × SWCAP × IND_CAP(P=N) sweep with E5052B acquisition")
    action = parser.add_mutually_exclusive_group(required=False)
    action.add_argument("--plan", action="store_true", help="Print plan only; never access hardware")
    action.add_argument("--check-point", action="store_true", help="Real hardware, CHECK_POINT_CODES from USER CONFIG")
    action.add_argument("--run", action="store_true", help="Real hardware, full sweep")
    action.add_argument("--report-only", metavar="RUN_DIR", help="Rebuild Excel from existing CSV, no hardware")
    parser.add_argument("--settle-s", type=float, default=SETTLE_TIME_S)
    parser.add_argument("--acquire-s", type=float, default=ACQUIRE_TIME_S)
    parser.add_argument("--screenshot", dest="screenshot", action="store_true", default=SAVE_SCREENSHOT)
    parser.add_argument("--no-screenshot", dest="screenshot", action="store_false")
    parser.add_argument("--point-excel", dest="point_excel", action="store_true", default=SAVE_POINT_EXCEL)
    parser.add_argument("--no-point-excel", dest="point_excel", action="store_false")
    parser.add_argument("--no-restore", dest="restore", action="store_false", default=RESTORE_REGISTERS)
    parser.add_argument("--min-carrier-dbm", type=float, default=MIN_CARRIER_DBM)
    parser.add_argument("--freq-min-mhz", type=float, default=FREQ_MIN_MHZ)
    parser.add_argument("--freq-max-mhz", type=float, default=FREQ_MAX_MHZ)
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--output-dir", default=OUTPUT_BASE_DIR)
    args = parser.parse_args(argv)
    try:
        validate_user_config()
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))
    initialize_colors(disable_color=args.no_color or not TERMINAL_COLOR)
    if any(not math.isfinite(t) or t < 0 for t in (args.settle_s, args.acquire_s)):
        parser.error("--settle-s and --acquire-s must be non-negative finite numbers")
    if args.freq_min_mhz is not None and args.freq_max_mhz is not None and args.freq_min_mhz >= args.freq_max_mhz:
        parser.error("--freq-min-mhz must be less than --freq-max-mhz")

    if args.report_only:
        try:
            generated = regenerate_report_from_existing(Path(args.report_only))
        except Exception as exc:
            emit(("[REPORT ERROR] ", "red"), (f"{type(exc).__name__}: {exc}", "red"), err=True)
            return 1
        emit(("[REPORT PASS] ", "green"), str(generated))
        emit_path_link("Report Excel", generated)
        if GENERATE_PN_COMPARISON:
            try:
                from utils.pn_comparison_report import generate_pn_comparison
                pn_report = generate_pn_comparison(
                    Path(args.report_only), gallery_columns=PN_GALLERY_COLUMNS)
                emit(("[PN COMPARE PASS] ", "green"), str(pn_report))
            except Exception as comparison_exc:
                emit(("[PN COMPARE ERROR] ", "red"),
                     f"{type(comparison_exc).__name__}: {comparison_exc}", err=True)
                return 1
        emit("No Ginkgo or E5052B connection; original Excel and CSV were not overwritten.")
        return 0

    mode = ("PLAN_ONLY" if args.plan else "CHECK_POINT" if args.check_point
            else "FULL_SWEEP" if args.run else TEST_MODE.upper())
    point_tuple = CHECK_POINT_CODES
    points = ([ScanPoint(1, *point_tuple)] if mode == "CHECK_POINT" else scan_points())
    if mode == "PLAN_ONLY":
        plan_only(points)
        return 0

    # Only real hardware actions import Windows-specific Ginkgo DLL.
    from protocol.chip_spi import ChipSpi
    from instruments.e5052b.capture import capture_phase_noise_once
    from scripts.fullflow.common import build_capture_options, make_client_from_config
    from utils.e5052b_config import load_e5052b_config
    # Run folders still use the original hierarchy / name convention.

    cfg = load_e5052b_config()
    if E5052B_HOST_OVERRIDE is not None:
        cfg['host'] = str(E5052B_HOST_OVERRIDE).strip()
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
        "created_at_local": datetime.now().isoformat(timespec='seconds'),
        "sample": {"pcb_id": PCB_ID, "chip_id": CHIP_ID, "saw_id": SAW_ID,
                   "test_name": TEST_NAME, "test_note": TEST_NOTE,
                   "operator": TEST_OPERATOR, "temperature_c": TEST_TEMPERATURE_C,
                   "vdd_v": TEST_VDD_V},
        "user_configuration": {
            "mode": mode,
            "IBIAS": {"mode": IBIAS_MODE, "range": IBIAS_RANGE, "list": IBIAS_LIST,
                      "actual_codes": list(dict.fromkeys(p.ibias for p in points))},
            "SWCAP": {"mode": SWCAP_MODE, "range": SWCAP_RANGE, "list": SWCAP_LIST,
                      "actual_codes": list(dict.fromkeys(p.swcap for p in points))},
            "IND_CAP": {"mode": IND_CAP_MODE, "range": IND_CAP_RANGE, "list": IND_CAP_LIST,
                        "actual_codes": list(dict.fromkeys(p.ind_cap for p in points))},
            "default_fixed_codes": {"IBIAS": DEFAULT_FIXED_IBIAS, "SWCAP": DEFAULT_FIXED_SWCAP,
                                    "IND_CAP": DEFAULT_FIXED_IND_CAP},
            "spi_read_retry": SPI_READ_RETRY,
            "instrument_integration": "READ FROM ACQUIRED RESULT; NOT PROGRAMMED HERE",
            "environment_values_entered_by_user_not_automatically_measured": True,
            "terminal_color": not args.no_color and TERMINAL_COLOR,
        },
        "report_top_n": TOP_N,
        "settle_s": args.settle_s, "acquire_s": args.acquire_s,
        "save_screenshot": args.screenshot, "save_point_excel": args.point_excel,
        "restore": args.restore,
        "min_carrier_dbm": args.min_carrier_dbm,
        "freq_min_mhz": args.freq_min_mhz, "freq_max_mhz": args.freq_max_mhz,
        "instrument_host": cfg['host'], "instrument_port": cfg.get('port', 5025),
        "note": "Endpoint-inclusive sweeps; no initialization; real snapshot before first write",
    })
    global LOG_HANDLE
    LOG_HANDLE = (run_dir / "run_log.txt").open("w", encoding="utf-8")
    emit(("[SAMPLE] ", "cyan"), f"PCB={PCB_ID}  CHIP={CHIP_ID}  SAW={SAW_ID}  TEST={TEST_NAME}")
    emit(("[RUN DIR] ", "cyan"), str(run_dir))
    emit_path_link("Output Folder", run_dir, log_handle=LOG_HANDLE, show_full_path=True)
    emit(("[CONFIG] ", "cyan"), f"{len(points)} combinations; settle={args.settle_s}s, acquisition={args.acquire_s}s")
    emit(("[OUTPUT] ", "cyan"), "Original run layout preserved: merged/ screenshots/ summary/ traces/")
    emit(("[FILES] ", "cyan"), f"screenshot={'ON' if args.screenshot else 'OFF'}; "
         f"point XLSX={'ON' if args.point_excel else 'OFF'}; CSV/JSON/summary XLSX=ON; Top {TOP_N}")
    emit(("[WARNING] ", "yellow"), "Check actual E5052B sweep/average time before the full scan")
    emit(("[WARNING] ", "yellow"), "IBIAS=0 or other settings may cause oscillation to stop; the first failed capture aborts")
    try:
        with make_client_from_config(cfg) as inst:
            emit(("[E5052B] ", "cyan"), str(inst.identify()))
            with ChipSpi() as chip:
                run_sweep(chip, inst, points, run_dir, capture_phase_noise_once, options,
                          settle_s=args.settle_s, acquisition_s=args.acquire_s,
                          restore=args.restore,
                          min_carrier_dbm=args.min_carrier_dbm,
                          freq_min_mhz=args.freq_min_mhz, freq_max_mhz=args.freq_max_mhz)
    except KeyboardInterrupt:
        emit(("[ABORTED] ", "red"), "Ctrl+C; restore attempted if chip was connected and snapshot was available")
        emit(("[OUTPUT LINKS] ", "cyan"), "Partial results (Ctrl+click on VS Code terminal links)")
        emit_run_file_links(run_dir, log_handle=LOG_HANDLE)
        if LOG_HANDLE is not None:
            LOG_HANDLE.close()
            LOG_HANDLE = None
        return 130
    except Exception as exc:
        emit(("[ERROR] ", "red"), (f"{type(exc).__name__}: {exc}", "red"), err=True)
        emit(("[OUTPUT LINKS] ", "cyan"), "Partial results (Ctrl+click on VS Code terminal links)")
        emit_run_file_links(run_dir, log_handle=LOG_HANDLE)
        if LOG_HANDLE is not None:
            LOG_HANDLE.close()
            LOG_HANDLE = None
        return 1
    emit(("[PASS] ", "green"), "Ready for Excel plotting")
    emit(("[OUTPUT LINKS] ", "cyan"), "Ctrl+click a link in the VS Code integrated terminal")
    emit_run_file_links(run_dir, log_handle=LOG_HANDLE)
    if LOG_HANDLE is not None:
        LOG_HANDLE.close()
        LOG_HANDLE = None
    return 0


if __name__ == "__main__":
    sys.exit(cli())
