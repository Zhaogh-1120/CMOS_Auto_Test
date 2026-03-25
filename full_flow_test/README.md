# Ginkgo field-based SPI automation + E5052B integration

This project keeps SPI control and E5052B phase-noise capture decoupled, then combines them in full-flow scripts.

## Confirmed SPI mode
- control_mode = 0
- cpol = 0
- cpha = 0
- read protocol = `80 [addr]`
- readback byte = `raw_rx[1]`

## Layout
- `protocol/` SPI register and field operations
- `instruments/e5052b/` E5052B SCPI client, capture pipeline, metrics, exporters
- `scripts/basic/` pure SPI examples, no measurement hook
- `scripts/loops/` pure SPI sweeps, no measurement hook
- `scripts/templates/` reusable SPI templates
- `scripts/fullflow/` orchestration cases that combine SPI with E5052B

## E5052B integration design
- SPI layer remains independent.
- E5052B is a callable module, not a standalone giant script.
- Full-flow cases decide whether to measure, whether to wait, and whether to save screenshots.
- All full-flow cases load instrument parameters from `config/instrument/e5052b_config.json`.

## First validation order in VSCode
1. Verify original SPI functions still work:
   - `python main.py field-write-read --name CFG_OSC2_GMP_NUM --value 5`
2. Validate E5052B standalone capture only:
   - `python -m scripts.fullflow.e5052b_capture_once`
3. Validate integrated case without screenshot:
   - `python -m scripts.fullflow.case_spi_then_capture_no_png`
4. Validate integrated case with screenshot:
   - `python -m scripts.fullflow.case_spi_then_capture`
5. Validate integrated case with delay:
   - `python -m scripts.fullflow.case_spi_wait_then_capture`
6. Validate sweep + capture:
   - `python -m scripts.fullflow.case_sweep_and_capture`

## Useful SPI commands
```bash
python main.py field-list
python main.py field-read --name CFG_OSC2_GMP_NUM
python main.py field-write --name CFG_OSC2_GMP_NUM --value 5
python main.py field-write-read --name CFG_OSC2_GMP_NUM --value 5
python main.py field-sweep --name CFG_OSC2_GMP_NUM --start 0 --stop 7 --step 1
```

## Example full-flow cases
```bash
python -m scripts.fullflow.e5052b_capture_once
python -m scripts.fullflow.case_simple_spi
python -m scripts.fullflow.case_spi_then_capture
python -m scripts.fullflow.case_spi_wait_then_capture
python -m scripts.fullflow.case_spi_then_capture_no_png
python -m scripts.fullflow.case_sweep_and_capture
python -m scripts.fullflow.case_multi_field_sweep_capture
python -m scripts.fullflow.case_preset_then_single_sweep
python -m scripts.fullflow.case_preset_then_nested_sweep_capture
python -m scripts.fullflow.case_discrete_sweep_capture
python -m scripts.fullflow.case_preset_then_discrete_sweep_capture
python -m scripts.fullflow.case_nested_discrete_sweep_capture
```

## Output layout
Every capture run now creates a dedicated run folder.

```text
outputs/
  e5052b/
    capture_once/
      run_YYYYMMDD_HHMMSS/
        summary/
        traces/
        screenshots/
  fullflow/
    case_xxx/
      run_YYYYMMDD_HHMMSS/
        summary/
        traces/
        screenshots/
        merged/
```

## Preset + sweep and discrete sweep
- Preset helper: `core.sweeper.apply_presets(chip, presets)`
- Discrete/continuous value helper: `utils.value_spec.iter_value_spec(spec)`
- Continuous spec example:
  - `{"start": 0, "stop": 7, "step": 1}`
- Discrete spec example:
  - `{"values": [0, 3, 4, 7]}`

## Notes
- `scripts/basic/` and `scripts/loops/` remain pure SPI. They do not attach a hook by default.
- `scripts/fullflow/` is where case orchestration lives.
- Update `config/instrument/e5052b_config.json` before running against your instrument.
