# i.MX8MP SPL + second-loader/FIT HABv4 signing

inherit myir-hab python3native

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += " \
    file://imx8mp_habv4/imx8mp_sign_boot.py \
    file://imx8mp_habv4/imx8mp_gen_fuse_cmds.py \
"

# i.MX8MP OCOTP fuse layout.  Keep these variables local to the 8MP include;
# they must not alter the i.MX6ULL HAB or i.MX95 AHAB fuse paths.  The values
# are the i.MX8MP HABv4 layout: SRK_HASH occupies bank 6, words 0..3, followed
# by bank 7, words 0..3.  The HAB close bit is SEC_CONFIG at bank 1, word 3,
# bit 25.  A machine can override them if another silicon revision requires a
# different map.
MYIR_IMX8MP_HAB_SRK_FUSE_BANK_START ?= "6"
MYIR_IMX8MP_HAB_SRK_FUSE_WORD_START ?= "0"
MYIR_IMX8MP_HAB_SRK_FUSE_WORD_COUNT ?= "8"
MYIR_IMX8MP_HAB_SRK_FUSE_WORDS_PER_BANK ?= "4"
MYIR_IMX8MP_HAB_CLOSE_FUSE_BANK ?= "1"
MYIR_IMX8MP_HAB_CLOSE_FUSE_WORD ?= "3"
MYIR_IMX8MP_HAB_CLOSE_FUSE_VALUE ?= "0x02000000"

python () {
    conflicts = []
    for name in ('MYIR_AHAB_ENABLE', 'MYIR_HAB_ENABLE',
                 'MYIR_FIT_ENABLE', 'MYIR_KERNEL_HAB_SIGN',
                 'UBOOT_SIGN_ENABLE'):
        if d.getVar(name) == '1':
            conflicts.append(name)
    if conflicts:
        bb.fatal('MYIR_IMX8MP_HAB_ENABLE=1 cannot be combined with: %s' %
                 ', '.join(conflicts))
}

do_imx8mp_hab_sign_boot[cleandirs] = "${WORKDIR}/imx8mp-hab-boot"
do_imx8mp_hab_sign_boot[nostamp] = "1"

