# Transfer

Set up another device like this one: open **Transfer** on both devices (Zorro Settings →
Connect → Transfer, or the Dialer: type "transfer").

1. On this device: **Send this setup to another device**. It shows a 6-digit code.
2. On the new device: **Get the setup from another device**. Your devices nearby show up by
   themselves (local network and NetBird peers; or type a name or address). One that is not
   sending yet has **Ask it to send**: a notification on that device says who asks, and its
   **Send** button opens Transfer there. Then type the code it shows.
3. Choose what comes along (with sizes). **Put everything in place by itself** is on: press
   **Start**, and the admin password is asked once, right away (login look and user accounts,
   with the passwords for other people's accounts typed here). From then on it runs on its
   own: receiving, then putting in place, Wi-Fi, settings and icons. Both devices show the
   progress; **Go on in the background** closes the window and it continues. Apps whose files
   would change (Firefox, Obsidian…) are waited for: a notification says which to close.
4. Off: when everything is there, press **Put in place** yourself. A file it replaces is
   kept as `NAME.before-transfer` either way.

Devices nearby: every device runs a small **beacon** (`zorro-beacon.service`, a user service
that install.sh enables). It tells only its name, the Transfer version and whether it is
sending; only to this device, NetBird peers and the home network (`apps/zorro-fx/zorro_net.py`:
home is known by its router; a café's Wi-Fi or the mobile network is not). A knock (Ask it to
send) only shows a notification, at most once a minute per device and 3 a minute in all;
after 3 that nobody acted on (within 10 minutes) it stays quiet until Transfer is opened
there, or an hour passed. It never starts sending and never tells the code. Two devices with
the same name are both listed, with their addresses. Settings → Connect → Transfer → Nearby
lists them too, with **Get its setup**.

Safety: a transfer can only start with Transfer open on both devices. The sender only lets
in the same devices as the beacon, 8 connections at most. The code works once. One device
pairs at a time, 15 seconds at most for the whole pairing; each wrong code makes the next try
from that device wait longer (2 s, 4 s… up to a minute) and after 10 that device is not let
in; every 3 wrong tries a new code is made; after 100 in all no code is offered until you
press **New code**. Pairing uses SPAKE2 (as magic-wormhole does), so listening in does not
reveal the code; the copy goes over TLS 1.3 with the paired key (this needs Python 3.13 or
newer on both devices; Transfer says so when it is older).

The new device does not take the sender's word for it:
- It accepts only files that belong to the groups you ticked, checked against its own list
  of what a group holds. Anything else in the sender's list is refused and counted. Who may
  log in to the new device is never copied: `.ssh/authorized_keys` does not travel.
- Inside those groups a sender you paired with can still bring files that run by themselves
  at login (autostart entries, user services, shell start-up files, `~/bin` programs). They
  are listed before **Put in place** (in the window and by `apply`), and in the final notes
  when it is put in place by itself: check them if you did not expect them.
- Each file must come with the size of the list; a sender that sends more, or changes the
  size, gets 3 tries for that file, then it is noted. Before the copy starts the new device
  checks it has room for everything (and says so if not). Small files come in batches of
  32 MB at most.
- Every file is checked with a SHA-256 from the sender. A copy that does not match is thrown
  away and fetched again (3 times at most); then it is noted as "not received" and the rest
  goes on. A file the sender cannot read (also when the disk breaks halfway) is noted the
  same way, and so is one that cannot be written here (a name taken by a folder…).
- Received files wait in a folder only you can read (0700, files 0600). In place they get
  the permissions they had (scripts stay runnable), never setuid, setgid or writable by
  everyone; everything of **Logins and keys** (and the logins of Claude and MQTTX) is yours
  only: files 0600 (0700 when runnable), folders 0700.
- A path that is a symbolic link, or lies behind one (`~/.config/openbox` into the repo), is
  left alone.
- New accounts are shown with their groups before you type a password for them. The groups
  your own account would join are shown before the admin password is asked; the powerful
  ones (sudo, input, kvm, libvirt) only when you tick them (`apply` asks y/N). The admin
  password is asked every time, never remembered.

Interrupted (network gone, laptop closed)? It retries for half an hour after the last byte
that arrived (the sender waits as long, also with its window closed), then stops; open
Transfer on both devices (Send again on the sender) and it goes on where it stopped, without
a new code. The sender forgets a transfer half an hour after its last sign of life, and at
once when it is done; after that you pair again. A cable is faster than Wi-Fi, but Wi-Fi and
NetBird work too.

What can go along (`transfer/items.py`):
- **Installers**: `~/Installers` (Unreal, DaVinci…).
- **Desktop and launcher**: the choices of the Dialer, Zorro Settings, info circle, wallpaper,
  music, languages, default apps (mimeapps.list), autostart, window places, file manager and
  GTK app preferences (dconf), and the login look (/etc/zorro-dm/look.json). Keybinds, kitty,
  rofi and Openbox come from the repo itself. After "Put in place" Transfer rebuilds what
  Settings makes from the choices (`zorro-settings --apply-windows`, `build-icons`) and saves
  the login look with the login-screen helper (asks your password).
- **Logins and keys**: Firefox and the web-app profiles (logins, saved passwords), SSH keys,
  the keyring (it opens with the old device's password), Wi-Fi networks (read with nmcli,
  added on the new device through nmcli's input, so the password is never on a command line;
  the password file is deleted when sending stops; networks with a company login are set up
  by hand), Drive accounts (rclone), GitHub login.
- **Apps' settings and data**: Obsidian, Claude, LocalSend, Blender, Godot, darktable,
  Scribus, MQTTX, mpv. Not Signal: a copied Signal stops working; link the new device to your
  phone instead.
- **Personal files**: one tick box per folder in your home (folders up to 5 GB are ticked);
  online drives (rclone mounts) are never walked. Not the repo, `UnrealEngine` or
  `Installers` (its own group).
- **User accounts**: you get your full name and groups on the new device (admin, printers,
  video, kvm…; whatever your user is called there); the other people's accounts are made
  there with a password you type on the new device: passwords never travel. Their files are
  not copied (only they can read them). Accounts that already exist are left alone. This
  needs the root part, `sudo apps/zorro-transfer/install-system.sh` (install.sh runs it):
  `zorro-transfer-helper` through polkit does the login look and the accounts in one go, so
  the admin password is asked once.

Caches are left out (they rebuild themselves). Small files travel in batches, so thousands of
notes don't each wait for the network. "Put in place" waits until the apps whose files it
would replace are closed (Firefox, Obsidian…), for a day at most; then it asks you to press
**Put in place**. The sender shows which of them are open on the sending device (close them
there for a clean copy). A home folder called `system` or `generated` cannot go along.

    zorro-transfer [--send|--get [--from HOST]]  the window (sending / getting side)
    zorro-transfer send            offer this device (the window runs this)
    zorro-transfer nearby [--json] [--wait S]    Zorro devices nearby, sending or not
    zorro-transfer knock HOST      ask that device to send (a notification there)
    zorro-transfer beacon          the beacon (zorro-beacon.service runs this)
    zorro-transfer get HOST        pair (asks the code) and list what it offers
    zorro-transfer continue [--groups a,b]   fetch / go on
    zorro-transfer apply           put in place
    zorro-transfer status          both sides' progress (JSON)

State: `~/.local/state/zorro-transfer/` (sender.json, receiver.json with the progress,
receiver-files.json with the file list, beacon.json, 0600; receiver.lock: one fetch or
pairing at a time; window.pid: a Send page is open; window.seen: when Transfer was last
opened). Received files wait in `~/.local/share/zorro-transfer/SESSION/` (half-arrived ones
in `SESSION.parts/`) until they are put in place; what an abandoned transfer left there is
removed at the next pairing, or after a week. Ports:
47820 (TCP, the sender), 47821 (UDP, the beacon: "who?" on the local network) and 47822 (TCP,
the beacon for NetBird peers: `{"op":"probe"}` and `{"op":"knock","name":…}`, 512 bytes at
most); `ZORRO_TRANSFER_PORT` moves all three (tests).

Code (`transfer/`): `sender.py` + `serve.py` the sending side, `receiver.py` + `fetch.py` the
getting side, `place.py` + `after.py` putting in place, `check.py` everything the other device
says is checked there, `items.py` + `generated.py` what goes along, `net.py` the wire (and who is trusted: `zorro_net`),
`state.py` state files, `beacon.py` the beacon, `find.py` finding devices nearby, `cli.py`, `pages/` the window (one page
per file).

Tests: `python3 -m unittest discover apps/zorro-transfer/tests`: two made-up devices in a
temporary folder talk over localhost; nmcli, pkexec and the root helper are stand-ins
(`tests/bin`, also netbird and notify-send), nothing touches your real home or network.
`test_window.py` opens the window's pages in a private Xvfb screen (skipped without Xvfb;
`XVFB=/path/to/Xvfb` points to one).
