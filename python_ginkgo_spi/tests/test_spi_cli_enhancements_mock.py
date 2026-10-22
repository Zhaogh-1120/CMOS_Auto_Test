"""Comprehensive hardware-free tests for Oct 2026 CLI enhancement.

Execute: python -m unittest discover -s tests -p 'test_*mock.py' -v
The deterministic fake Ginkgo bus is imported from the legacy read-protocol tests.
"""
from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

try:
    from . import test_spi_read_protocol_mock as driver_mock
except ImportError:  # unittest discover loads tests as top-level modules
    import test_spi_read_protocol_mock as driver_mock
from main import main as cli_main, parse_int
from protocol.chip_spi import ChipSpi


class CommandEnhancementTests(unittest.TestCase):
    def setUp(self):
        driver_mock._bus = driver_mock.FakeBus()

    @property
    def bus(self):
        return driver_mock._bus

    def run_cli(self, *args, error=False):
        out = io.StringIO()
        err = io.StringIO()
        with patch.object(sys, "argv", ["main.py", *args]), redirect_stdout(out), redirect_stderr(err):
            if error:
                with self.assertRaises(SystemExit) as caught:
                    cli_main()
                self.assertEqual(caught.exception.code, 2)
            else:
                cli_main()
        return out.getvalue(), err.getvalue()

    def assert_read_only(self):
        self.assertEqual([typ for typ, frame in self.bus.frames if typ == "write" and frame[0] == 0x40], [])

    def test_parse_decimal_hex_binary(self):
        for value in ("10", "0xA", "0b1010", "010", "0X0a"):
            self.assertEqual(parse_int(value), 10)

    def test_read_by_numeric_addr(self):
        out, _ = self.run_cli("read", "--reg", "0x20")
        self.assertIn("reg=0x20", out)
        self.assertIn("raw_rx=00 ac", out)
        self.assertIn("value_bin=2b10101100", out)
        self.assertEqual(self.bus.frames, [("write", b"\x00\x20"), ("exchange", b"\x80\x00")])

    def test_read_by_reg_name(self):
        out, _ = self.run_cli("read", "--name", "REG20")
        self.assertIn("name=REG20", out)
        self.assertIn("read=0xAC", out)
        self.assertIn("value_bin=2b10101100", out)
        self.assert_read_only()

    def test_read_by_field_name(self):
        out, _ = self.run_cli("read", "--name", "CFG_OSC2_IDAC_IBIAS")
        self.assertIn("FIELD_READ", out)
        self.assertIn("value_dec=21", out)
        self.assertIn("value_hex=0x15", out)
        self.assertIn("value_bin=2b10101", out)
        self.assert_read_only()

    def test_legacy_field_read_kept(self):
        out, _ = self.run_cli("field-read", "--name", "CFG_OSC2_GMP_NUM")
        self.assertIn("value_bin=2b100", out)

    def test_read_second_reg_without_data_write(self):
        out, _ = self.run_cli("read", "--name", "REG21")
        self.assertIn("read=0x37", out)
        self.assertIn("value_bin=2b00110111", out)
        self.assert_read_only()

    def test_write_reg_three_bases(self):
        for user_value in ("10", "0x0A", "0b00001010"):
            self.setUp()
            self.run_cli("write", "--reg", "0x20", "--value", user_value)
            self.assertEqual(self.bus.regs[0x20], 10)
            self.assertEqual(self.bus.frames[-1], ("write", b"\x40\x0a"))

    def test_write_field_three_bases(self):
        for user_value in ("10", "0x0A", "0b01010"):
            self.setUp()
            self.run_cli("field-write-read", "--name", "CFG_OSC2_IDAC_IBIAS", "--value", user_value)
            expected = (0xAC & 0x07) | (10 << 3)
            self.assertEqual(self.bus.regs[0x20], expected)
            self.assertEqual(self.bus.frames[3], ("write", bytes([0x40, expected])))

    def test_reg_dry_run_never_writes_reg_data(self):
        out, _ = self.run_cli("write", "--reg", "0x20", "--value", "0x54", "--dry-run")
        self.assertIn("before_reg=0xAC", out)
        self.assertIn("after_reg=0x54", out)
        self.assertIn("status=NO_REGISTER_WRITE", out)
        self.assertEqual(self.bus.regs[0x20], 0xAC)
        self.assertEqual(self.bus.frames, [("write", b"\x00\x20"), ("exchange", b"\x80\x00")])

    def test_write_read_dry_run_never_writes(self):
        self.run_cli("write-read", "--reg", "0x20", "--value", "0b10010000", "--dry-run")
        self.assertEqual(self.bus.regs[0x20], 0xAC)
        self.assert_read_only()

    def test_field_dry_run_preserves_other_bits(self):
        out, _ = self.run_cli("field-write", "--name", "CFG_OSC2_IDAC_IBIAS", "--value", "0b01010", "--dry-run")
        self.assertIn("after_reg=0x54", out)  # old lower 3 bits = 100
        self.assertEqual(self.bus.regs[0x20], 0xAC)
        self.assert_read_only()

    def test_field_write_read_dry_run_no_write(self):
        out, _ = self.run_cli("field-write-read", "--name", "CFG_OSC2_GMP_NUM", "--value", "5", "--dry-run")
        self.assertIn("after_reg=0xAD", out)
        self.assert_read_only()

    def test_reg_sweep_dry_run_once_read(self):
        out, _ = self.run_cli("sweep", "--reg", "0x20", "--start", "0b0", "--stop", "0x04", "--step", "2", "--dry-run")
        self.assertEqual(out.count("DRY_RUN"), 3)
        self.assertEqual(len(self.bus.frames), 2)
        self.assertEqual(self.bus.regs[0x20], 0xAC)

    def test_field_sweep_dry_run_unchanged_low_bits(self):
        out, _ = self.run_cli("field-sweep", "--name", "CFG_OSC2_IDAC_IBIAS", "--start", "0", "--stop", "0x04", "--step", "0b10", "--dry-run")
        self.assertEqual(out.count("DRY_RUN"), 3)
        self.assertIn("after_reg=0x04", out)
        self.assertIn("after_reg=0x14", out)
        self.assertIn("after_reg=0x24", out)
        self.assertEqual(len(self.bus.frames), 2)
        self.assertEqual(self.bus.regs[0x20], 0xAC)

    def test_reg_sweep_binary_live(self):
        out, _ = self.run_cli("sweep", "--reg", "0x20", "--start", "0b0", "--stop", "0b10", "--step", "1")
        self.assertEqual(out.count("VERIFY"), 3)
        self.assertEqual(self.bus.regs[0x20], 2)

    def test_field_sweep_hex_live(self):
        out, _ = self.run_cli("field-sweep", "--name", "CFG_OSC2_GMP_NUM", "--start", "0x01", "--stop", "0x03")
        self.assertEqual(out.count("FIELD_VERIFY"), 3)
        self.assertEqual(self.bus.regs[0x20] & 7, 3)

    def test_invalid_regs_and_fields_fail_without_io(self):
        invalid = [
            ("write", "--reg", "0x20", "--value", "0x100"),
            ("write", "--reg", "0x20", "--value", "-1"),
            ("write-read", "--reg", "0x100", "--value", "0"),
            ("read", "--reg", "-1"),
            ("read", "--name", "REG100"),
            ("read", "--reg", "0x20", "--name", "REG20"),
            ("field-write", "--name", "CFG_OSC2_GMP_NUM", "--value", "8"),
            ("field-write-read", "--name", "CFG_OSC2_IDAC_IBIAS", "--value", "0x20"),
            ("sweep", "--reg", "0x20", "--start", "0", "--stop", "0x100"),
            ("sweep", "--reg", "0x20", "--start", "0", "--stop", "4", "--step", "-1"),
            ("sweep", "--reg", "0x20", "--start", "0", "--stop", "4", "--step", "0"),
            ("field-sweep", "--name", "CFG_OSC2_GMP_NUM", "--start", "0", "--stop", "8"),
            ("write", "--reg", "0x20", "--value", "0xGG"),
        ]
        for cmd in invalid:
            with self.subTest(args=cmd):
                self.setUp()
                out, err = self.run_cli(*cmd, error=True)
                self.assertIn("error:", err)
                self.assertEqual(self.bus.frames, [])

    def test_invalid_field_direct_api_never_writes(self):
        chip = ChipSpi()
        with self.assertRaises(ValueError):
            chip.write_field("CFG_OSC2_GMP_NUM", 8)
        with self.assertRaises(ValueError):
            chip.write_reg(0x20, 256)
        with self.assertRaises(ValueError):
            chip.sweep_field("CFG_OSC2_GMP_NUM", 1, 9, 1)
        self.assertEqual(self.bus.frames, [])

    def test_shadow_and_dry_run_incompatible(self):
        _, err = self.run_cli("field-write", "--name", "CFG_OSC2_GMP_NUM", "--value", "2", "--dry-run", "--use-shadow", error=True)
        self.assertIn("cannot be combined", err)
        self.assertEqual(self.bus.frames, [])


    def test_reg_read_uses_three_bases_in_requested_order(self):
        for selector in (("--reg", "0x20"), ("--name", "REG20")):
            with self.subTest(selector=selector):
                self.setUp()
                out, _ = self.run_cli("read", *selector)
                self.assertIn("\033[93mname=REG20\033[0m", out)
                self.assertIn("\033[93mread=0xAC\033[0m", out)
                self.assertIn("\033[93mvalue_hex=0xAC\033[0m", out)
                self.assertIn("\033[93mvalue_bin=2b10101100\033[0m", out)
                self.assertIn("\033[93mvalue_dec=172\033[0m", out)
                self.assertIn("reg=0x20  raw_rx=00 ac", out)
                self.assertLess(out.index("value_hex="), out.index("value_bin="))
                self.assertLess(out.index("value_bin="), out.index("value_dec="))
                self.assert_read_only()

    def test_field_read_yellow_name_and_order(self):
        out, _ = self.run_cli("read", "--name", "CFG_OSC2_IDAC_IBIAS")
        self.assertIn("\033[93mname=CFG_OSC2_IDAC_IBIAS<7:3>\033[0m", out)
        self.assertIn("\033[93mreg=0xAC\033[0m", out)
        for key in ("value_hex=0x15", "value_bin=2b10101", "value_dec=21"):
            self.assertIn("\033[93m"+key+"\033[0m", out)
        self.assertLess(out.index("value_hex="), out.index("value_bin="))
        self.assertLess(out.index("value_bin="), out.index("value_dec="))
        self.assert_read_only()

    def test_errors_are_red_but_usage_not(self):
        _, err = self.run_cli("write", "--reg", "0x20", "--value", "-1", error=True)
        self.assertIn("main.py: \033[31merror: 8-bit register value must", err)
        self.assertIn("got -1\033[0m", err)
        self.assertTrue(err.startswith("usage: main.py "))
        self.assertEqual(self.bus.frames, [])

    def test_no_color_environment_works(self):
        with patch.dict("os.environ", {"NO_COLOR":"1"}):
            out, _ = self.run_cli("read", "--reg", "0x20")
            self.assertNotIn("\033[", out)
            self.assertIn("value_hex=0xAC  value_bin=2b10101100  value_dec=172", out)
            _, err = self.run_cli("write", "--reg", "0x20", "--value", "256", error=True)
            self.assertIn("error: 8-bit register value must", err)
            self.assertNotIn("\033[", err)



if __name__ == "__main__":
    unittest.main()
