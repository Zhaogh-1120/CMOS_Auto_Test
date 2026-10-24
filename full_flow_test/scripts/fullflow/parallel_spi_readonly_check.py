"""Parallel SAW read-only SPI preflight.

From full_flow_test:
  python -m scripts.fullflow.parallel_spi_readonly_check           # map-only; NO hardware
  python -m scripts.fullflow.parallel_spi_readonly_check --read    # SPI read-only REG05..REG14

Never calls chip.write_reg(), does not restore registers, never initializes defaults.
"""
from __future__ import annotations
import argparse
from datetime import datetime
from protocol.register_map import RegisterMap

ADDRESSES = tuple(range(0x05, 0x15))
REQUIRED_FIELDS = {
    'CFG_OSC_SWCAP': (0x05, 0x0F, 0),
    'CFG_OSC_IND_SWCAP_N': (0x06, 0x38, 3),
    'CFG_OSC_IND_SWCAP_P': (0x06, 0x07, 0),
    'CFG_OSC_IDAC_IBIAS': (0x07, 0x1F, 0),
}

def preflight_map() -> RegisterMap:
    regmap = RegisterMap()
    reg_addrs = tuple(sorted(regmap.defaults_by_address))
    if reg_addrs != ADDRESSES:
        raise RuntimeError(f'Register Map addresses not REG05..REG14: {reg_addrs!r}')
    for name, (addr, mask, lsb) in REQUIRED_FIELDS.items():
        fd = regmap.resolve(name)
        if (fd.address, fd.mask, fd.lsb) != (addr, mask, lsb):
            raise RuntimeError(f'{name} unexpectedly maps to {fd}')
    print(f'[MAP PASS] {len(ADDRESSES)} registers / {len(regmap.fields)} fields')
    for name, (addr, mask, lsb) in REQUIRED_FIELDS.items():
        print(f'  {name:<27} REG{addr:02X} mask=0x{mask:02X} lsb={lsb}')
    print('[INFO] Excel reference defaults are metadata only; no values were sent to hardware')
    return regmap

def main() -> int:
    parser=argparse.ArgumentParser(description='Parallel SAW register map and optional SPI read-only verification')
    parser.add_argument('--read',action='store_true',help='Connect Ginkgo and read all valid register values, without any data writes')
    args=parser.parse_args()
    preflight_map()
    if not args.read:
        print('[PLAN ONLY] Hardware not opened. To read real silicon, add --read')
        return 0
    from protocol.chip_spi import ChipSpi
    print('[SPI READ ONLY] Reading REG05..REG14; no write-data commands')
    with ChipSpi() as chip:
        values={}
        for addr in ADDRESSES:
            val=chip.read_reg(addr)
            values[addr]=val
            print(f'  REG{addr:02X}: 0x{val:02X}  bin={val:08b}  dec={val}')
        get=lambda name: ((values[chip.get_field(name).address] & chip.get_field(name).mask)>>chip.get_field(name).lsb)
        p,n=get('CFG_OSC_IND_SWCAP_P'),get('CFG_OSC_IND_SWCAP_N')
        print(f'[IND_CAP] P={p}, N={n}  '+('SYNC' if p==n else 'DIFFERENT - values kept unchanged'))
    print(f'[SPI READ PASS] {len(values)}/{len(ADDRESSES)} registers read at {datetime.now().isoformat(timespec="seconds")}')
    return 0

if __name__=='__main__':raise SystemExit(main())
