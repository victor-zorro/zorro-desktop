# zorro-dm

Our own display manager for one seat: animated login screen, lock screen and session start.
Replaces LightDM + nody-greeter. Python, GTK3 + WebKitGTK.

| File | What |
|---|---|
| `zorro-dm` | root daemon: Xorg :0 on vt7, greeter, PAM login, starts the X session, lock screen on vt8 |
| `zorro-greeter` | login/lock screen: a WebKit window showing `theme/`; `--preview` for theme work |
| `zorro-lock` | asks zorro-dm to lock (used by `xss-lock -l` in Openbox autostart), pauses dunst meanwhile |
| `theme/` | HTML/CSS/WebGL screen; talks to a `window.lightdm`-style API, so it also runs in web greeters |
| `pam/` | PAM services `zorro-dm`, `zorro-dm-greeter`, `zorro-lock` |
| `zorro-dm.service` | systemd unit, `Alias=display-manager.service` |

Install: `sudo ./install.sh` (files) or `sudo ./install.sh --enable` (also make it the display manager).
Needs: `xorg python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1 python3-pam xauth xss-lock`.

Locking: zorro-dm starts a second X server on vt8 with the greeter in lock mode and blocks VT
switching until the session user's password is right, so the session is never on screen while
locked; a crashing lock screen is restarted. Sleep waits until the lock screen is drawn.

Back to LightDM: `sudo systemctl disable zorro-dm && sudo systemctl enable --force lightdm`.
Test changes in the VM first (`zvm`).
