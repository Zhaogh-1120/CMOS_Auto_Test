from protocol.chip_spi import ChipSpi

with ChipSpi() as chip:
    print("Ginkgo SPI open success.")
