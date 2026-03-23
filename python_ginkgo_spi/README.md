# Ginkgo field-based SPI automation

This version adds direct field-name operations based on your uploaded register list.

## Confirmed SPI mode
- control_mode = 0
- cpol = 0
- cpha = 0
- read protocol = `80 [addr]`
- readback byte = `raw_rx[1]`

## New capability
You can now operate by field name instead of only by whole-register address.

## Name matching
You can use either:
- the full field name from Excel, for example `CFG_OSC2_GMP_NUM<2:0>`
- the alias without `<bits>`, for example `CFG_OSC2_GMP_NUM`

## Decimal write rule
All `field-*` commands use decimal values.

## Useful commands

### list all available fields
python main.py field-list

### read a field by name
python main.py field-read --name CFG_OSC2_GMP_NUM

### write a field with a decimal value
python main.py field-write --name CFG_OSC2_GMP_NUM --value 5

### write then read back a field and get PASS/FAIL
python main.py field-write-read --name CFG_OSC2_GMP_NUM --value 5

### sweep a field in decimal
python main.py field-sweep --name CFG_OSC2_GMP_NUM --start 0 --stop 7 --step 1

### run the example scripts from VSCode terminal
python -m scripts.field_demo
python -m scripts.field_sweep_demo

## About other bits in the same register
A field write reads the current whole-register value first, then only updates the target bit field, then writes the merged register value back.

## Future 5052B hook
A placeholder file is reserved at `instruments/inst_5052b.py`.


## Restructured layout
This package was reorganized into `driver/`, `protocol/`, `core/`, `scripts/`, `tests/`, and `config/` with portable VSCode settings under `.vscode/`. Existing original paths were preserved for compatibility.
