# Usage

This project is organized into reusable layers:
- `driver/`: Ginkgo device access
- `protocol/`: chip SPI protocol and field/register operations
- `core/`: reusable verification/sweep/session hooks
- `scripts/`: daily experiment scripts
- `config/`: changeable project/chip/SPI configuration

Backward compatibility is preserved for the original paths in `config/` and `scripts/`.
