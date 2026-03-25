from __future__ import annotations

import math
from typing import Optional, Sequence, Tuple


def parse_ascii_array(s: str) -> list[float]:
    s = s.strip()
    if not s:
        return []
    return [float(x.strip()) for x in s.split(",") if x.strip()]


def parse_date(s: str) -> Optional[str]:
    try:
        items = [int(float(x.strip())) for x in s.split(",") if x.strip()]
        if len(items) >= 3:
            return f"{items[0]:04d}-{items[1]:02d}-{items[2]:02d}"
    except Exception:
        return None
    return None


def parse_time(s: str) -> Optional[str]:
    try:
        items = [int(float(x.strip())) for x in s.split(",") if x.strip()]
        if len(items) >= 3:
            return f"{items[0]:02d}:{items[1]:02d}:{items[2]:02d}"
    except Exception:
        return None
    return None


def nearest_value(xs: Sequence[float], ys: Sequence[float], target: float) -> Optional[Tuple[float, float]]:
    if not xs or not ys or len(xs) != len(ys):
        return None
    idx = min(range(len(xs)), key=lambda i: abs(xs[i] - target))
    return xs[idx], ys[idx]


def interpolate_linear(xs: Sequence[float], ys: Sequence[float], x0: float) -> float:
    if x0 <= xs[0]:
        return ys[0]
    if x0 >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if xs[i] >= x0:
            x1, x2 = xs[i - 1], xs[i]
            y1, y2 = ys[i - 1], ys[i]
            if x2 == x1:
                return y2
            t = (x0 - x1) / (x2 - x1)
            return y1 + t * (y2 - y1)
    return ys[-1]


def crop_and_interpolate(xs: Sequence[float], ys: Sequence[float], start: float, stop: float) -> tuple[list[float], list[float]]:
    if start >= stop:
        raise ValueError("Integration start must be < stop")
    if len(xs) != len(ys) or len(xs) < 2:
        raise ValueError("Trace arrays are invalid")
    if start < xs[0] or stop > xs[-1]:
        raise ValueError("Integration range is outside trace range")

    work_x: list[float] = [start]
    work_y: list[float] = [interpolate_linear(xs, ys, start)]
    for x, y in zip(xs, ys):
        if start < x < stop:
            work_x.append(x)
            work_y.append(y)
    work_x.append(stop)
    work_y.append(interpolate_linear(xs, ys, stop))
    return work_x, work_y


def trapz(xs: Sequence[float], ys: Sequence[float]) -> float:
    total = 0.0
    for i in range(1, len(xs)):
        dx = xs[i] - xs[i - 1]
        total += 0.5 * dx * (ys[i] + ys[i - 1])
    return total


def compute_integrals(xs: Sequence[float], l_dbc_hz: Sequence[float], start: float, stop: float, carrier_hz: float) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    x2, y2 = crop_and_interpolate(xs, l_dbc_hz, start, stop)
    lin = [10 ** (v / 10.0) for v in y2]
    ssb = trapz(x2, lin)
    if ssb <= 0:
        return None, None, None, None
    integ_dbc = 10.0 * math.log10(ssb)
    rms_rad = math.sqrt(2.0 * ssb)
    jitter_s = rms_rad / (2.0 * math.pi * carrier_hz) if carrier_hz > 0 else None
    residual_integrand = [2.0 * (x ** 2) * (10 ** (v / 10.0)) for x, v in zip(x2, y2)]
    residual_fm_hz = math.sqrt(max(trapz(x2, residual_integrand), 0.0))
    return integ_dbc, rms_rad, jitter_s, residual_fm_hz


def choose_x_axis_range(xvals: Sequence[float]) -> tuple[float, float]:
    vals = [v for v in xvals if v is not None and math.isfinite(v) and v > 0]
    if not vals:
        return 1.0, 1.0e7
    return min(vals), max(vals)


def choose_y_axis_range(yvals: Sequence[float]) -> tuple[float, float]:
    vals = [v for v in yvals if v is not None and math.isfinite(v)]
    if not vals:
        return -170.0, 0.0
    ymin = min(vals)
    ymax = max(vals)
    pad = max(2.0, 0.05 * (ymax - ymin if ymax > ymin else 20.0))
    lower = math.floor((ymin - pad) / 5.0) * 5.0
    upper = math.ceil((ymax + pad) / 5.0) * 5.0
    if upper <= lower:
        upper = lower + 10.0
    return lower, upper
