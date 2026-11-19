# AppArmor on MYD-JMX95X B0

## Build the AHAB-signed test image

Set these values in `build-xwayland/conf/local.conf` to enable AHAB signing
and AppArmor with dm-verity and OTA disabled. The existing `BBMULTICONFIG`
assignment derives its value from `ENABLE_DM_VERITY`.

```bitbake
MYIR_SECURE_BOOT = "1"
ENABLE_DM_VERITY = "0"
OTA_SUPPORT = "0"
DISTRO_FEATURES:append = " apparmor"
IMAGE_INSTALL:append:pn-myir-image-emmc = " apparmor"
```

In the Yocto container, build `myir-image-emmc` using the existing
`build-xwayland` signing keys.

```sh
cd /home/myir
. ./setup-environment build-xwayland
bitbake myir-image-emmc

grep -E '^CONFIG_SECURITY_APPARMOR=y$|^CONFIG_LSM=.*apparmor' \
    tmp/work-shared/myd-jmx95x-b0/kernel-build-artifacts/.config
grep '^apparmor ' \
    tmp/deploy/images/myd-jmx95x-b0/myir-image-emmc-myd-jmx95x-b0.rootfs.manifest
```

Expect both kernel settings and an AppArmor package entry. Use the
`myir-image-emmc-myd-jmx95x-b0.rootfs.wic.zst` from the same deployment directory
with the board's usual eMMC image installation procedure.

## Verify on the board

After boot, run as root. Expect `apparmor` in the LSM list, `Y` for the module
parameter and `enabled` / `active` for the service. Use `aa-status` to check the
loaded profiles and enforcement modes.

```sh
cat /sys/kernel/security/lsm
cat /sys/module/apparmor/parameters/enabled
systemctl is-enabled apparmor.service
systemctl is-active apparmor.service
aa-status
```

Use a dedicated copy of `touch` to check automatic attachment when a program
starts. The profile allows one test path and leaves the other without a rule.

```sh
install -d /usr/local/libexec/myir-apparmor-test /run/myir-apparmor-test
install -m 0755 "$(command -v touch)" /usr/local/libexec/myir-apparmor-test/touch
cat > /etc/apparmor.d/myir-apparmor-test <<'EOF'
#include <tunables/global>

profile myir-apparmor-test /usr/local/libexec/myir-apparmor-test/touch {
  #include <abstractions/base>
  /run/myir-apparmor-test/allowed rw,
}
EOF
apparmor_parser -r /etc/apparmor.d/myir-apparmor-test
```

Run the checks below after loading the profile and again after reboot without
manually loading it. The normal `touch` establishes that the denied path is
writable. Expect the first two `touch` commands to succeed, the last `touch`
to print `Permission denied` and return a nonzero status, and the kernel log
to show `apparmor="DENIED"` for `myir-apparmor-test`.

```sh
install -d /run/myir-apparmor-test
grep '^myir-apparmor-test (enforce)$' /sys/kernel/security/apparmor/profiles
touch /run/myir-apparmor-test/denied && rm /run/myir-apparmor-test/denied
/usr/local/libexec/myir-apparmor-test/touch /run/myir-apparmor-test/allowed
/usr/local/libexec/myir-apparmor-test/touch /run/myir-apparmor-test/denied
echo "exit=$?"
journalctl -b --no-pager -o cat | grep -F 'profile="myir-apparmor-test"' | grep -F 'apparmor="DENIED"'
```

Unload and remove the test profile and its files when finished.

```sh
apparmor_parser -R /etc/apparmor.d/myir-apparmor-test
rm -f /etc/apparmor.d/myir-apparmor-test /usr/local/libexec/myir-apparmor-test/touch
rm -f /run/myir-apparmor-test/allowed /run/myir-apparmor-test/denied
rmdir /usr/local/libexec/myir-apparmor-test /run/myir-apparmor-test
```
