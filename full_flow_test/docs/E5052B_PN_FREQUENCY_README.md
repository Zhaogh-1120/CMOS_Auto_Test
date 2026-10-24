# E5052B frequency display-only update (PN mode only)

This release restores the original Phase Noise capture source: `:CALC:PN1:DATA:CARR?`.
It **does not** switch to Freq & Power mode, change the instrument configuration,
acquire any additional SCPI data or introduce frequency fallback warnings.
The returned numeric carrier is preserved as `carrier_hz` and divided by 1e6
for `carrier_mhz`. The Excel MHz frequency columns are displayed to six
decimal places (1 Hz in MHz units), but **this is a display precision**, not a
claim that the E5052B PN CARR frequency resolution is 1 Hz. If the instrument
returns frequency values in 8 kHz increments, those increments remain.

SPI/scan behavior, E5052B PN acquisition, phase-noise/Jitter calculations,
output file names and folder structure are unchanged.

Run a safe single-point verification (short Windows output path):

    python -m scripts.fullflow.case_saw_pn_sweep_1param --check-point --output-dir E:\SAW_OUT\1param

A true finer-resolution frequency reading requires a supported measurement
source with sufficient input power; it cannot be created by formatting.
