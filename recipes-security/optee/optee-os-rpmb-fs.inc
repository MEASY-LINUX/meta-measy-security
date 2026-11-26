# optee-os-rpmb-fs.inc
# Secure storage configuration for the Replay Protected Memory Block file system
#
# MYIR_OPTEE_STORAGE selects REE-FS or RPMB-FS, and MYIR_RPMB_MODE selects
# the RPMB operating mode.
#
# Set these variables in local.conf or machine.conf.
#
#   1. REE-FS (default)
#      MYIR_OPTEE_STORAGE = "ree"
#
#   2. RPMB-FS emulation for development (data is lost on reboot)
#      MYIR_OPTEE_STORAGE = "rpmb"
#      MYIR_RPMB_MODE = "emu"
#
#   3. RPMB-FS on physical eMMC with a test key for development
#      MYIR_OPTEE_STORAGE = "rpmb"
#      MYIR_RPMB_MODE = "test"
#
#   4. RPMB-FS on physical eMMC with one-time factory key provisioning
#      MYIR_OPTEE_STORAGE = "rpmb"
#      MYIR_RPMB_MODE = "provision"
#
#   5. RPMB-FS on physical eMMC with a pre-programmed production key
#      MYIR_OPTEE_STORAGE = "rpmb"
#      MYIR_RPMB_MODE = "prod"
#

# eMMC device ID (usually 0 on i.MX95)
MYIR_RPMB_FS_DEV_ID ?= "0"

# Use 1 for RPMB emulation and 0 for physical eMMC.
RPMB_EMU = "${@'1' if d.getVar('MYIR_RPMB_MODE') == 'emu' else '0'}"

# ===================================================================
# RPMB-FS build options for MYIR_OPTEE_STORAGE = "rpmb"
# ===================================================================

# The NXP OP-TEE OS Makefile consumes these options. Enable RPMB-FS
# and disable REE-FS to select RPMB for secure storage.
RPMB_FS_OEMAKE = " \
    RPMB_EMU=${RPMB_EMU} \
    CFG_REE_FS=n \
    CFG_RPMB_FS=y \
    CFG_RPMB_FS_DEV_ID=${MYIR_RPMB_FS_DEV_ID} \
    CFG_CORE_DYN_SHM=y \
    CFG_SCTLR_ALIGNMENT_CHECK=n \
    CFG_PREALLOC_RPC_CACHE=n \
    CFG_CORE_HEAP_SIZE=2097152 \
    CFG_TEE_RAM_VA_SIZE=4194304 \
"

EXTRA_OEMAKE:append = " ${RPMB_FS_OEMAKE}"

# ===================================================================
# RPMB operating modes
# ===================================================================

# The emu mode routes RPMB requests to tee-supplicant for software emulation.
EXTRA_OEMAKE:append = " \
    ${@oe.utils.conditional('MYIR_RPMB_MODE', 'emu', \
        'CFG_RPMB_EMU=y CFG_RPMB_TESTKEY=y CFG_RPMB_ANNOUNCE_PROBE_CAP=n', \
        '', d)} \
"

# The test mode uses physical eMMC with a test key.
EXTRA_OEMAKE:append = " \
    ${@oe.utils.conditional('MYIR_RPMB_MODE', 'test', \
        'CFG_RPMB_EMU=n CFG_RPMB_TESTKEY=y', \
        '', d)} \
"

# The provision mode programs the RPMB key once during manufacturing.
# CFG_RPMB_WRITE_KEY=y programs the authentication key into eMMC RPMB.
# CFG_RPMB_RESET_FAT=y resets the RPMB file allocation table.
EXTRA_OEMAKE:append = " \
    ${@oe.utils.conditional('MYIR_RPMB_MODE', 'provision', \
        'CFG_RPMB_EMU=n CFG_RPMB_WRITE_KEY=y CFG_RPMB_RESET_FAT=y', \
        '', d)} \
"

# The prod mode uses the key programmed in eMMC RPMB during factory provisioning.
# Leave CFG_RPMB_WRITE_KEY and CFG_RPMB_TESTKEY disabled in production.
EXTRA_OEMAKE:append = " \
    ${@oe.utils.conditional('MYIR_RPMB_MODE', 'prod', \
        'CFG_RPMB_EMU=n', \
        '', d)} \
"

# ===================================================================
# RPMB build configuration log
# ===================================================================
python () {
    mode = d.getVar('MYIR_RPMB_MODE')

    mode_desc = {
        'emu': 'Software emulation (reboot loses data)',
        'test': 'Real eMMC with test key',
        'provision': 'FACTORY: Write RPMB key to eMMC (ONE-TIME!)',
        'prod': 'Production mode (key pre-programmed)',
    }
    bb.plain('=============================================')
    bb.plain(' MYIR OP-TEE Storage: RPMB-FS')
    bb.plain(' RPMB Mode:          %s' % mode)
    bb.plain(' Description:        %s' % mode_desc[mode])
    bb.plain(' RPMB FS Device ID:  %s' % d.getVar('MYIR_RPMB_FS_DEV_ID'))
    bb.plain('=============================================')
}
