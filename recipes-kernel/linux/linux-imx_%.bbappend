# linux-imx_%.bbappend
# Kernel security configuration for MYIR i.MX95
#
# Uses modular linux-sec-features.inc to conditionally include:
#   - dm-verity.cfg       (when myir-dmverity is in OVERRIDES)
#   - dm-crypt.cfg + CAAM (when myir-encrypted is in OVERRIDES)
#
# FILESEXTRAPATHS is set in linux-sec-features.inc, not here.
#

require linux-sec-features.inc

# Parse the i.MX8MP signing task only for the selected board and explicit
# opt-in.  Other machines do not gain a task, dependency, or source file.
include ${@'linux-imx8mp-hab-sign.inc' if d.getVar('MACHINE') == 'myd-js8mpq' and d.getVar('MYIR_IMX8MP_HAB_ENABLE') == '1' else ''}
