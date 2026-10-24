# PN Comparison XLSX - SAW Auto Test v2.0

## What changes?

The original measurement and export pipeline is unchanged. After a 1Param,
2Param or 3Param test, `utils/pn_comparison_report.py` reads the already saved
`summary_ibias_swcap_indcap.csv`, `all_traces_long.csv` and `screenshots/*.png`
and adds **`pn_comparison.xlsx`** to the same `run_YYYYMMDD_HHMMSS` directory.
This step opens **no** Ginkgo USB-SPI or E5052B connections.

The standalone XLSX contains:

- **Overview**: one row per tested IBIAS/SWCAP/IND_CAP combination. The last
  column **Q** embeds the corresponding **original PNG screenshot**. The Excel
  drawing is display-scaled to fit the row, but the embedded image's bytes and
  native resolution remain unchanged. Other columns show measured frequency,
  power, PN at selected offsets, jitter and file identification.
- **PN_Gallery**: two-up image gallery with original PNGs and compact measured
  captions. It complements Overview; it does not replace it.
- **PN_Overlay**: Excel-native scatter curves using logarithmic frequency offset
  and the actual captured PN data (no resampling, interpolation or smoothing).
  Grouping uses active scan fields from run_plan: 1Param overlays IND_CAP;
  2Param groups by IBIAS; 3Param groups by IBIAS and SWCAP. Two extra charts
  compare up to the five best valid PN@1MHz and jitter points.
- **Raw_PN**: one row per actual captured PN trace point.
- **Test_Info**: sample metadata, run configuration and missing-data counts.
- **Chart_Data**: hidden numeric backing data for the native Excel charts.

The preexisting `summary_ibias_swcap_indcap.xlsx` is NOT modified or replaced.
Existing per-point XLSX/CSV/PNG files are also unchanged.

## Normal operation

From `full_flow_test`:

```bat
python -m scripts.fullflow.case_saw_pn_sweep_1param --check-point
python -m scripts.fullflow.case_saw_pn_sweep_2param --check-point
python -m scripts.fullflow.case_saw_pn_sweep_3param --check-point
```

Use only one of the commands at a time. The test adds:

```text
[EXCEL PASS] ...summary_ibias_swcap_indcap.xlsx
[PN COMPARE PASS] ...pn_comparison.xlsx
```

The three cases have a new setting:

```python
GENERATE_PN_COMPARISON = True
PN_GALLERY_COLUMNS = 2
```

Set `GENERATE_PN_COMPARISON=False` to skip only the supplemental XLSX.

## Rebuild from a completed run (NO HARDWARE)

```bat
python -m utils.pn_comparison_report --run-dir "outputs/fullflow/case_saw_pn_sweep_2param/run_YYYYMMDD_HHMMSS"
```

Use an existing run path, relative or absolute. This generates the comparison
workbook only; it does not rerun or reconnect to any instruments.

The existing Case command `--report-only RUN_DIR` is also supported and now
produces `pn_comparison.xlsx` in addition to its legacy preview report.

## Important data integrity behavior

- Missing screenshots are marked **NO SCREENSHOT**; the report does not put
  another step's screenshot into that row. If `--no-screenshot` was used,
  pictures are genuinely absent.
- A screenshot corrupted on disk is not embedded. All surviving source PNGs
  are embedded at their original resolution; the report never converts them to
  lossy JPEG or reduces their stored pixel count.
- Raw PN traces are read from `all_traces_long.csv`. If it is absent, the
  per-point `traces` files referenced by the summary are used if available.
  Missing traces are omitted, not fabricated.
- The supplemental workbook is produced even after a partial sweep (provided
  at least one summary row has been saved). Its failure is logged as
  `[PN COMPARE ERROR]`, but will not discard or invalidate the already acquired
  SPI/PN measurements and existing summary reports.
- Excel row height is limited, so screenshots are display-scaled in the
  Overview and Gallery cells; the source PNG is still embedded unchanged and
  can be viewed at higher zoom or extracted from `xl/media/` inside the XLSX.
- Output paths from historical Windows runs are resolved against **this run's**
  own `screenshots/` and `traces/` directories only. No files from other runs
  are substituted based solely on step number.

## Basic offline test

```bat
python -m unittest tests.test_pn_comparison_report -v
```
