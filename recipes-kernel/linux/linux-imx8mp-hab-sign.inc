# i.MX8MP ARM64 Image HABv4 signing
#
# This path intentionally does not reuse linux-hab-sign.inc.  The i.MX6ULL
# implementation places its IVT after ALIGN(zImage file size), while booti on
# ARM64 derives the IVT position from the Image header's image_size field.

inherit myir-hab python3native

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += "file://imx8mp_sign_image.py"

do_imx8mp_hab_sign_kernel[depends] += "virtual/bootloader:do_deploy"
do_imx8mp_hab_sign_kernel[cleandirs] = "${WORKDIR}/imx8mp-hab-kernel"
do_imx8mp_hab_sign_kernel[nostamp] = "1"

do_imx8mp_hab_sign_kernel() {
    image="${B}/${KERNEL_OUTPUT_DIR}/${KERNEL_IMAGETYPE}"
    signed="${WORKDIR}/imx8mp-hab-kernel/${KERNEL_IMAGETYPE}.signed"

    if [ ! -f "${image}" ]; then
        bbfatal "i.MX8MP HAB: kernel image not found: ${image}"
    fi

    ${PYTHON} "${UNPACKDIR}/imx8mp_sign_image.py" \
        --image "${image}" \
        --output "${signed}" \
        --workdir "${WORKDIR}/imx8mp-hab-kernel" \
        --deploy-dir "${DEPLOY_DIR_IMAGE}" \
        --machine "${MACHINE}" \
        --cst "${MYIR_HAB_CST_BIN}" \
        --srk-table "${MYIR_HAB_CST_SRK}" \
        --csf-cert "${MYIR_HAB_CST_CSF_CERT}" \
        --img-cert "${MYIR_HAB_CST_IMG_CERT}" \
        --source-index "${@myir_hab_srk_source_idx(d)}" \
        --ivt-size "${MYIR_IMX8MP_HAB_IVT_SIZE}" \
        --csf-max-size "${MYIR_IMX8MP_HAB_CSF_MAX_SIZE}" \
        --align "${MYIR_IMX8MP_HAB_IMAGE_ALIGN}"
}

addtask imx8mp_hab_sign_kernel after do_compile before do_deploy

# External CST keys are deliberately not covered by the kernel source
# checksum.  Do not restore a previously deployed signature from sstate when
# this security flow is enabled.
do_deploy[nostamp] = "1"

do_deploy:append() {
    deploy_dir="${DEPLOYDIR}"
    if [ -n "${KERNEL_DEPLOYSUBDIR}" ]; then
        deploy_dir="${DEPLOYDIR}/${KERNEL_DEPLOYSUBDIR}"
    fi

    target="${deploy_dir}/${KERNEL_IMAGETYPE}-${KERNEL_IMAGE_NAME}${KERNEL_IMAGE_BIN_EXT}"
    unsigned="${deploy_dir}/${KERNEL_IMAGETYPE}-${KERNEL_IMAGE_NAME}-unsigned${KERNEL_IMAGE_BIN_EXT}"
    signed="${WORKDIR}/imx8mp-hab-kernel/${KERNEL_IMAGETYPE}.signed"

    if [ ! -f "${target}" ]; then
        bbfatal "i.MX8MP HAB: deployed unsigned Image not found: ${target}"
    fi
    if [ ! -f "${signed}" ]; then
        bbfatal "i.MX8MP HAB: signed Image not found: ${signed}"
    fi

    install -m 0644 "${target}" "${unsigned}"
    install -m 0644 "${signed}" "${target}"
    install -m 0644 \
        "${WORKDIR}/imx8mp-hab-kernel/Image.hab.json" \
        "${target}.hab.json"

    bbnote "i.MX8MP HAB: deployed signed Image as $(basename "${target}")"
    bbnote "i.MX8MP HAB: preserved unsigned Image as $(basename "${unsigned}")"
}
