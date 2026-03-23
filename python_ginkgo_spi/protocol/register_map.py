from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FieldDef:
    name: str
    alias: str
    address: int
    address_hex: str
    bits: str
    msb: int
    lsb: int
    width: int
    mask: int
    default_decimal: int
    max_decimal: int


class RegisterMap:
    def __init__(self, json_path: str | None = None) -> None:
        if json_path is None:
            json_path = str(Path(__file__).resolve().parent.parent / "config" / "register_fields.json")
        with open(json_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        self.fields = [FieldDef(**item) for item in raw]
        self._by_name = {}
        self._by_alias = {}
        for field in self.fields:
            self._by_name[field.name.upper()] = field
            alias_key = field.alias.upper()
            if alias_key in self._by_alias and self._by_alias[alias_key].name != field.name:
                self._by_alias[alias_key] = None
            else:
                self._by_alias[alias_key] = field
        self.defaults_by_address = {}
        for field in self.fields:
            self.defaults_by_address.setdefault(field.address, 0)
            self.defaults_by_address[field.address] = (
                (self.defaults_by_address[field.address] & ~field.mask)
                | ((field.default_decimal << field.lsb) & field.mask)
            )

    def resolve(self, name: str) -> FieldDef:
        key = name.strip().upper()
        if key in self._by_name:
            return self._by_name[key]
        if key in self._by_alias and self._by_alias[key] is not None:
            return self._by_alias[key]
        matches = [f for f in self.fields if key in f.name.upper() or key in f.alias.upper()]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise KeyError(f"Field not found: {name}")
        raise KeyError("Field name is ambiguous. Use the full name with bit range.")

    def list_lines(self) -> list[str]:
        out = []
        for f in self.fields:
            out.append(
                f"{f.alias:<28} full={f.name:<32} addr={f.address_hex} bits={f.bits:<5} width={f.width} max={f.max_decimal} default={f.default_decimal}"
            )
        return out
