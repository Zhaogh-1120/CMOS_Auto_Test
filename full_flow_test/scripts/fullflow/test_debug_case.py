from __future__ import annotations

import scripts.fullflow.case_discrete_sweep_capture as base


def main():
    base.CASE_NAME = 'test_debug_case'
    base.CASE_DESC = 'debug-enabled variant of discrete sweep capture'
    base.DEBUG = True
    base.CASE_POLICY.update({
        'DEBUG': True,
    })
    base.main()


if __name__ == '__main__':
    main()
