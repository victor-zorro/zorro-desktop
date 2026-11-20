# Transfer

Set up another device like this one: open **Transfer** on both devices (Zorro Settings →
Desktop → Transfer, or the Dialer: type "transfer").

1. On this device: **Send this setup to another device**. It shows a 6-digit code.
2. On the new device: **Get the setup from another device**. It finds this one on the local
   network or among your NetBird peers (or type its NetBird name), then type the code.
3. Choose what comes along (with sizes). **Put everything in place by itself** is on: press
   **Start**, and the admin password is asked once, right away (login look and user accounts,
   with the passwords for other people's accounts typed here). From then on it runs on its
   own: receiving, then putting in place, Wi-Fi, settings and icons. Both devices show the
   progress; **Go on in the background** closes the window and it continues. Apps whose files
   would change (Firefox, Obsidian…) are waited for: a notification says which to close.
4. Off: when everything is there, press **Put in place** yourself. A file it replaces is
   kept as `NAME.before-transfer` either way.

Safety: a transfer can only start with Transfer open on both devices. The code works once;
after 3 wrong tries a new one is made. Pairing uses SPAKE2 (as magic-wormhole does), so
listening in does not reveal the code; the copy goes over TLS 1.3 with the paired key. One
device at a time.

Interrupted (network gone, laptop closed)? It retries for half an hour (the sender waits as
long, also with its window closed), then stops; open
Transfer on both devices (Send again on the sender) and it goes on where it stopped, without
a new code. A cable is faster than Wi-Fi, but Wi-Fi and NetBird work too.

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
  added on the new device; the password file is deleted when sending stops), Drive accounts
  (rclone), GitHub login.
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
would replace are closed (Firefox, Obsidian…); the sender shows which of them are open on the
sending device (close them there for a clean copy).

    zorro-transfer [--send|--get]  the window (on the sending / getting side)
    zorro-transfer send            offer this device (the window runs this)
    zorro-transfer find            senders on the network / NetBird
    zorro-transfer get HOST        pair (asks the code) and list what it offers
    zorro-transfer continue [--groups a,b]   fetch / go on
    zorro-transfer apply           put in place
    zorro-transfer status          both sides' progress (JSON)

State: `~/.local/state/zorro-transfer/` (sender.json, receiver.json, 0600). Received files wait
in `~/.local/share/zorro-transfer/SESSION/` until they are put in place. Port 47820 (TCP) and
47821 (UDP, finding devices on the local network).
