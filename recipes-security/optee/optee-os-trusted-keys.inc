# optee-os-trusted-keys.inc
# MYIR Security Layer - Trusted Keys Early TA support
#
# Build the OP-TEE Trusted Keys TA (f04a0fe7) as an early TA. It registers
# on the TEE bus at startup so the Linux trusted-key-tee driver can match
# it and complete its probe.
#
# Enable it in local.conf.
#   MYIR_TRUSTED_KEYS = "1"
#
# Required kernel settings
#   CONFIG_TRUSTED_KEYS=y
#   CONFIG_TRUSTED_KEYS_TEE=y
#   # CONFIG_TRUSTED_KEYS_DCP is not set
#   Kernel command line: trusted.source=tee
#
# Hardware support
#   - i.MX6ULL lacks CAAM and ELE. Trusted Keys run in software and require
#     CFG_WITH_SOFTWARE_PRNG.
#   - i.MX8 and i.MX9 have CAAM or ELE and can use CFG_IMX_TRUSTED_ARM_CE
#     for hardware acceleration.
#

TRUSTED_KEYS_OEMAKE = " \
    CFG_IN_TREE_EARLY_TAS=trusted_keys/f04a0fe7-1f5d-4b9b-abf7-619b85b4ce8c \
    CFG_WITH_SOFTWARE_PRNG=y \
"

EXTRA_OEMAKE:append = " ${@oe.utils.conditional('MYIR_TRUSTED_KEYS', '1', '${TRUSTED_KEYS_OEMAKE}', '', d)}"
