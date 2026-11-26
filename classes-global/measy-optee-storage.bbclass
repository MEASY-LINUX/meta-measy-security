python measy_validate_optee_storage() {
    storage = d.getVar("MYIR_OPTEE_STORAGE")
    if storage not in ("ree", "rpmb"):
        bb.fatal("MYIR_OPTEE_STORAGE must be 'ree' or 'rpmb', got %r" % storage)

    mode = d.getVar("MYIR_RPMB_MODE")
    if mode not in ("emu", "test", "provision", "prod"):
        bb.fatal("MYIR_RPMB_MODE must be 'emu', 'test', 'provision' or 'prod', got %r" % mode)
}
addhandler measy_validate_optee_storage
measy_validate_optee_storage[eventmask] = "bb.event.ConfigParsed"
