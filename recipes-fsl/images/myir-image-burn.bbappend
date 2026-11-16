# A dm-verity product payload and its writable factory SD must not share one
# recipe configuration.  Normal and AHAB-only burn images are unaffected.
python myir_validate_dmverity_factory_image() {
    if d.getVar('ENABLE_DM_VERITY') == '1':
        bb.fatal('dm-verity myir-image-burn must be built as mc:factory:myir-image-burn')
}
do_rootfs[prefuncs] += "myir_validate_dmverity_factory_image"
