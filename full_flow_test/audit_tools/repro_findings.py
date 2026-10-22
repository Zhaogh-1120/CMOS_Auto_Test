"""Intentional negative-path reproductions; no actual USB SPI calls."""
import io,sys,os
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout,redirect_stderr
project=Path(os.environ['SPI_AUDIT_PROJECT'])
sys.path.insert(0,str(project))
from tests import test_spi_read_protocol_mock as mockdrv
from protocol.chip_spi import ChipSpi
import protocol.chip_spi as chip_module
import main

def cli(*args):
    fakeout,fakeerr=io.StringIO(),io.StringIO()
    with patch.object(sys,'argv',['main.py',*args]),redirect_stdout(fakeout),redirect_stderr(fakeerr):
        try:main.main();code=0
        except SystemExit as err:code=err.code
    return code, fakeout.getvalue().strip(),fakeerr.getvalue().strip()

print('CASE A: REG write/read mismatch exits 0')
class IgnoreWrites(mockdrv.FakeBus):
    def write(self,d,s,frame):
        data=bytes(frame); self.frames.append(('write',data))
        if (data[0]&0xE0)==0x00:self.addr=data[1]
        return 0
mockdrv._bus=IgnoreWrites()
code,out,err=cli('write-read','--reg','0x20','--value','0x54')
print('exit_code=',code,'out=',out,'data_written=',mockdrv._bus.regs[0x20])
assert code==0 and 'result=FAIL' in out

print('CASE B: Field verify PASS despite unrelated-bit corruption')
class CorruptLowBit(mockdrv.FakeBus):
    def write(self,d,s,frame):
        ret=super().write(d,s,frame)
        if bytes(frame)[0]==0x40: self.regs[self.addr] ^= 1
        return ret
mockdrv._bus=CorruptLowBit()
info=ChipSpi().write_field_then_read('CFG_OSC2_IDAC_IBIAS',10)
print('verify=',info['verify_result'], 'expected_REG=',info['after_reg_hex'],'real_REG=',hex(mockdrv._bus.regs[0x20]))
assert info['verify_result']=='PASS' and int(info['after_reg_hex'],16)!=mockdrv._bus.regs[0x20]

print('CASE C: CLI sweep continues after readback mismatch')
mockdrv._bus=IgnoreWrites()
code,out,err=cli('sweep','--reg','0x20','--start','0','--stop','2')
print('exit_code=',code,'verify_lines=',out.count('VERIFY'),'fail_lines=',out.count('result=FAIL'))
assert code==0 and out.count('VERIFY')==3 and out.count('result=FAIL')>=2

print('CASE D: Partial batch_write before invalid later entry')
mockdrv._bus=mockdrv.FakeBus()
try: ChipSpi().batch_write([(0x20,0x5A),(0x21,256)])
except ValueError as err: print('exception=',str(err),'REG20 now=',hex(mockdrv._bus.regs[0x20]))
assert mockdrv._bus.regs[0x20]==0x5A

print('CASE E: SPI init fails but already-open USB handle not closed')
mockdrv._bus=mockdrv.FakeBus()
closed=[]
with patch.object(chip_module,'init_spi',return_value=-3),patch.object(chip_module,'close_device',side_effect=lambda index:closed.append(index)):
    try:ChipSpi().open()
    except Exception as err:print('exception=',str(err),'close_calls=',closed)
assert not closed

print('CASE F: --clock and --cpol invalid values enter device configuration')
mockdrv._bus=mockdrv.FakeBus()
code,out,err=cli('read','--reg','0x20','--clock','-1','--cpol','2','--cpha','4','--control-mode','99')
print('exit_code=',code,'result_line=',out[:100],'stderr=',err[:100])
assert code==0

print('CASE G: Chip sweep stop only included when step lands exactly on stop')
chip=ChipSpi(); print('range(0,5,2)=',list(chip.validate_sweep(0,5,2,31)))
assert list(chip.validate_sweep(0,5,2,31)) == [0,2,4]

print('ALL 7 ISSUES REPRODUCED (as currently implemented).')
