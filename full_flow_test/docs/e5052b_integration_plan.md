# E5052B integration plan

## Purpose
Integrate E5052B phase-noise capture into the existing SPI project without polluting the SPI layer.

## Layering
1. `protocol/chip_spi.py` keeps SPI-only logic.
2. `instruments/e5052b/` provides standalone E5052B capture capability.
3. `scripts/fullflow/` orchestrates specific test cases.

## Validation order
1. SPI only: verify `main.py` and `scripts/basic/`.
2. E5052B only: verify `python -m scripts.fullflow.e5052b_capture_once`.
3. Full flow no png.
4. Full flow with png.
5. Full flow with delay.
6. Sweep + capture.
