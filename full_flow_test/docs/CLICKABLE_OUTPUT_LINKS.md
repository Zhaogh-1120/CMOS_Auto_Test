# VS Code clickable test-result paths (1Param / 2Param / 3Param)

## Changes and scope

Only the terminal/log presentation in the three `scripts/fullflow/case_saw_pn_sweep_*param.py` scripts has changed. A shared, dependency-free helper is added at `utils/terminal_links.py`. No register map, SPI write/read, E5052B SCPI, capture timing, measurement math, Excel sheets/charts, CSV format, or output directory is modified.

At each `[SAVE PASS]`, the terminal shows clickable file names for raw PN CSV, PNG screenshot, and per-point XLSX. At `[EXCEL PASS]`, it also links the summary Excel file. At the end of a run (including errors/interrupts), `[OUTPUT LINKS]` points to the run directory, summary report, summary CSV, raw trace CSV, run log, and output subfolders, if they exist.

## How to open

Run scripts from **VS Code integrated terminal** as usual, for example:

```cmd
python -m scripts.fullflow.case_saw_pn_sweep_1param --check-point
```

Use **Ctrl+left-click** (or the terminal's link-opening gesture) on a displayed path / filename. Terminal hyperlink support determines whether a local file opens in VS Code or its associated application. Clicking a directory can navigate/open it using VS Code's local file URI handler. The script does not automatically launch Explorer, Excel, or an image viewer.

When command output is redirected to a file or piped (non-interactive), plain **absolute** paths are printed instead of terminal control codes. The saved `run_log.txt` always contains absolute paths as **plain text only**, without OSC 8 or ANSI hyperlink control sequences. VS Code may auto-detect the plain paths inside `run_log.txt` for Ctrl+click as well.

## Important

- No change to existing `OUTPUT_BASE_DIR`. The original `outputs/fullflow/case_saw_pn_sweep_*param/run_*/` structure remains intact.
- The helper uses `Path.resolve().as_uri()` to encode Windows paths, including spaces and Chinese characters, as standard `file://` URIs.
- If a requested file was not saved, it is not presented as a successful clickable output link.
- Existing readback, capture, reporting, snapshot and restore tests should still pass.
- Tests: `python -m unittest tests.test_terminal_output_links tests.test_parallel_migration_offline -v`.