do_imx8mp_hab_sign_boot() {
    if [ "${SOC_FAMILY}" != "mx8m" ] || [ "${IMX_BOOT_SOC_TARGET}" != "iMX8MP" ]; then
        bbfatal "i.MX8MP HAB task selected for unexpected SoC: SOC_FAMILY=${SOC_FAMILY}, IMX_BOOT_SOC_TARGET=${IMX_BOOT_SOC_TARGET}"
    fi

    for type in ${UBOOT_CONFIG}; do
        if [ "${@d.getVarFlags('UBOOT_DTB_NAME')}" = "None" ]; then
            UBOOT_DTB_NAME_FLAGS="${type}:${UBOOT_DTB_NAME}"
        else
            UBOOT_DTB_NAME_FLAGS="${@' '.join(flag + ':' + dtb for flag, dtb in (d.getVarFlags('UBOOT_DTB_NAME')).items()) if d.getVarFlags('UBOOT_DTB_NAME') is not None else ''}"
        fi

        type_found=0
        for key_value in ${UBOOT_DTB_NAME_FLAGS}; do
            type_key="${key_value%%:*}"
            dtb_name="${key_value#*:}"
            if [ "${type_key}" != "${type}" ]; then
                continue
            fi
            type_found=1

            UBOOT_CONFIG_EXTRA="${type_key}"
            if [ -e "${DEPLOY_DIR_IMAGE}/${BOOT_TOOLS}/${dtb_name}-${type}" ]; then
                UBOOT_DTB_NAME_EXTRA="${dtb_name}-${type}"
            else
                UBOOT_DTB_NAME_EXTRA="${dtb_name}"
            fi
            UBOOT_NAME_EXTRA="u-boot-${MACHINE}.bin-${UBOOT_CONFIG_EXTRA}"
            boot_base="imx-boot${BOOT_VARIANT}-${MACHINE}-${UBOOT_CONFIG_EXTRA}.bin"

            for target in ${IMXBOOT_TARGETS}; do
                target_work="${WORKDIR}/imx8mp-hab-boot/${type}-${target}"
                install -d "${target_work}"
                mkimage_log="${target_work}/mkimage-${target}.log"
                fit_log="${target_work}/print-fit-hab-${target}.log"
                boot_image="${S}/${boot_base}-${target}"
                unsigned_image="${boot_image}.unsigned"

                if [ ! -f "${boot_image}" ]; then
                    bbfatal "i.MX8MP HAB: unsigned canonical boot image missing: ${boot_image}"
                fi

                # Reload the exact U-Boot configuration before rebuilding.
                # This mirrors the base recipe and prevents a later config in
                # UBOOT_CONFIG from leaving stale staging inputs behind.
                compile_${SOC_FAMILY}

                bbnote "i.MX8MP HAB: regenerating ${type}/${target} to capture its exact HAB layout"
                # Invoke the top-level imx-mkimage Makefile exactly as the base
                # recipe does.  It dispatches into ${BOOT_STAGING}/soc.mak;
                # calling make from BOOT_STAGING can trigger an implicit rule.
                cd "${S}"
                if ! make SOC="${IMX_BOOT_SOC_TARGET}" ${REV_OPTION} ${MKIMAGE_EXTRA_ARGS} \
                        dtbs="${UBOOT_DTB_NAME}" "${target}" > "${mkimage_log}" 2>&1; then
                    cat "${mkimage_log}"
                    bbfatal "i.MX8MP HAB: imx-mkimage failed for ${type}/${target}"
                fi
                if [ ! -f "${BOOT_STAGING}/flash.bin" ]; then
                    bbfatal "i.MX8MP HAB: flash.bin missing after rebuilding ${target}"
                fi
                if cmp -s "${BOOT_STAGING}/flash.bin" "${boot_image}"; then
                    # Fresh do_compile output: refresh the rollback copy.
                    install -m 0644 "${boot_image}" "${unsigned_image}"
                elif [ -f "${unsigned_image}" ] && \
                        cmp -s "${BOOT_STAGING}/flash.bin" "${unsigned_image}"; then
                    # A nostamp signing task may run again without do_compile;
                    # in that case the canonical file is already signed.
                    bbnote "i.MX8MP HAB: reusing verified unsigned backup for ${type}/${target}"
                else
                    bbfatal "i.MX8MP HAB: regenerated flash.bin differs from ${boot_image}; refusing to sign mismatched layout"
                fi

                case "${target}" in
                    *flexspi*) fit_hab_target="print_fit_hab_flexspi" ;;
                    *ddr4*)    fit_hab_target="print_fit_hab_ddr4" ;;
                    *)         fit_hab_target="print_fit_hab" ;;
                esac

                bbnote "i.MX8MP HAB: collecting FIT blocks with ${fit_hab_target}"
                if ! make SOC="${IMX_BOOT_SOC_TARGET}" ${REV_OPTION} ${MKIMAGE_EXTRA_ARGS} \
                        dtbs="${UBOOT_DTB_NAME}" "${fit_hab_target}" > "${fit_log}" 2>&1; then
                    cat "${fit_log}"
                    bbfatal "i.MX8MP HAB: ${fit_hab_target} failed for ${type}/${target}"
                fi

                ${PYTHON} "${UNPACKDIR}/imx8mp_habv4/imx8mp_sign_boot.py" \
                    --flash "${BOOT_STAGING}/flash.bin" \
                    --output "${target_work}/flash.signed.bin" \
                    --workdir "${target_work}" \
                    --mkimage-log "${mkimage_log}" \
                    --fit-log "${fit_log}" \
                    --cst "${MYIR_HAB_CST_BIN}" \
                    --srk-table "${MYIR_HAB_CST_SRK}" \
                    --csf-cert "${MYIR_HAB_CST_CSF_CERT}" \
                    --img-cert "${MYIR_HAB_CST_IMG_CERT}" \
                    --source-index "${@myir_hab_srk_source_idx(d)}" \
                    --ivt-size "${MYIR_IMX8MP_HAB_IVT_SIZE}" \
                    --csf-max-size "${MYIR_IMX8MP_HAB_CSF_MAX_SIZE}"

                if [ ! -f "${target_work}/flash.signed.bin" ]; then
                    bbfatal "i.MX8MP HAB: signed flash missing for ${type}/${target}"
                fi

                # Replace the recipe's canonical artifact only after every
                # parser, IVT, bounds, CST, and final-size check succeeds.
                install -m 0644 "${target_work}/flash.signed.bin" "${boot_image}"
                bbnote "i.MX8MP HAB: signed ${boot_base}-${target}"
            done
        done

        if [ "${type_found}" -ne 1 ]; then
            bbfatal "i.MX8MP HAB: no U-Boot DTB mapping found for config ${type}"
        fi
    done
}

