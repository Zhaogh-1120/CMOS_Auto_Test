from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from driver.control_spi import (
    ERR_SUCCESS,
    GinkgoSPIError,
    build_config,
    close_device,
    init_spi,
    open_device,
    scan_device,
    write_bytes,
    write_read_bytes,
)
from protocol.register_map import RegisterMap, FieldDef


@dataclass
class ChipSpiConfig:
    dev_index: int = 0
    spi_index: int = 0
    clock_hz: int = 500_000
    control_mode: int = 0
    cpol: int = 0
    cpha: int = 0
    lsb_first: int = 0
    cs_polarity: int = 0
    address_cmd: int = 0x00
    write_cmd: int = 0x40
    read_cmd: int = 0x80
    read_response_index: int = 1


class ChipSpi:
    def __init__(self, config: ChipSpiConfig | None = None, register_map: RegisterMap | None = None) -> None:
        self.cfg = config or ChipSpiConfig()
        self._is_open = False
        self.regmap = register_map or RegisterMap()
        self.shadow_registers = dict(self.regmap.defaults_by_address)

    def open(self) -> None:
        count = scan_device(1)
        if count <= 0:
            raise GinkgoSPIError("No Ginkgo SPI device found.")
        ret = open_device(self.cfg.dev_index, 0)
        if ret != ERR_SUCCESS:
            raise GinkgoSPIError(f"Open device failed, code={ret}")
        spi_cfg = build_config(
            control_mode=self.cfg.control_mode,
            cpol=self.cfg.cpol,
            cpha=self.cfg.cpha,
            lsb_first=self.cfg.lsb_first,
            cs_polarity=self.cfg.cs_polarity,
            clock_hz=self.cfg.clock_hz,
        )
        ret = init_spi(self.cfg.dev_index, spi_cfg)
        if ret != ERR_SUCCESS:
            raise GinkgoSPIError(f"Init SPI failed, code={ret}")
        self._is_open = True

    def close(self) -> None:
        if self._is_open:
            close_device(self.cfg.dev_index)
            self._is_open = False

    def __enter__(self) -> "ChipSpi":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def transfer(self, data: bytes) -> None:
        ret = write_bytes(self.cfg.dev_index, self.cfg.spi_index, data)
        if ret != ERR_SUCCESS:
            raise GinkgoSPIError(f"SPI write failed, code={ret}, data={data.hex(' ')}")

    def transfer_read(self, data: bytes, rx_len: int | None = None) -> bytes:
        if rx_len is None:
            rx_len = len(data)
        rx = write_read_bytes(self.cfg.dev_index, self.cfg.spi_index, data, rx_len)
        return bytes(rx)

    @staticmethod
    def validate_address(reg_addr: int) -> int:
        reg_addr = int(reg_addr)
        if not 0 <= reg_addr <= 0xFF:
            raise ValueError(f"Register address must be 0..255 (0x00..0xFF), got {reg_addr}")
        return reg_addr

    @staticmethod
    def validate_reg_value(value: int) -> int:
        value = int(value)
        if not 0 <= value <= 0xFF:
            raise ValueError(f"8-bit register value must be 0..255 (0x00..0xFF), got {value}")
        return value

    @staticmethod
    def validate_sweep(start: int, stop: int, step: int, maximum: int) -> range:
        start, stop, step = int(start), int(stop), int(step)
        if step == 0:
            raise ValueError("Sweep step cannot be 0")
        if not 0 <= start <= maximum or not 0 <= stop <= maximum:
            raise ValueError(f"Sweep start/stop must be within 0..{maximum}, got {start}, {stop}")
        if (stop - start) * step < 0:
            raise ValueError(f"Sweep step {step} points away from stop={stop} (start={start})")
        return range(start, stop + (1 if step > 0 else -1), step)

    def write_reg(self, reg_addr: int, value: int) -> None:
        reg_addr = self.validate_address(reg_addr)
        value = self.validate_reg_value(value)
        self.transfer(bytes([self.cfg.address_cmd, reg_addr & 0xFF]))
        self.transfer(bytes([self.cfg.write_cmd, value & 0xFF]))
        self.shadow_registers[reg_addr & 0xFF] = value & 0xFF

    def read_reg_raw(self, reg_addr: int) -> bytes:
        """Read a register without modifying its stored value.

        This chip uses a persistent internal address pointer.  The Read Data
        command (0x80 by default) does NOT contain the target address:

          CS low: [Set Address, reg_addr]  -> CS high
          CS low: [Read Data, 0x00]      -> CS high; RX[1] is the value

        Keep these as two distinct driver calls/CS frames, as already done
        for the known-working write_reg() address + data sequence.
        """
        reg_addr = self.validate_address(reg_addr)
        self.transfer(bytes([self.cfg.address_cmd, reg_addr]))
        return self.transfer_read(bytes([self.cfg.read_cmd, 0x00]), 2)

    def decode_read_value(self, rx: bytes) -> int:
        idx = self.cfg.read_response_index
        if idx >= len(rx):
            raise GinkgoSPIError(f"Read response too short: {rx.hex(' ')}")
        return int(rx[idx])

    def read_reg(self, reg_addr: int) -> int:
        value = self.decode_read_value(self.read_reg_raw(reg_addr))
        self.shadow_registers[reg_addr & 0xFF] = value
        return value

    def write_then_read(self, reg_addr: int, value: int) -> tuple[int, bytes]:
        self.write_reg(reg_addr, value)
        rx = self.read_reg_raw(reg_addr)
        decoded = self.decode_read_value(rx)
        self.shadow_registers[reg_addr & 0xFF] = decoded
        return decoded, rx

    def sweep_reg(self, reg_addr: int, start: int, stop: int, step: int = 1, return_raw: bool = False):
        self.validate_address(reg_addr)
        values = self.validate_sweep(start, stop, step, 0xFF)
        result = []
        for value in values:
            decoded, raw = self.write_then_read(reg_addr, value)
            result.append((value, decoded, raw) if return_raw else (value, decoded))
        return result

    def batch_write(self, items: Iterable[tuple[int, int]]) -> None:
        for reg_addr, value in items:
            self.write_reg(reg_addr, value)

    def get_field(self, name: str) -> FieldDef:
        return self.regmap.resolve(name)

    def extract_field_value(self, reg_value: int, field: FieldDef) -> int:
        return (reg_value & field.mask) >> field.lsb

    def compose_field_value(self, reg_value: int, field: FieldDef, field_value: int) -> int:
        self.validate_field_value(field, field_value)
        return (reg_value & ~field.mask) | ((int(field_value) << field.lsb) & field.mask)

    @staticmethod
    def validate_field_value(field: FieldDef, value: int) -> int:
        value = int(value)
        if not 0 <= value <= field.max_decimal:
            raise ValueError(f"Field {field.alias} ({field.bits}) only allows 0..{field.max_decimal}, got {value}")
        return value

    def preview_reg(self, reg_addr: int, value: int) -> dict:
        """Read actual silicon register, calculate a prospective write; never write register data."""
        reg_addr = self.validate_address(reg_addr)
        value = self.validate_reg_value(value)
        before = self.read_reg(reg_addr)
        return {"address": reg_addr, "before_reg": before, "after_reg": value}

    def preview_field(self, name: str, value: int) -> dict:
        """Read-Only RMW preview; actual silicon register remains unchanged."""
        field = self.get_field(name)
        value = self.validate_field_value(field, value)
        before = self.read_reg(field.address)
        after = self.compose_field_value(before, field, value)
        return {"field_name": field.name, "address": field.address, "bits": field.bits,
                "before_reg": before, "after_reg": after, "field_value": value,
                "before_field": self.extract_field_value(before, field)}

    def read_field(self, name: str) -> dict:
        field = self.get_field(name)
        reg_value = self.read_reg(field.address)
        field_value = self.extract_field_value(reg_value, field)
        return {
            "field_name": field.name,
            "alias": field.alias,
            "address": field.address,
            "address_hex": field.address_hex,
            "bits": field.bits,
            "reg_value": reg_value,
            "reg_value_hex": f"0x{reg_value:02X}",
            "field_value_decimal": field_value,
            "field_value_hex": f"0x{field_value:X}",
            "field_value_bin": f"2b{field_value:0{field.width}b}",
            "max_decimal": field.max_decimal,
        }

    def write_field(self, name: str, decimal_value: int, verify: bool = False, use_shadow: bool = False) -> dict:
        field = self.get_field(name)
        decimal_value = self.validate_field_value(field, decimal_value)
        if use_shadow:
            base_reg = self.shadow_registers.get(field.address, self.regmap.defaults_by_address.get(field.address, 0))
        else:
            base_reg = self.read_reg(field.address)
        new_reg = self.compose_field_value(base_reg, field, decimal_value)
        self.write_reg(field.address, new_reg)
        result = {
            "field_name": field.name,
            "alias": field.alias,
            "address": field.address,
            "address_hex": field.address_hex,
            "bits": field.bits,
            "before_reg_decimal": base_reg,
            "before_reg_hex": f"0x{base_reg:02X}",
            "after_reg_decimal": new_reg,
            "after_reg_hex": f"0x{new_reg:02X}",
            "write_field_decimal": decimal_value,
            "write_field_hex": f"0x{decimal_value:X}",
            "max_decimal": field.max_decimal,
        }
        if verify:
            readback = self.read_field(field.name)
            result["read_field_decimal"] = readback["field_value_decimal"]
            result["read_field_hex"] = readback["field_value_hex"]
            result["verify_result"] = "PASS" if readback["field_value_decimal"] == decimal_value else "FAIL"
        return result

    def write_field_then_read(self, name: str, decimal_value: int, use_shadow: bool = False) -> dict:
        return self.write_field(name, decimal_value, verify=True, use_shadow=use_shadow)

    def sweep_field(self, name: str, start: int, stop: int, step: int = 1, use_shadow: bool = False) -> list[dict]:
        field = self.get_field(name)
        values = self.validate_sweep(start, stop, step, field.max_decimal)
        result = []
        for value in values:
            result.append(self.write_field_then_read(field.name, value, use_shadow=use_shadow))
        return result
