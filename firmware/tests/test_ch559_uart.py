# SPDX-License-Identifier: Apache-2.0
"""CH559 pin and UART logic with mock SFR; not an electrical test."""
import test_uart as uart


class Ch559UartTests(uart.UartTests):
    extra_flags = ('-DMG_CH559',)
