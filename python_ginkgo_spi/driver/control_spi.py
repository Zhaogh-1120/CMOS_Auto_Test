from __future__ import annotations

from ctypes import *
from pathlib import Path
import platform


class VSI_INIT_CONFIG(Structure):
    _fields_ = [
        ("ControlMode", c_ubyte),   # 0=HW full duplex, 1=HW half duplex, 2=SW half duplex, 3=single bus
        ("TranBits", c_ubyte),      # 8 or 16
        ("MasterMode", c_ubyte),    # 0=slave, 1=master
        ("CPOL", c_ubyte),          # actual observed mapping on your setup: 0=idle high, 1=idle low
        ("CPHA", c_ubyte),          # 0=first edge, 1=second edge
        ("LSBFirst", c_ubyte),      # 0=MSB first, 1=LSB first
        ("SelPolarity", c_ubyte),   # 0=CS low active, 1=CS high active
        ("ClockSpeed", c_int),      # HW: fixed values, SW: 1000~1000000
    ]


VSI_USBSPI = 2
ERR_SUCCESS = 0


class GinkgoSPIError(RuntimeError):
    pass


def _load_library() -> CDLL:
    base = Path(__file__).resolve().parents[1] / "lib"
    system = platform.system()
    arch = platform.architecture()[0]
    if system == "Windows":
        dll = base / "windows" / ("64bit" if "64" in arch else "32bit") / "Ginkgo_Driver.dll"
        if not dll.exists():
            raise FileNotFoundError(f"DLL not found: {dll}")
        return windll.LoadLibrary(str(dll))
    raise OSError(f"This project currently bundles only Windows DLL. Current system: {system}")


_LIB = _load_library()


def scan_device(need_init: int = 1) -> int:
    return int(_LIB.VSI_ScanDevice(c_ubyte(need_init)))


def open_device(dev_index: int = 0, reserved: int = 0) -> int:
    return int(_LIB.VSI_OpenDevice(c_int(VSI_USBSPI), c_int(dev_index), c_int(reserved)))


def close_device(dev_index: int = 0) -> int:
    return int(_LIB.VSI_CloseDevice(c_int(VSI_USBSPI), c_int(dev_index)))


def init_spi(dev_index: int, config: VSI_INIT_CONFIG) -> int:
    return int(_LIB.VSI_InitSPI(c_int(VSI_USBSPI), c_int(dev_index), byref(config)))


def write_bytes(dev_index: int, spi_index: int, data: bytes) -> int:
    if not data:
        return 0
    buf = (c_ubyte * len(data))(*data)
    return int(_LIB.VSI_WriteBytes(c_int(VSI_USBSPI), c_int(dev_index), c_int(spi_index), byref(buf), c_ushort(len(data))))


def read_bytes(dev_index: int, spi_index: int, read_len: int) -> bytes:
    if read_len <= 0:
        return b""
    buf = (c_ubyte * read_len)()
    ret = int(_LIB.VSI_ReadBytes(c_int(VSI_USBSPI), c_int(dev_index), c_int(spi_index), byref(buf), c_ushort(read_len)))
    if ret != ERR_SUCCESS:
        raise GinkgoSPIError(f"VSI_ReadBytes failed, code={ret}")
    return bytes(buf)


def write_read_bytes(dev_index: int, spi_index: int, tx_data: bytes, read_len: int) -> bytes:
    if not tx_data:
        tx_data = b"\x00"
    tx = (c_ubyte * len(tx_data))(*tx_data)
    rx = (c_ubyte * read_len)()
    ret = int(
        _LIB.VSI_WriteReadBytes(
            c_int(VSI_USBSPI),
            c_int(dev_index),
            c_int(spi_index),
            byref(tx),
            c_short(len(tx_data)),
            byref(rx),
            c_short(read_len),
        )
    )
    if ret != ERR_SUCCESS:
        raise GinkgoSPIError(f"VSI_WriteReadBytes failed, code={ret}")
    return bytes(rx)


def build_config(
    *,
    control_mode: int = 2,
    tran_bits: int = 8,
    master_mode: int = 1,
    cpol: int = 1,
    cpha: int = 0,
    lsb_first: int = 0,
    cs_polarity: int = 0,
    clock_hz: int = 500_000,
) -> VSI_INIT_CONFIG:
    cfg = VSI_INIT_CONFIG()
    cfg.ControlMode = control_mode
    cfg.TranBits = tran_bits
    cfg.MasterMode = master_mode
    cfg.CPOL = cpol
    cfg.CPHA = cpha
    cfg.LSBFirst = lsb_first
    cfg.SelPolarity = cs_polarity
    cfg.ClockSpeed = clock_hz
    return cfg
