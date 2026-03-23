from dataclasses import dataclass

@dataclass
class VerifyResult:
    name: str
    write_value: int
    read_value: int
    result: str
