from __future__ import annotations

import scripts.fullflow.case_discrete_sweep_capture as base


def main():
    base.CASE_NAME = 'test_spi_retry_policy_case'
    base.CASE_DESC = 'discrete sweep with retry/link-check policy enabled for validation'
    base.DEBUG = False
    base.CONTINUE_ON_ERROR = True
    base.CASE_POLICY.update({
        'DEBUG': False,
        'CONTINUE_ON_ERROR': True,
        'SPI_RETRY_ON_FAIL': True,
        'SPI_RETRY_COUNT': 2,
        'SPI_RETRY_DELAY_S': 0.05,
        'STRICT_SPI_LINK_CHECK': True,
        'MAX_CONSECUTIVE_SPI_FAILS': 3,
        'CONTINUE_ON_DEVICE_LOSS': False,
        'RAISE_ON_SPI_VERIFY_FAIL': False,
    })
    base.main()


if __name__ == '__main__':
    main()
