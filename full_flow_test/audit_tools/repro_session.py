import sys,os
from pathlib import Path
p=Path(os.environ['SPI_AUDIT_PROJECT']);sys.path.insert(0,str(p))
from tests import test_spi_read_protocol_mock as fake
from protocol.chip_spi import ChipSpi
from core.session import TestSession
class IgnoreWrites(fake.FakeBus):
 def write(self,d,s,data):
  data=bytes(data);self.frames.append(('write',data))
  if (data[0]&0xE0)==0:self.addr=data[1]
  return 0
fake._bus=IgnoreWrites()
chip=ChipSpi()
s=TestSession(chip, None, runtime_policy={'CONTINUE_ON_ERROR':False,'RAISE_ON_SPI_VERIFY_FAIL':False})
rec=s.run_field_write_read('CFG_OSC2_IDAC_IBIAS',10)
print('spi_verify_result:',rec.spi_result.verify_result)
print('overall_status_without_finalize:',rec.overall_status)
print('overall_status_after_finalize:',end=' ');rec.finalize_statuses();print(rec.overall_status)
