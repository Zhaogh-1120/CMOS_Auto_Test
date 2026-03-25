from protocol.chip_spi import ChipSpi


def main():
    with ChipSpi() as chip:
        info = chip.write_field_then_read("CFG_OSC2_GMP_NUM", 4)
        print(f"Step 1/3: field write-read -> name={info['field_name']} addr={info['address_hex']} bits={info['bits']}")
        print(f"Step 2/3: decimal write -> {info['write_field_decimal']}")
        print(f"Step 3/3: decimal read  -> {info['read_field_decimal']}  result={info['verify_result']}")


if __name__ == "__main__":
    main()
