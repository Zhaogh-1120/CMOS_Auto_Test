"""Standalone PN Comparison workbook built from existing E5052B measurements.

Produces ``pn_comparison.xlsx`` alongside the original sweep outputs without
opening any instruments, changing any scan logic, or editing the original report.

- Overview: one measured configuration per row, *original* screenshot PNG in the
  last column (no resized/re-encoded JPEG intermediates).
- PN_Gallery: original PNG images side by side, with concise measured metrics.
- PN_Overlay: Excel-native log-X scatter overlays of the actual offset/PN data.
- Raw_PN: one long, numeric, filterable trace table.
- Test_Info: experiment provenance and report diagnostics.
- Chart_Data: hidden chart-only source containing unmodified numeric samples.

Run offline from ``full_flow_test``:
    python -m utils.pn_comparison_report --run-dir <run_YYYYMMDD_HHMMSS>
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import xlsxwriter
from PIL import Image

SUMMARY_NAME = "summary_ibias_swcap_indcap.csv"
TRACES_NAME = "all_traces_long.csv"
OUTPUT_NAME = "pn_comparison.xlsx"


def _number(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def _load_json(path: Path) -> dict[str, Any]:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def _load_summary(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing required measured summary: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        data = list(csv.DictReader(handle))
    if not data:
        raise ValueError(f"No measured rows in {path}")
    return data


def _saved_file(run_dir: Path, value: str | None, folder: str, suffix: str) -> Path | None:
    """Resolve original Windows relative/absolute capture paths after relocating a run."""
    if not value:
        return None
    name = str(value).replace('\\', '/').rsplit('/', 1)[-1]
    if not name.lower().endswith(suffix) or name in ("", ".", ".."):
        return None
    # The destination *must* be inside this run: never substitute a file from
    # another PCB or another run with an identical step number.
    local = run_dir / folder / name
    return local if local.is_file() else None


def _load_traces(run_dir: Path, rows: list[dict[str, str]]) -> dict[int, list[tuple[float, float]]]:
    results: dict[int, list[tuple[float, float]]] = defaultdict(list)
    trace_file = run_dir / TRACES_NAME
    if trace_file.is_file():
        with trace_file.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                try:
                    step = int(row['step'])
                except (KeyError, TypeError, ValueError):
                    continue
                offset = _number(row.get('offset_hz'))
                level = _number(row.get('phase_noise_dbc_hz'))
                if offset is not None and offset > 0 and level is not None:
                    results[step].append((offset, level))
    # For historical runs lacking a consolidated CSV, read each genuine raw trace.
    for rec in rows:
        try:
            step = int(rec['step'])
        except (KeyError, TypeError, ValueError):
            continue
        if results[step]:
            continue
        path = _saved_file(run_dir, rec.get('raw_csv_path'), 'traces', '.csv')
        if path is None:
            continue
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for point in csv.DictReader(handle):
                x = _number(point.get('offset_hz'))
                y = _number(point.get('phase_noise_dbc_hz'))
                if x is not None and x > 0 and y is not None:
                    results[step].append((x, y))
    # Do not interpolate, smooth, or create any non-existent points.
    return dict(results)


def _write_value(ws: Any, row: int, col: int, value: Any, fmt: Any = None) -> None:
    if value is None:
        ws.write_blank(row, col, None, fmt)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        ws.write_number(row, col, value, fmt)
    else:
        ws.write_string(row, col, str(value), fmt)


def _insert_original_png(ws: Any, row: int, col: int, path: Path,
                         *, max_width: int, max_height: int, offset: int = 5) -> tuple[int, int]:
    """Use unchanged source PNG bytes; Excel display-scale metadata only."""
    with Image.open(path) as image:
        if image.format != "PNG":
            raise ValueError(f"Not a PNG screenshot: {path}")
        width, height = image.size
    scale = min(max_width / width, max_height / height, 1.0)
    opts = {"x_scale": scale, "y_scale": scale,
            "x_offset": offset, "y_offset": offset,
            "object_position": 1, "description": path.name}
    ws.insert_image(row, col, str(path), opts)
    return round(width * scale), round(height * scale)


def _fmt_workbook(wb: Any) -> dict[str, Any]:
    navy, teal, pale = "#152A42", "#0D7C86", "#E9F4F7"
    return {
        "title": wb.add_format({"bold": True, "font_size": 18, "font_color": "white", "bg_color": navy, "valign": "vcenter"}),
        "subtitle": wb.add_format({"font_color": navy, "bg_color": pale, "font_size": 10, "text_wrap": True, "valign": "vcenter"}),
        "head": wb.add_format({"bold": True, "font_color": "white", "bg_color": teal, "border": 1, "border_color": "#CCE4E6", "align": "center", "text_wrap": True, "valign": "vcenter"}),
        "num": wb.add_format({"num_format": "0.00", "align": "center", "valign": "vcenter", "bottom": 1, "bottom_color": "#E6EBEF"}),
        "hz": wb.add_format({"num_format": "0.000000", "align": "center", "valign": "vcenter", "bottom": 1, "bottom_color": "#E6EBEF"}),
        "int": wb.add_format({"num_format": "0", "align": "center", "valign": "vcenter", "bottom": 1, "bottom_color": "#E6EBEF"}),
        "txt": wb.add_format({"align": "center", "valign": "vcenter", "bottom": 1, "bottom_color": "#E6EBEF"}),
        "link": wb.add_format({"font_color": "#176E9B", "underline": 1, "align": "center", "valign": "vcenter"}),
        "small": wb.add_format({"font_color": "#607589", "font_size": 9}),
        "tag": wb.add_format({"font_color": "#152A42", "bg_color": pale, "bold": True, "valign": "vcenter"}),
        "missing": wb.add_format({"font_color": "#B42318", "bg_color": "#FFF0EC", "align": "center", "valign": "vcenter"}),
        "metric": wb.add_format({"font_size": 10, "font_color": "#304F68", "italic": True}),
    }


def _key(row: dict[str, str]) -> int:
    return int(row['step'])


def _values(row: dict[str, str]) -> tuple[int, int, int]:
    return (int(row['ibias_dec']), int(row['swcap_dec']), int(row['ind_cap_dec']))


def _measured(row: dict[str, str]) -> bool:
    return row.get('spi_verify') == 'PASS' and row.get('capture_status') == 'PASS'


def _active_fields(plan: dict[str, Any], rows: list[dict[str, str]]) -> list[str]:
    fields = plan.get('user_configuration', {}).get('active_scan_fields', [])
    possible = ('IBIAS', 'SWCAP', 'IND_CAP')
    if isinstance(fields, list) and fields and all(f in possible for f in fields):
        return list(fields)
    return [name for name, field in zip(possible, ('ibias_dec', 'swcap_dec', 'ind_cap_dec'))
            if len({r.get(field) for r in rows}) > 1] or ['IND_CAP']


def generate_pn_comparison(run_dir: str | Path, *, gallery_columns: int = 2,
                           output_name: str = OUTPUT_NAME) -> Path:
    """Generate supplementary workbook from existing saved outputs only.

    Missing PNG/trace content is explicitly reported and never substituted.
    No Ginkgo driver or E5052B module is imported or contacted.
    """
    run_dir = Path(run_dir).expanduser().resolve()
    if gallery_columns not in (1, 2):
        raise ValueError('gallery_columns must be 1 or 2')
    records = sorted(_load_summary(run_dir / SUMMARY_NAME), key=_key)
    plan = _load_json(run_dir / 'run_plan.json')
    result = _load_json(run_dir / 'run_result.json')
    traces = _load_traces(run_dir, records)
    images: dict[int, Path] = {}
    for r in records:
        path = _saved_file(run_dir, r.get('screenshot_path'), 'screenshots', '.png')
        if path:
            try:
                with Image.open(path) as im:
                    im.verify()
                    if im.format != 'PNG':
                        raise ValueError('not PNG')
                images[_key(r)] = path
            except (OSError, ValueError):
                pass  # Report a missing/unreadable picture instead of substituting another.

    target = run_dir / output_name
    wb = xlsxwriter.Workbook(str(target))
    wb.set_properties({"title": "SAW OSC — Phase Noise Comparison",
                       "subject": "Measured PN traces and original E5052B screenshots",
                       "comments": "No instrument remeasurement. Original PNGs are embedded unchanged."})
    f = _fmt_workbook(wb)
    try:
        # ------------ Overview: numeric record + original PNG in the LAST column ------------
        over = wb.add_worksheet('Overview')
        over.activate()
        over.set_first_sheet()
        over.set_tab_color('#117A83')
        over.freeze_panes(5, 4)
        over.set_zoom(75)
        over.hide_gridlines(0)
        over.set_column('A:A', 9)
        over.set_column('B:D', 11)
        over.set_column('E:L', 17)
        over.set_column('M:M', 12)
        over.set_column('N:O', 25)
        over.set_column('P:P', 22)
        over.set_column('Q:Q', 96)
        over.merge_range('A2:Q3', 'SAW OSC | PHASE NOISE COMPARISON  /  MEASURED DATA', f['title'])
        over.merge_range('A4:Q4', 'One configuration per row · Last column contains its genuine E5052B PNG (source pixels unchanged) · PN/Jitter shown to 2 decimals', f['subtitle'])
        headers = ['Step', 'IBIAS', 'SWCAP', 'IND_CAP', 'Carrier MHz', 'Power dBm',
                   'PN@1kHz', 'PN@10kHz', 'PN@100kHz', 'PN@1MHz', 'Jitter fs',
                   'PN@10MHz', 'Status', 'Screenshot filename', 'Raw PN CSV',
                   'Capture time', 'E5052B Screenshot (original PNG)']
        for col, name in enumerate(headers):
            over.write(4, col, name, f['head'])
        over.set_row(4, 35)
        for index, r in enumerate(records):
            rr = index + 5
            step = _key(r)
            ib, sw, ind = _values(r)
            vals = [step, ib, sw, ind, _number(r.get('carrier_mhz')),
                    _number(r.get('output_power_dbm')), _number(r.get('PN_1kHz')),
                    _number(r.get('PN_10kHz')), _number(r.get('PN_100kHz')),
                    _number(r.get('PN_1MHz')), _number(r.get('jitter_fs')),
                    _number(r.get('PN_10MHz')), r.get('capture_status',''),
                    Path(str(r.get('screenshot_path') or '').replace('\\','/')).name,
                    Path(str(r.get('raw_csv_path') or '').replace('\\','/')).name,
                    r.get('capture_time','')]
            for c, val in enumerate(vals):
                fmt = f['int'] if c < 4 else f['hz'] if c == 4 else f['num'] if 5 <= c <= 11 else f['txt']
                _write_value(over, rr, c, val, fmt)
            photo = images.get(step)
            if photo:
                _, disp_h = _insert_original_png(over, rr, 16, photo, max_width=660, max_height=475)
                # Max Excel row height is ~409 pt; 475 px + margins -> 365 pt.
                over.set_row(rr, min(390, (disp_h + 18) * 0.75))
            else:
                over.write(rr, 16, 'NO SCREENSHOT' if _measured(r) else 'CAPTURE FAILED', f['missing'])
                over.set_row(rr, 48)
            if step in images:
                over.write_url(rr, 13, f"internal:'PN_Gallery'!{'A' if index%gallery_columns == 0 else 'J'}{7+(index//gallery_columns)*5}", f['link'], images[step].name)
        over.autofilter(4, 0, 4+len(records), len(headers)-1)

        # ------------ PN_Gallery: two-up gallery, ORIGINAL PNG bytes ------------
        gallery = wb.add_worksheet('PN_Gallery')
        gallery.set_tab_color('#3589A4')
        gallery.set_zoom(80)
        gallery.hide_gridlines(2)
        gallery.set_column('A:A', 5)
        gallery.set_column('B:H', 12)
        gallery.set_column('I:I', 4)
        gallery.set_column('J:P', 12)
        gallery.set_column('Q:Q', 3)
        gallery.merge_range('A2:P3', 'PN GALLERY | ORIGINAL E5052B SCREENSHOTS', f['title'])
        gallery.merge_range('A4:P4', 'The screenshots are the original saved PNGs, not downscaled/re-encoded JPEGs. Select a screenshot in Excel to zoom.', f['subtitle'])
        for i, rec in enumerate(records):
            colgroup = i % gallery_columns
            group_row = i // gallery_columns
            top = 6 + group_row*5
            first = 0 if colgroup == 0 else 9
            last = first + 7
            step = _key(rec)
            ib, sw, ind = _values(rec)
            title = f"STEP {step:03d}  |  IBIAS={ib}  SWCAP={sw}  IND={ind}"
            gallery.merge_range(top, first, top, last, title, f['tag'])
            gallery.set_row(top, 25)
            gallery.merge_range(top+1, first, top+1, last, '', f['txt'])
            gallery.set_row(top+1, 300)
            photo = images.get(step)
            if photo:
                _insert_original_png(gallery, top+1, first, photo, max_width=540, max_height=385)
            else:
                gallery.write(top+1, first, 'NO SCREENSHOT' if _measured(rec) else 'CAPTURE FAILED', f['missing'])
            fm = _number(rec.get('carrier_mhz'))
            pn = _number(rec.get('PN_1MHz'))
            jit = _number(rec.get('jitter_fs'))
            label = (f"Carrier {fm:.6f} MHz" if fm is not None else 'Carrier --') + '    ' + (
                f"PN@1MHz {pn:.2f} dBc/Hz" if pn is not None else 'PN@1MHz --') + '    ' + (
                f"Jitter {jit:.2f} fs" if jit is not None else 'Jitter --')
            gallery.merge_range(top+2, first, top+2, last, label, f['metric'])
            gallery.merge_range(top+3, first, top+3, last, f"PNG: {photo.name if photo else 'not available'}", f['small'])

        # ------------ Raw_PN and Chart_Data: unmodified numeric samples ------------
        raw = wb.add_worksheet('Raw_PN')
        raw.set_tab_color('#7D8D9F')
        raw.freeze_panes(1, 4)
        raw.set_column('A:D', 12)
        raw.set_column('E:E', 20)
        raw.set_column('F:F', 23)
        raw.set_column('G:G', 15)
        for c, v in enumerate(('Step','IBIAS','SWCAP','IND_CAP','Offset_Hz','Phase_Noise_dBc_Hz','Status')):
            raw.write(0, c, v, f['head'])
        chartdata = wb.add_worksheet('Chart_Data')
        chartdata.set_column(0, max(0, 2*len(records)-1), 19)
        chart_ranges: dict[int, tuple[int, int, int]] = {}
        raw_line = 1
        all_x: list[float] = []
        all_y: list[float] = []
        for idx, rec in enumerate(records):
            step = _key(rec)
            i, sw, ind = _values(rec)
            points = traces.get(step, []) if _measured(rec) else []
            chartdata.write(0, 2*idx, f'Step{step:03d}_Offset_Hz', f['head'])
            chartdata.write(0, 2*idx+1, f'Step{step:03d}_PN_dBcHz', f['head'])
            for pos, (x,y) in enumerate(points, 1):
                if pos > 1048575:
                    break
                chartdata.write_number(pos, idx*2, x)
                chartdata.write_number(pos, idx*2+1, y)
                if raw_line <= 1048575:
                    for c, v in enumerate((step,i,sw,ind,x,y)):
                        raw.write_number(raw_line, c, v, f['int'] if c < 4 else f['num'])
                    raw.write(raw_line, 6, 'PASS', f['txt'])
                    raw_line += 1
                all_x.append(x)
                all_y.append(y)
            if points:
                chart_ranges[step] = (idx*2, idx*2+1, min(len(points), 1048575))
        if raw_line > 1:
            raw.autofilter(0,0,raw_line-1,6)
        chartdata.hide()

        # ------------ PN_Overlay: log-X plot of real per-point PN CSV traces ------------
        overlay = wb.add_worksheet('PN_Overlay')
        overlay.set_tab_color('#0A8C91')
        overlay.set_zoom(85)
        overlay.set_column('A:A',4)
        overlay.set_column('B:P',11)
        overlay.hide_gridlines(2)
        overlay.merge_range('B2:P3', 'PHASE NOISE OVERLAYS | ACTUAL MEASURED TRACES', f['title'])
        overlay.merge_range('B4:P4', 'Logarithmic offset axis (Hz) · No interpolation / smoothing · All plots share a common Y range', f['subtitle'])
        active = _active_fields(plan, records)
        grouping = [x for x in active[:-1]]
        ix = {'IBIAS':0,'SWCAP':1,'IND_CAP':2}
        groups: dict[tuple[int,...], list[dict[str,str]]] = defaultdict(list)
        for rec in records:
            code = _values(rec)
            groups[tuple(code[ix[k]] for k in grouping)].append(rec)
        eligible_rows = [r for r in records if _measured(r) and _key(r) in chart_ranges]
        if len(eligible_rows) > 1:
            for metric in ('PN_1MHz','jitter_fs'):
                best = sorted([r for r in eligible_rows if _number(r.get(metric)) is not None],
                              key=lambda r: float(r[metric]))[:5]
                if best:
                    groups[(f'BEST_{metric}',)] = best
        if all_x:
            min_offset, max_offset = min(all_x), max(all_x)
            ylo = 10 * math.floor((min(all_y)-5)/10)
            yhi = 10 * math.ceil((max(all_y)+5)/10)
            ylo = max(-240, ylo)
            yhi = min(20, yhi)
            if ylo >= yhi:
                ylo, yhi = min(all_y)-10, max(all_y)+10
        else:
            min_offset, max_offset, ylo, yhi = 100.0, 40e6, -180.0, -40.0
        colors = ['#147DA4','#E48632','#188B70','#8867AA','#CC6580','#687A2F','#B06A27']
        num_charts = 0
        for g_index,(fixed, group_rows) in enumerate(groups.items()):
            chart_rows = [r for r in group_rows if _measured(r) and _key(r) in chart_ranges]
            start = 6 + 25*g_index
            name = (' / '.join(f'{k}={v}' for k,v in zip(grouping, fixed)) if len(fixed)==len(grouping)
                    else str(fixed[0]).replace('BEST_', 'TOP 5 — '))
            if not name:
                name = f'All {active[-1]} codes'
            overlay.merge_range(start, 1, start, 15, f'{name}  |  {len(chart_rows)} measured traces', f['tag'])
            if not chart_rows:
                overlay.write(start+2, 1, 'NO VALID PN TRACES', f['missing'])
                continue
            chart = wb.add_chart({'type':'scatter','subtype':'straight'})
            for j,r in enumerate(chart_rows):
                step = _key(r)
                xcol,ycol,count = chart_ranges[step]
                i, sw, ind = _values(r)
                chart.add_series({'name': f'#{step:03d} IBIAS={i} SWCAP={sw} IND={ind}',
                                  'categories':['Chart_Data', 1,xcol,count,xcol],
                                  'values':['Chart_Data',1,ycol,count,ycol],
                                  'line':{'color':colors[j%len(colors)], 'width':1.35},
                                  'marker':{'type':'none'}})
            chart.set_x_axis({'name':'Offset frequency (Hz)', 'log_base':10,
                              'min':min_offset, 'max':max_offset,
                              'major_gridlines':{'visible':True,'line':{'color':'#E6EEF4'}}})
            chart.set_y_axis({'name':'Phase noise (dBc/Hz)', 'min':ylo, 'max':yhi,
                              'major_gridlines':{'visible':True,'line':{'color':'#E2EAF0'}}})
            chart.set_legend({'position':'bottom', 'font':{'size':8}})
            chart.set_chartarea({'border':{'none':True}})
            chart.set_plotarea({'border':{'none':True}})
            chart.set_title({'name': f'PN comparison | {name}'})
            chart.set_size({'width':920,'height':400})
            overlay.insert_chart(start+2, 1, chart, {'x_offset':2,'y_offset':2})
            num_charts += 1
        if not num_charts:
            overlay.write('B7','NO MEASURED TRACES AVAILABLE',f['missing'])

        # ------------ Test_Info: exact provenance and diagnostics ------------
        info = wb.add_worksheet('Test_Info')
        info.set_column('A:A',4)
        info.set_column('B:B',34)
        info.set_column('C:C',85)
        info.merge_range('B2:C3','REPORT PROVENANCE | PN COMPARISON',f['title'])
        sample = plan.get('sample',{})
        settings = plan.get('user_configuration',{})
        info_rows = [
            ('Case',plan.get('case','unknown')),
            ('Run directory',str(run_dir)),
            ('PCB ID',sample.get('pcb_id','')),
            ('CMOS chip ID',sample.get('chip_id','')),
            ('SAW resonator ID',sample.get('saw_id','')),
            ('Test name',sample.get('test_name','')),
            ('Test note',sample.get('test_note','')),
            ('Operator',sample.get('operator','')),
            ('Temperature C (user recorded)',sample.get('temperature_c','')),
            ('VDD V (user recorded)',sample.get('vdd_v','')),
            ('Active scan fields',', '.join(active)),
            ('Test mode',settings.get('mode','')),
            ('Settle s',plan.get('settle_s','')),
            ('Acquire s',plan.get('acquire_s','')),
            ('E5052B host',plan.get('instrument_host','')),
            ('Planned points',len(records)),
            ('Measured PN PASS',sum(_measured(r) for r in records)),
            ('Original PNG available',len(images)),
            ('Missing/unreadable PNG',len(records)-len(images)),
            ('Points with raw PN trace',sum(bool(traces.get(_key(r))) for r in records)),
            ('Overlay charts',num_charts),
            ('Original summary CSV',SUMMARY_NAME),
            ('Original trace CSV',TRACES_NAME),
            ('Original PNG encoding','Source PNG embedded unchanged; display dimensions scaled only'),
            ('Trace source','Actual E5052B CSV; no interpolation or remeasurement'),
            ('Run result status',result.get('status','')),
        ]
        for i,(label,value) in enumerate(info_rows,5):
            _write_value(info,i,1,label,f['tag'])
            _write_value(info,i,2,value,f['txt'])
        info.write(len(info_rows)+8,1,'NOTE: PN screenshot is unavailable when capture was run with --no-screenshot or screenshot transfer failed.',f['small'])
    finally:
        wb.close()
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Generate PN Comparison Excel from stored data only (no hardware)')
    parser.add_argument('--run-dir',required=True, help='Path to an existing run_YYYYMMDD_HHMMSS directory')
    parser.add_argument('--gallery-columns',type=int,choices=(1,2),default=2)
    args = parser.parse_args(argv)
    try:
        path = generate_pn_comparison(args.run_dir,gallery_columns=args.gallery_columns)
    except Exception as exc:
        parser.exit(1,f'[PN COMPARE ERROR] {type(exc).__name__}: {exc}\n')
    print(f'[PN COMPARE PASS] {path}')
    print('No SPI/E5052B connected; existing measured files were not modified.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
