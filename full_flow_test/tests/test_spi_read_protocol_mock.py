"""Offline SPI protocol unit tests. Run from the project directory.

    python -m unittest tests.test_spi_read_protocol_mock -v

Avoids loading hardware-only Ginkgo_Driver.dll: injects a deterministic fake
module BEFORE importing protocol.chip_spi.
"""
from __future__ import annotations

import sys
import types
import unittest

_fake = types.ModuleType("driver.control_spi")

class FakeSpiError(RuntimeError):
    pass

class FakeBus:
    def __init__(self):
        self.regs = {0x20: 0xAC, 0x21: 0x37, 0x05: 0x08, 0x06: 0x1B, 0x07: 0xB5, 0x08: 0x4C}
        self.addr = 0
        self.frames = []
        self.fail_next_write = False

    def write(self, _dev, _spi, data):
        data = bytes(data)
        self.frames.append(("write", data))
        if self.fail_next_write:
            self.fail_next_write = False
            return -10
        if len(data) == 2 and (data[0] & 0xE0) == 0x00:
            self.addr = data[1]
        elif len(data) == 2 and (data[0] & 0xE0) == 0x40:
            self.regs[self.addr] = data[1]
        else:
            raise AssertionError(f"Unexpected SPI write frame: {data!r}")
        return 0

    def exchange(self, _dev, _spi, data, rx_len):
        data = bytes(data)
        self.frames.append(("exchange", data))
        if data != b"\x80\x00" or rx_len != 2:
            raise AssertionError(f"Unexpected SPI read frame: {data!r}, rx_len={rx_len}")
        return bytes([0x00, self.regs.get(self.addr, 0)])

_bus = FakeBus()
_fake.ERR_SUCCESS = 0
_fake.GinkgoSPIError = FakeSpiError
_fake.build_config = lambda **kwargs: kwargs
_fake.close_device = lambda *args: 0
_fake.init_spi = lambda *args: 0
_fake.open_device = lambda *args: 0
_fake.scan_device = lambda *args: 1
_fake.write_bytes = lambda dev, spi, data: _bus.write(dev, spi, data)
_fake.write_read_bytes = lambda dev, spi, data, count: _bus.exchange(dev, spi, data, count)
sys.modules["driver.control_spi"] = _fake

from protocol.chip_spi import ChipSpi, ChipSpiConfig  # noqa: E402

class ReadProtocolTests(unittest.TestCase):
    def setUp(self):
        global _bus
        _bus = FakeBus()
        self.chip = ChipSpi()

    def test_read_without_previous_write(self):
        self.assertEqual(self.chip.read_reg(0x20), 0xAC)
        self.assertEqual(_bus.frames, [("write", b"\x00\x20"), ("exchange", b"\x80\x00")])
        self.assertEqual(_bus.regs[0x20], 0xAC)  # no register write

    def test_raw_rx_index(self):
        raw = self.chip.read_reg_raw(0x21)
        self.assertEqual(raw, b"\x00\x37")
        self.assertEqual(self.chip.decode_read_value(raw), 0x37)

    def test_address_set_again_on_each_read(self):
        self.assertEqual(self.chip.read_reg(0x21), 0x37)
        self.assertEqual(self.chip.read_reg(0x20), 0xAC)
        self.assertEqual(_bus.frames, [
            ("write", b"\x00\x21"), ("exchange", b"\x80\x00"),
            ("write", b"\x00\x20"), ("exchange", b"\x80\x00"),
        ])

    def test_optional_set_address_encoding(self):
        chip = ChipSpi(ChipSpiConfig(address_cmd=0x1F))
        self.assertEqual(chip.read_reg(0x20), 0xAC)
        self.assertEqual(_bus.frames[0], ("write", b"\x1f\x20"))

    def test_write_then_read(self):
        value, rx = self.chip.write_then_read(0x20, 0x5A)
        self.assertEqual((value, rx), (0x5A, b"\x00\x5a"))
        self.assertEqual(_bus.frames, [
            ("write", b"\x00\x20"), ("write", b"\x40\x5a"),
            ("write", b"\x00\x20"), ("exchange", b"\x80\x00"),
        ])

    def test_read_field_is_non_destructive(self):
        field = self.chip.regmap.fields[0]
        _bus.regs[field.address] = 0xD3
        info = self.chip.read_field(field.name)
        self.assertEqual(info["reg_value"], 0xD3)
        self.assertEqual(info["field_value_decimal"], (0xD3 & field.mask) >> field.lsb)
        self.assertEqual(len(_bus.frames), 2)
        self.assertNotIn(("write", b"\x40\xd3"), _bus.frames)

    def test_field_write_preserves_other_bits(self):
        field = next(f for f in self.chip.regmap.fields if f.width < 8)
        initial = 0xA5
        _bus.regs[field.address] = initial
        wanted = min(1, field.max_decimal)
        info = self.chip.write_field(field.name, wanted, verify=False)
        expected = (initial & ~field.mask) | ((wanted << field.lsb) & field.mask)
        self.assertEqual(info["before_reg_decimal"], initial)
        self.assertEqual(_bus.regs[field.address], expected)
        self.assertEqual(_bus.frames[:2], [
            ("write", bytes([0x00, field.address])), ("exchange", b"\x80\x00")
        ])
        self.assertEqual(_bus.frames[2:], [
            ("write", bytes([0x00, field.address])), ("write", bytes([0x40, expected]))
        ])

    def test_cli_read_does_not_write_register(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        from main import main as cli_main

        output = StringIO()
        with patch.object(sys, "argv", ["main.py", "read", "--reg", "0x20"]):
            with redirect_stdout(output):
                cli_main()
        self.assertIn("raw_rx=00 ac", output.getvalue())
        self.assertEqual(_bus.frames, [
            ("write", b"\x00\x20"), ("exchange", b"\x80\x00")
        ])
        self.assertEqual(_bus.regs[0x20], 0xAC)

    def test_cli_alternate_address_command(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        from main import main as cli_main

        with patch.object(sys, "argv", ["main.py", "read", "--reg", "0x20", "--address-cmd", "0x1F"]):
            with redirect_stdout(StringIO()):
                cli_main()
        self.assertEqual(_bus.frames, [
            ("write", b"\x1f\x20"), ("exchange", b"\x80\x00")
        ])

    def test_write_errors_propagate_without_reading(self):
        _bus.fail_next_write = True
        with self.assertRaises(FakeSpiError):
            self.chip.read_reg(0x20)
        self.assertEqual(len(_bus.frames), 1)

if __name__ == "__main__":
    unittest.main()
