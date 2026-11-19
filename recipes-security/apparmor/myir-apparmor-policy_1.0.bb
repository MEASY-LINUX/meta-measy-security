# SPDX-License-Identifier: MIT

SUMMARY = "AppArmor policy additions for MYD-JMX95X"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

inherit allarch features_check

COMPATIBLE_MACHINE = "(myir-jmx95)"
REQUIRED_DISTRO_FEATURES = "apparmor"

SRC_URI = "file://sbin.syslogd"
S = "${UNPACKDIR}"
RDEPENDS:${PN} = "apparmor"

do_install() {
    install -Dm 0644 ${S}/sbin.syslogd ${D}${sysconfdir}/apparmor.d/local/sbin.syslogd
}

CONFFILES:${PN} = "${sysconfdir}/apparmor.d/local/sbin.syslogd"
