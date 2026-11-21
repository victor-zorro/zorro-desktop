#!/bin/sh
# Runs inside the Debian installer at the end of the install (preseed late_command).
# Puts the repo snapshot from the installation medium in the new user's home and
# installs the desktop's packages. Everything goes to /var/log/zorro-install.log.
log=/target/var/log/zorro-install.log
say() { echo "$(date '+%F %T') $*" >> "$log"; }
mkdir -p /target/var/log

cp /zorro-first-login.sh /target/etc/profile.d/zorro-first-login.sh
chmod 644 /target/etc/profile.d/zorro-first-login.sh

user=$(awk -F: '$3 == 1000 {print $1; exit}' /target/etc/passwd)
if [ -z "$user" ]; then say "no normal user found: nothing else to do"; exit 0; fi

snapshot=
for dir in /cdrom /media/cdrom /hd-media; do
  [ -f "$dir/zorro/zorro-desktop.tar.gz" ] && snapshot=$dir/zorro/zorro-desktop.tar.gz && break
done
if [ -z "$snapshot" ]; then say "snapshot not found on the installation medium"; exit 0; fi

home=/target/home/$user/zorro-desktop
mkdir -p "$home"
if tar -xzf "$snapshot" -C "$home"; then
  in-target chown -R "$user:" "/home/$user/zorro-desktop"
  say "snapshot unpacked to /home/$user/zorro-desktop"
else
  rm -rf "$home"
  say "could not unpack the snapshot"
  exit 0
fi

cp /in-target-packages.sh /target/tmp/zorro-packages.sh
in-target sh /tmp/zorro-packages.sh "/home/$user/zorro-desktop/packages" >> "$log" 2>&1
rm -f /target/tmp/zorro-packages.sh
say "done"
exit 0
