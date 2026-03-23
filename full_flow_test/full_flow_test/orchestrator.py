from dataclasses import dataclass


@dataclass
class FlowStepResult:
    ok: bool
    message: str


class FullFlowOrchestrator:
    def __init__(self, chip_spi=None, e5052b=None):
        self.chip_spi = chip_spi
        self.e5052b = e5052b

    def run_once(self) -> FlowStepResult:
        """TODO: 先配置 SPI，再采集 E5052B。"""
        return FlowStepResult(ok=False, message="Full flow not implemented yet")
