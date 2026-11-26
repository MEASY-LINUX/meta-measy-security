# optee-os_%.imx.bbappend
# MYIR Security Layer - OP-TEE OS RPMB-FS support
#
# The default NXP configuration uses REE-FS. To build for RPMB-FS with a
# development test key, set these variables in local.conf.
#
#   MYIR_OPTEE_STORAGE = "rpmb"
#   MYIR_RPMB_MODE = "test"
#
# Enable the Trusted Keys early TA in local.conf.
#   MYIR_TRUSTED_KEYS = "1"

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

include ${@oe.utils.conditional('MYIR_OPTEE_STORAGE', 'rpmb', 'optee-os-rpmb-fs.inc', 'no-optee-rpmb.inc', d)}
include optee-os-trusted-keys.inc