addtask imx8mp_hab_sign_boot after do_compile before do_install do_deploy

# External CST keys are outside BitBake's normal source checksums.  Secure
# deploys must consume the signature generated in this invocation.
do_deploy[nostamp] = "1"

do_deploy:append() {
    if [ "${MACHINE}" = "myd-js8mpq" ] && [ "${MYIR_IMX8MP_HAB_ENABLE}" = "1" ]; then
        # Generate during every secure deploy instead of relying on a separate
        # task edge.  This ensures the file comes from the SRK selected for the
        # current build and cannot be a stale artifact from an earlier run.
        if [ ! -f "${MYIR_HAB_CST_SRK_FUSE}" ]; then
            bbfatal "i.MX8MP HAB SRK fuse file not found: ${MYIR_HAB_CST_SRK_FUSE}"
        fi

        install -d "${WORKDIR}/imx8mp-hab-fuse"
        ${PYTHON} "${UNPACKDIR}/imx8mp_habv4/imx8mp_gen_fuse_cmds.py" \
            --srk-fuse "${MYIR_HAB_CST_SRK_FUSE}" \
            --output "${WORKDIR}/imx8mp-hab-fuse/fuse-cmds.txt" \
            --srk-bank-start "${MYIR_IMX8MP_HAB_SRK_FUSE_BANK_START}" \
            --srk-word-start "${MYIR_IMX8MP_HAB_SRK_FUSE_WORD_START}" \
            --srk-word-count "${MYIR_IMX8MP_HAB_SRK_FUSE_WORD_COUNT}" \
            --srk-words-per-bank "${MYIR_IMX8MP_HAB_SRK_FUSE_WORDS_PER_BANK}" \
            --close-bank "${MYIR_IMX8MP_HAB_CLOSE_FUSE_BANK}" \
            --close-word "${MYIR_IMX8MP_HAB_CLOSE_FUSE_WORD}" \
            --close-value "${MYIR_IMX8MP_HAB_CLOSE_FUSE_VALUE}"

        if [ ! -s "${WORKDIR}/imx8mp-hab-fuse/fuse-cmds.txt" ]; then
            bbfatal "i.MX8MP HAB fuse command file was not generated"
        fi
        install -m 0644 "${WORKDIR}/imx8mp-hab-fuse/fuse-cmds.txt" \
            "${DEPLOYDIR}/fuse-cmds.txt"
        bbnote "i.MX8MP HAB: deployed fuse-cmds.txt"
    fi

    for type in ${UBOOT_CONFIG}; do
        boot_base="imx-boot${BOOT_VARIANT}-${MACHINE}-${type}.bin"
        for target in ${IMXBOOT_TARGETS}; do
            source_unsigned="${S}/${boot_base}-${target}.unsigned"
            target_work="${WORKDIR}/imx8mp-hab-boot/${type}-${target}"
            if [ ! -f "${source_unsigned}" ]; then
                bbfatal "i.MX8MP HAB: unsigned boot backup missing: ${source_unsigned}"
            fi
            install -m 0644 "${source_unsigned}" \
                "${DEPLOYDIR}/${boot_base}-${target}.unsigned"
            install -m 0644 "${target_work}/imx-boot.hab.json" \
                "${DEPLOYDIR}/${boot_base}-${target}.hab.json"
            install -m 0644 "${target_work}/csf_spl.bin" \
                "${DEPLOYDIR}/${boot_base}-${target}.csf-spl.bin"
            install -m 0644 "${target_work}/csf_fit.bin" \
                "${DEPLOYDIR}/${boot_base}-${target}.csf-fit.bin"
        done
    done
}
