from protocol.chip_spi import ChipSpi
from core.formatter import format_reg_verify
from utils.range_helper import inclusive_range


def main():
    with ChipSpi() as chip:
        reg_a = 0x20
        reg_b = 0x21
        for a in inclusive_range(0, 7, 1):
            for b in inclusive_range(0, 15, 1):
                read_a, raw_a = chip.write_then_read(reg_a, a)
                result_a = "PASS" if read_a == a else "FAIL"
                print(format_reg_verify(reg_a, a, raw_a, read_a, result_a))

                read_b, raw_b = chip.write_then_read(reg_b, b)
                result_b = "PASS" if read_b == b else "FAIL"
                print(format_reg_verify(reg_b, b, raw_b, read_b, result_b))


if __name__ == "__main__":
    main()
