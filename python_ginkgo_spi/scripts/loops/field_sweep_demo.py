from protocol.chip_spi import ChipSpi


def main():
    with ChipSpi() as chip:
        print("Sweep CFG_OSC2_GMP_NUM from decimal 0 to 7")
        for info in chip.sweep_field("CFG_OSC2_GMP_NUM", 0, 7, 1):
            print(
                f"name={info['field_name']} write_dec={info['write_field_decimal']} "
                f"read_dec={info['read_field_decimal']} result={info['verify_result']}"
            )


if __name__ == "__main__":
    main()
