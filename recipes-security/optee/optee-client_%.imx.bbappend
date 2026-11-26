# optee-client_%.imx.bbappend
# MYIR Security Layer - OP-TEE Client RPMB support
#
# With RPMB-FS enabled, RPMB_EMU=1 selects in-memory emulation for development.
# RPMB_EMU=0 lets tee-supplicant access physical eMMC via /dev/mmcblkXrpmb.

python () {
    storage = d.getVar("MYIR_OPTEE_STORAGE")
    if storage == "rpmb":
        # Derive the client flag from MYIR_RPMB_MODE because the RPMB_EMU
        # variable in optee-os-rpmb-fs.inc is local to the OS recipe.
        mode = d.getVar("MYIR_RPMB_MODE")
        rpmb_emu = "1" if mode == "emu" else "0"

        d.appendVar("EXTRA_OECMAKE", " -DRPMB_EMU=" + rpmb_emu)

        bb.plain(" OPTEE Client: RPMB_EMU=%s" % rpmb_emu)
}
