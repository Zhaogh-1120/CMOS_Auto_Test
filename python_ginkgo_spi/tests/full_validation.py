from __future__ import annotations

import argparse
import random
from statistics import mean

from protocol.chip_spi import ChipSpi


def fmt_case(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def run_case(chip: ChipSpi, reg: int, value: int):
    read_value, raw = chip.write_then_read(reg, value)
    ok = (read_value & 0xFF) == (value & 0xFF)
    print(
        f"VERIFY reg=0x{reg:02X}  write=0x{value:02X}  raw_rx={raw.hex(' ')}  "
        f"read=0x{read_value:02X}  result={fmt_case(ok)}"
    )
    return ok


def section(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def build_vectors(max_value: int) -> list[int]:
    base = [0x00, 0x01, 0x03, 0x05, 0x07]
    return [v for v in base if v <= max_value]


def main() -> None:
    parser = argparse.ArgumentParser(description="Comprehensive write/read validation cases for Ginkgo SPI")
    parser.add_argument("--reg", type=lambda x: int(x, 0), default=0x20, help="register address")
    parser.add_argument("--min-value", type=lambda x: int(x, 0), default=0x00, help="minimum test value")
    parser.add_argument("--max-value", type=lambda x: int(x, 0), default=0x07, help="maximum test value")
    parser.add_argument("--random-count", type=int, default=16, help="number of random cases")
    parser.add_argument("--repeat-count", type=int, default=20, help="number of repeat stability cases")
    parser.add_argument("--seed", type=int, default=20260323, help="random seed")
    args = parser.parse_args()

    if args.min_value < 0 or args.max_value < 0 or args.max_value > 0xFF:
        raise SystemExit("Value range must be within 0x00~0xFF.")
    if args.min_value > args.max_value:
        raise SystemExit("--min-value cannot be larger than --max-value.")

    rng = random.Random(args.seed)
    total = 0
    passed = 0
    records = []

    with ChipSpi() as chip:
        # 1. single spot check
        section("CASE 1: Single spot check")
        single_val = min(0x05, args.max_value)
        ok = run_case(chip, args.reg, single_val)
        total += 1
        passed += int(ok)
        records.append(ok)

        # 2. vector cases
        section("CASE 2: Vector values")
        vectors = build_vectors(args.max_value)
        if not vectors:
            vectors = [args.min_value, args.max_value]
        for v in vectors:
            if v < args.min_value or v > args.max_value:
                continue
            ok = run_case(chip, args.reg, v)
            total += 1
            passed += int(ok)
            records.append(ok)

        # 3. boundary cases
        section("CASE 3: Boundary values")
        boundary_values = []
        for v in [args.min_value, args.min_value + 1, max(args.min_value, args.max_value - 1), args.max_value]:
            if args.min_value <= v <= args.max_value and v not in boundary_values:
                boundary_values.append(v)
        for v in boundary_values:
            ok = run_case(chip, args.reg, v)
            total += 1
            passed += int(ok)
            records.append(ok)

        # 4. random regression
        section("CASE 4: Random regression")
        for _ in range(args.random_count):
            v = rng.randint(args.min_value, args.max_value)
            ok = run_case(chip, args.reg, v)
            total += 1
            passed += int(ok)
            records.append(ok)

        # 5. repeat stability
        section("CASE 5: Repeat stability")
        stable_value = args.max_value
        for _ in range(args.repeat_count):
            ok = run_case(chip, args.reg, stable_value)
            total += 1
            passed += int(ok)
            records.append(ok)

    section("SUMMARY")
    pass_rate = (passed / total * 100.0) if total else 0.0
    final = "PASS" if passed == total else "FAIL"
    print(f"reg=0x{args.reg:02X}")
    print(f"total_cases={total}")
    print(f"pass_cases={passed}")
    print(f"fail_cases={total - passed}")
    print(f"pass_rate={pass_rate:.2f}%")
    print(f"final_result={final}")


if __name__ == "__main__":
    main()
