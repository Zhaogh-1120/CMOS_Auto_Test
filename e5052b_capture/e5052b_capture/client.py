from dataclasses import dataclass
from pathlib import Path


@dataclass
class E5052BConfig:
    resource: str = "TCPIP0::127.0.0.1::inst0::INSTR"
    timeout_ms: int = 10000


class E5052BClient:
    def __init__(self, config: E5052BConfig | None = None):
        self.config = config or E5052BConfig()
        self.inst = None

    def open(self):
        """TODO: 后续接入 pyvisa / SCPI。"""
        return self

    def close(self):
        self.inst = None

    def capture_screenshot(self, output_path: str | Path):
        """TODO: 保存 E5052B 屏幕截图。"""
        raise NotImplementedError("E5052B screenshot capture not implemented yet")

    def export_trace_csv(self, output_path: str | Path):
        """TODO: 导出曲线数据。"""
        raise NotImplementedError("E5052B trace export not implemented yet")
