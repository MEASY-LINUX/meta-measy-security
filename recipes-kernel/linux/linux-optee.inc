# linux-optee.inc
# Kernel OP-TEE configuration include for MYIR i.MX95
#
# When MYIR_OPTEE_STORAGE=rpmb, loads optee.cfg + tee.cfg + rpmb.cfg
#
# rpmb.cfg enables kernel RPMB subsystem so OP-TEE RPMB-FS uses
# in-kernel routing (rpmb_routing_model=kernel) instead of relying
# on tee-supplicant (NXP 4.8 does not support new RPMB probe protocol).

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

python __anonymous() {
    storage = d.getVar("MYIR_OPTEE_STORAGE")
    if storage == "rpmb":
        # kernel-yocto consumes .cfg entries from SRC_URI as fragments.
        d.appendVar("SRC_URI", " file://optee.cfg file://tee.cfg file://rpmb.cfg")

        bb.debug(1, "OP-TEE RPMB-FS: optee.cfg + tee.cfg + rpmb.cfg added")
}
