"""Helper library for the dual-supplicant tests.

config       settings: command line > environment > dsup.ini > defaults
board        run commands on the board over the system ssh
checks       "soft" checks: a test reports every broken expectation
journal      read and parse the board's journal
bus          capture and parse D-Bus traffic on the board
nm           NetworkManager and supplicant state helpers
monitors     background ping / device-state monitors that run on the board
"""
