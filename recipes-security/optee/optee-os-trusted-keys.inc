# optee-os-trusted-keys.inc
# MYIR Security Layer - Trusted Keys Early TA support
#
# 将 Linux trusted key 所需的 OP-TEE TA (f04a0fe7) 编译为 Early TA，
# 使 TA 在 OP-TEE 启动时注册到 TEE bus，kernel trusted-key-tee 驱动
# 才能通过 TEE bus match 到该 TA 并完成 probe。
#
# 使用方式 (local.conf):
#   MYIR_TRUSTED_KEYS = "1"
#
# 同时需要内核侧:
#   CONFIG_TRUSTED_KEYS=y
#   CONFIG_TRUSTED_KEYS_TEE=y
#   # CONFIG_TRUSTED_KEYS_DCP is not set
#   内核 cmdline: trusted.source=tee
#
# 硬件依赖:
#   - i.MX6ULL: 无 CAAM/ELE, trusted key 操作纯软件实现, 需 CFG_WITH_SOFTWARE_PRNG
#   - i.MX8/9:  自带 CAAM/ELE, 可使用 CFG_IMX_TRUSTED_ARM_CE 实现硬件加速
#

TRUSTED_KEYS_OEMAKE = " \
    CFG_IN_TREE_EARLY_TAS=trusted_keys/f04a0fe7-1f5d-4b9b-abf7-619b85b4ce8c \
    CFG_WITH_SOFTWARE_PRNG=y \
"

EXTRA_OEMAKE:append = " ${@oe.utils.conditional('MYIR_TRUSTED_KEYS', '1', '${TRUSTED_KEYS_OEMAKE}', '', d)}"
