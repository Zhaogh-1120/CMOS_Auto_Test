"""Extended read/write audits against unchanged Enhanced_Color project, fake SPI hardware."""
import sys, unittest, random, json, io, os
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch
base=Path(os.environ['SPI_AUDIT_PROJECT'])
sys.path.insert(0,str(base))
from tests import test_spi_read_protocol_mock as fake
from protocol.chip_spi import ChipSpi
from main import main as cli

class Extra(unittest.TestCase):
  def setUp(self): fake._bus = fake.FakeBus()
  def cli(self,*args):
    out,err=io.StringIO(),io.StringIO()
    with patch.object(sys,'argv',['main.py',*args]),redirect_stdout(out),redirect_stderr(err):
      try: cli()
      except SystemExit as ex: return ex.code,out.getvalue(),err.getvalue()
    return 0,out.getvalue(),err.getvalue()
  def test_001_field_29_mask_and_range(self):
    chip=ChipSpi()
    self.assertEqual(len(chip.regmap.fields),29)
    for f in chip.regmap.fields:
      with self.subTest(f=f.name):
        self.assertEqual(f.width,f.msb-f.lsb+1)
        self.assertEqual(f.mask,((1<<f.width)-1)<<f.lsb)
        self.assertEqual(f.max_decimal,(1<<f.width)-1)
        self.assertLessEqual(f.address,255)
        for initial in (0,255,0xA5,0x5A):
          for value in (0, f.max_decimal, f.max_decimal//2):
            self.assertEqual(chip.extract_field_value(chip.compose_field_value(initial,f,value),f),value)
            self.assertEqual(chip.compose_field_value(initial,f,value)&(~f.mask&255),initial&(~f.mask&255))
  def test_002_randomized_29_fields_live_RMW(self):
    chip=ChipSpi(); rng=random.Random(2481)
    for f in chip.regmap.fields:
      for i in range(15):
        initial=rng.randrange(256); val=rng.randrange(f.max_decimal+1)
        fake._bus.regs[f.address]=initial
        result=chip.write_field_then_read(f.alias,val)
        wanted=((initial & (~f.mask&255)) | (val<<f.lsb))
        self.assertEqual(fake._bus.regs[f.address], wanted)
        self.assertEqual(result['verify_result'],'PASS')
        self.assertEqual(result['read_field_decimal'],val)
  def test_003_all_256_addresses_frame_and_raw_rx(self):
    chip=ChipSpi()
    for addr in range(256):
      fake._bus.regs[addr]=(addr*17+7)&255
      self.assertEqual(chip.read_reg(addr),(addr*17+7)&255)
      self.assertEqual(fake._bus.frames[-2:], [('write',bytes([0,addr])),('exchange',b'\x80\x00')])
    self.assertEqual(len(fake._bus.frames),512)
  def test_004_range_boundary_and_dryrun_no_data_writes(self):
    for action in ('write','write-read'):
      for val in ('0','255','0xFF','0b11111111'):
        fake._bus=fake.FakeBus()
        code,out,err=self.cli(action,'--reg','0x20','--value',val,'--dry-run')
        self.assertEqual(code,0); self.assertEqual(fake._bus.regs[0x20],0xAC)
        self.assertFalse(any(x[0]=='write' and x[1][0]==0x40 for x in fake._bus.frames))
      for val in ('-1','256','0x100','0b100000000'):
        fake._bus=fake.FakeBus()
        code,out,err=self.cli(action,'--reg','0x20','--value',val)
        self.assertEqual(code,2); self.assertEqual(fake._bus.frames,[])
    for f in ChipSpi().regmap.fields:
      for val in (str(f.max_decimal),hex(f.max_decimal),bin(f.max_decimal)):
        fake._bus=fake.FakeBus()
        code,out,err=self.cli('field-write','--name',f.alias,'--value',val,'--dry-run')
        self.assertEqual(code,0,err); self.assertEqual(fake._bus.frames,[('write',bytes([0,f.address])),('exchange',b'\x80\x00')])
      for val in (str(f.max_decimal+1), '-1'):
        fake._bus=fake.FakeBus()
        code,out,err=self.cli('field-write','--name',f.alias,'--value',val)
        self.assertEqual(code,2); self.assertEqual(fake._bus.frames,[])
  def test_005_all_fields_output_binary_width_and_order(self):
    for f in ChipSpi().regmap.fields:
      fake._bus = fake.FakeBus()
      fake._bus.regs[f.address]=255
      code,out,err=self.cli('read','--name',f.alias)
      self.assertEqual(code,0,err)
      self.assertIn('value_hex=',out)
      self.assertIn('value_bin=2b'+'1'*f.width,out)
      self.assertIn('value_dec='+str(f.max_decimal),out)
      self.assertLess(out.index('value_hex='),out.index('value_bin='))
      self.assertLess(out.index('value_bin='),out.index('value_dec='))
  def test_006_multi_range_and_default_address_command(self):
    for expr in ('0','0x00','0b0'):
      fake._bus=fake.FakeBus()
      code,out,err=self.cli('read','--reg',expr)
      self.assertEqual(code,0,err)
    for cmd in ('0x00','0x1F'):
      fake._bus=fake.FakeBus()
      code,out,err=self.cli('read','--reg','0x20','--address-cmd',cmd)
      self.assertEqual(code,0,err)
      self.assertEqual(fake._bus.frames[0][1][0],int(cmd,16))
  def test_007_live_field_and_reg_sweeps(self):
    for args,expected_reg in [
      (('sweep','--reg','0x20','--start','3','--stop','0','--step','-1'),0),
      (('field-sweep','--name','CFG_OSC2_GMP_NUM','--start','0','--stop','7','--step','1'),None),
    ]:
      fake._bus=fake.FakeBus()
      code,out,err=self.cli(*args)
      self.assertEqual(code,0,err)
      if expected_reg is not None: self.assertEqual(fake._bus.regs[0x20],expected_reg)
  def test_008_no_write_on_invalid_sweep_across_both_actions(self):
    bad=[('0','256','1'),('7','0','1'),('0','7','-1'),('0','7','0'),('-1','7','1')]
    for action,target in [('sweep',('--reg','0x20')),('field-sweep',('--name','CFG_OSC2_GMP_NUM'))]:
      for start,stop,step in bad:
        fake._bus=fake.FakeBus()
        code,out,err=self.cli(action,*target,'--start',start,'--stop',stop,'--step',step)
        self.assertEqual(code,2); self.assertEqual(fake._bus.frames,[])

if __name__=='__main__':unittest.main(verbosity=2)
