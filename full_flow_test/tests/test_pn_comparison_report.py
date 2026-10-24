"""Pure offline regression for PN Comparison report (no SPI/E5052B)."""
from __future__ import annotations
import csv
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from PIL import Image
from utils.pn_comparison_report import generate_pn_comparison


class PNComparisonTests(unittest.TestCase):
    def _build_run(self, tmp: Path, *, missing: bool=False) -> tuple[Path,dict[int,bytes]]:
        run=tmp/'run_20261024_120000'
        for folder in ('screenshots','traces','summary'):
            (run/folder).mkdir(parents=True)
        (run/'run_plan.json').write_text(json.dumps({
            'case':'case_saw_pn_sweep_2param',
            'sample':{'pcb_id':'PCB02','chip_id':'CHIP03','saw_id':'SAW01'},
            'user_configuration':{'active_scan_fields':['IBIAS','IND_CAP'],'mode':'FULL_SWEEP'},
            'settle_s':2,'acquire_s':12,'instrument_host':'127.0.0.1'}))
        originals={}
        with (run/'summary_ibias_swcap_indcap.csv').open('w',encoding='utf-8-sig',newline='') as fh, \
                (run/'all_traces_long.csv').open('w',encoding='utf-8-sig',newline='') as tf:
            fields=['step','ibias_dec','swcap_dec','ind_cap_dec','spi_verify','capture_status',
                    'carrier_mhz','output_power_dbm','PN_1kHz','PN_10kHz',
                    'PN_100kHz','PN_1MHz','PN_10MHz','jitter_fs','screenshot_path',
                    'raw_csv_path','capture_time']
            summary=csv.DictWriter(fh,fieldnames=fields);summary.writeheader()
            trace=csv.writer(tf);trace.writerow(['step','ibias_dec','swcap_dec','ind_cap_dec',
                                                'ind_p_dec','ind_n_dec','offset_hz','phase_noise_dbc_hz'])
            count=0
            for ib in (0,6,12,15):
                for ind in (0,4,7):
                    count+=1
                    pic_name=f'img_step{count:03d}_IBIAS{ib}_IND{ind}.png'
                    if not(missing and count==2):
                        pic=run/'screenshots'/pic_name
                        Image.new('RGB',(1024,728),(count*10,40,130)).save(pic)
                        originals[count]=pic.read_bytes()
                    summary.writerow({'step':count,'ibias_dec':ib,'swcap_dec':8,'ind_cap_dec':ind,
                                    'spi_verify':'PASS','capture_status':'PASS','carrier_mhz':3470+count/1000,
                                    'output_power_dbm':-48.0,'PN_1kHz':-90-count,
                                    'PN_10kHz':-102-count,'PN_100kHz':-110-count,
                                    'PN_1MHz':-115-count/2,'PN_10MHz':-125-count,
                                    'jitter_fs':500-count*3,
                                    'screenshot_path':f'outputs\\fullflow\\case\\run\\screenshots\\{pic_name}',
                                    'raw_csv_path':f'outputs\\fullflow\\case\\run\\traces\\step{count:03d}.csv',
                                    'capture_time':'2026-10-24 12:34:56'})
                    for offset in (100,1000,10000,100000,1000000,10000000):
                        trace.writerow([count,ib,8,ind,ind,ind,offset,-90-count-offset/1000000])
        return run,originals

    def test_2param_overview_embeds_original_png_and_chart_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            run,pngs=self._build_run(Path(tmp))
            target=generate_pn_comparison(run)
            with zipfile.ZipFile(target) as archive:
                self.assertIsNone(archive.testzip())
                wb=archive.read('xl/workbook.xml').decode()
                for name in ('Overview','PN_Gallery','PN_Overlay','Raw_PN','Test_Info','Chart_Data'):
                    self.assertIn(f'name="{name}"',wb)
                charts=[name for name in archive.namelist() if name.startswith('xl/charts/chart') and name.endswith('.xml')]
                self.assertEqual(len(charts),6)  # 4 fixed IBIAS groups + 2 best-of plots
                images=[archive.read(n) for n in archive.namelist() if n.startswith('xl/media/')]
                orig_hash={hashlib.sha256(v).hexdigest() for v in pngs.values()}
                actual_hash={hashlib.sha256(v).hexdigest() for v in images}
                self.assertEqual(orig_hash,actual_hash,'Images were resized/re-encoded')
                self.assertIn('logBase',archive.read(charts[0]).decode())
                ws=archive.read('xl/worksheets/sheet1.xml').decode()
                self.assertIn('r="Q5"',ws)
                # PNGs are Office drawing objects, anchored on Q (0-based column 16),
                # not literal spreadsheet cell values.
                drawing=archive.read('xl/drawings/drawing1.xml').decode()
                self.assertIn('<xdr:col>16</xdr:col>',drawing)
                self.assertIn('<xdr:row>5</xdr:row>',drawing)
                self.assertEqual(len([n for n in archive.namelist() if n.startswith('xl/drawings/drawing') and n.endswith('.xml')]),3)  # Overview + Gallery + Overlay

    def test_missing_png_is_reported_without_substitution(self):
        with tempfile.TemporaryDirectory() as tmp:
            run,pngs=self._build_run(Path(tmp),missing=True)
            with zipfile.ZipFile(generate_pn_comparison(run)) as archive:
                images=[archive.read(n) for n in archive.namelist() if n.startswith('xl/media/')]
                self.assertEqual(len(images),11)
                self.assertTrue(all(v in pngs.values() for v in images))
                self.assertIn('NO SCREENSHOT',archive.read('xl/sharedStrings.xml').decode())

    def test_existing_real_capture_rebuild_no_instrument(self):
        # The supplied ZIP's run is tested with a standalone command separately.
        with tempfile.TemporaryDirectory() as tmp:
            run,_=self._build_run(Path(tmp))
            actual=generate_pn_comparison(run)
            self.assertTrue(actual.exists())
            self.assertGreater(actual.stat().st_size,10000)


if __name__=='__main__':
    unittest.main()
