"""Parallel SAW register-map + 1/2/3Param offline regression; no hardware access.
Run from full_flow_test: python -m unittest tests.test_parallel_migration_offline -v
"""
from __future__ import annotations
import contextlib
import csv
import importlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from protocol.register_map import RegisterMap

REG_START, REG_STOP = 0x05, 0x14
SCAN_ADDR = {'IBIAS': 0x07, 'SWCAP': 0x05, 'IND_CAP': 0x06}

class FakeChip:
    def __init__(self, fail_addr=None):
        self.regmap=RegisterMap()
        self.values={int(x[3:],16):val for x,val in ((key,int(key[3:],16)*7%256) for key in [f'REG{k:02X}' for k in range(REG_START,REG_STOP+1)])}
        # Realistic mixed values incl. reserved bit positions; P = N = 3.
        self.values[0x05]=0xB8
        self.values[0x06]=0xDB  # bits [5:3]=3 and [2:0]=3; preserve bits 7:6
        self.values[0x07]=0xCD  # keep bits 7:5 through IBIAS sweeps
        self.initial=self.values.copy()
        self.writes=[]
        self.fail_addr=fail_addr
    def read_reg(self,a):
        if a==self.fail_addr:raise RuntimeError('Simulated read failure')
        return self.values[a]
    def write_reg(self,a,v):
        self.writes.append((a,v))
        self.values[a]=v
    def get_field(self,name):return self.regmap.resolve(name)
    def compose_field_value(self,rv,field,code):
        assert 0<=code<=field.max_decimal
        return (rv & ~field.mask)|((code<<field.lsb)&field.mask)

class FakeInstrument:
    def __init__(self):self.resumes=0
    def resume_display(self):self.resumes+=1

class FakeOptions:
    save_csv=True
    save_excel=True
    save_screenshot=True
    freeze_before_capture=True
    delay_before_capture_s=0.0

class FakeCapture:
    def __init__(self,dir,step):
        self.offsets_hz=[100.0,1e3,1e4,1e5,1e6,1e7]
        self.phase_noise_dbc_hz=[-70.0,-83.0,-102.0,-113.0,-121.0,-128.0]
        self.output_frequency_hz=3.45e9+step*10000
        self.output_power_dbm=-32.0
        self.capture_time='2026-10-23T20:00:00'
        self.integral_start_hz=12000
        self.integral_stop_hz=20e6
        self.jitter_fs=450+step
        self.rms_rad=0.03
        self.integrated_phase_noise_dbc=-40
        self.residual_fm_hz=5.0
        self.raw_csv_path=str(dir/'traces'/f'raw_{step:03d}.csv')
        self.excel_path=str(dir/'summary'/f'pn_{step:03d}.xlsx')
        self.screenshot_path=str(dir/'screenshots'/f'pn_{step:03d}.png')
        for name in [self.raw_csv_path,self.excel_path,self.screenshot_path]:
            f=Path(name);f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b'OFFLINE_FAKE')
    def key_point_dict(self):
        return {'PN_100Hz':-70,'PN_1kHz':-83,'PN_10kHz':-102,'PN_100kHz':-113,
                'PN_400kHz':-118,'PN_1MHz':-121,'PN_10MHz':-128,'PN_20MHz':-130,'PN_40MHz':-131}

def capture_mock(*,client,options,out_dir,shot_name,case_name,step_idx,field_names,active_values):
    assert 'CFG_OSC_IND_SWCAP_P' in active_values
    assert active_values['CFG_OSC_IND_SWCAP_P']==active_values['CFG_OSC_IND_SWCAP_N']
    return FakeCapture(Path(out_dir),step_idx+1)

class ParallelMigrationTest(unittest.TestCase):
    def test_01_register_map_matches_excel(self):
        mp=RegisterMap()
        self.assertEqual(len(mp.fields),35)
        self.assertEqual(list(sorted(mp.defaults_by_address)),list(range(REG_START,REG_STOP+1)))
        reference={5:0x08,6:0x1B,7:0x0D,8:0x48,9:0x88,10:0x0F,11:0x43,12:0x98,
                   13:0x98,14:0x88,15:0x89,16:0x2E,17:0x1A,18:0x02,19:0x13,20:0x1F}
        self.assertEqual(mp.defaults_by_address,reference)
        for name,address,msb,lsb in [
            ('CFG_OSC_IDAC_IBIAS',7,4,0),('CFG_OSC_SWCAP',5,3,0),
            ('CFG_OSC_IND_SWCAP_P',6,2,0),('CFG_OSC_IND_SWCAP_N',6,5,3)]:
            f=mp.resolve(name)
            self.assertEqual((f.address,f.msb,f.lsb),(address,msb,lsb))
        self.assertEqual(mp.resolve_register_name('REG14'),0x14)

    def test_02_run_all_templates(self):
        expected={1:({6},5),2:({7,6},12),3:({7,5,6},48)}
        for dim,(addr,total) in expected.items():
            with self.subTest(params=dim),tempfile.TemporaryDirectory() as tmp:
                mod=importlib.import_module(f'scripts.fullflow.case_saw_pn_sweep_{dim}param')
                points=mod.scan_points()
                self.assertEqual(len(points),total)
                self.assertEqual((mod.SNAPSHOT_REG_START,mod.SNAPSHOT_REG_STOP),(REG_START,REG_STOP))
                f=Path(tmp)
                mod.write_json(f/'run_plan.json',{
                    'user_configuration':{'IBIAS':{},'SWCAP':{},'IND_CAP':{}},
                    'sample':{'pcb_id':'PCB01','chip_id':'CHIP01','saw_id':'SAW01'},
                    'settle_s':0,'acquire_s':0,'instrument_host':'simulated',
                    'save_screenshot':True,'report_top_n':30})
                c=FakeChip();inst=FakeInstrument()
                with contextlib.redirect_stdout(io.StringIO()):
                    obj=mod.run_sweep(c,inst,points,f,capture_mock,FakeOptions(),settle_s=0,acquisition_s=0)
                self.assertEqual(obj['status'],'PASS')
                self.assertEqual(c.initial,c.values,'Chip not restored')
                self.assertEqual({a for a,_ in c.writes},addr,'Non-target register written')
                with (f/'summary_ibias_swcap_indcap.csv').open(encoding='utf-8-sig') as handle:
                    self.assertEqual(len(list(csv.DictReader(handle))),total)
                self.assertEqual(inst.resumes,total*2)
                initial=json.loads((f/'initial_register_snapshot.json').read_text())
                final=json.loads((f/'final_register_snapshot.json').read_text())
                self.assertEqual(len(initial['registers']),16)
                self.assertEqual(len(final['registers']),16)
                comparison=json.loads((f/'register_comparison.json').read_text())
                self.assertEqual(comparison['overall'],'PASS')
                self.assertEqual(len(comparison['registers']),16)
                self.assertEqual(set(comparison['written_registers']),{f'REG{x:02X}' for x in addr})
                with zipfile.ZipFile(f/'summary_ibias_swcap_indcap.xlsx') as z:
                    charts=[n for n in z.namelist() if n.startswith('xl/charts/chart') and n.endswith('.xml')]
                    self.assertEqual(len(charts),20)
                    s=z.read('xl/sharedStrings.xml').decode('utf-8')
                    self.assertIn('REG07',s)
                    self.assertIn('REG05',s)
                    self.assertIn('REG06',s)
                print(f'PARALLEL {dim}param: {total} cases, 16 readbacks, {len(c.writes)} writes, 20 graphs PASS')

    def test_03_initial_read_error_prevents_writes(self):
        mod=importlib.import_module('scripts.fullflow.case_saw_pn_sweep_1param')
        with tempfile.TemporaryDirectory() as tmp:
            chip=FakeChip(fail_addr=0x0A)
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError,'snapshot failed'):
                    mod.run_sweep(chip,FakeInstrument(),mod.scan_points()[:1],Path(tmp),capture_mock,FakeOptions(),settle_s=0,acquisition_s=0)
            self.assertFalse(chip.writes)
            self.assertEqual(json.loads((Path(tmp)/'run_result.json').read_text())['status'],'FAIL')

    def test_04_untouched_register_change_is_detected(self):
        mod=importlib.import_module('scripts.fullflow.case_saw_pn_sweep_1param')
        with tempfile.TemporaryDirectory() as tmp:
            chip=FakeChip()
            def modify_other_reg(**kw):
                chip.values[0x14]^=1
                return capture_mock(**kw)
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError,'verification failed'):
                    mod.run_sweep(chip,FakeInstrument(),mod.scan_points()[:1],Path(tmp),modify_other_reg,FakeOptions(),settle_s=0,acquisition_s=0)
            compare=json.loads((Path(tmp)/'register_comparison.json').read_text())
            self.assertIn('REG14',compare['failed_registers'])
            self.assertNotIn(0x14,{a for a,_ in chip.writes})

if __name__=='__main__':unittest.main()
