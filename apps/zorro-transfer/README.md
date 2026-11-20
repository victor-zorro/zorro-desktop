# Transfer

Set up another device like this one: open **Transfer** on both devices (Dialer: type
"transfer", or behind the settings gear).

1. On this device: **Send this setup to another device**. It shows a 6-digit code.
2. On the new device: **Get the setup from another device**. It finds this one on the local
   network or among your NetBird peers (or type its NetBird name), then type the code.
3. Choose what comes along (with sizes), press **Start**. Both devices show the progress;
   **Go on in the background** closes the window and the copy continues.
4. When everything is there: **Put in place**. A file it replaces is kept as
   `NAME.before-transfer`.

Safety: a transfer can only start with Transfer open on both devices. The code works once;
after 3 wrong tries a new one is made. Pairing uses SPAKE2 (as magic-wormhole does), so
listening in does not reveal the code; the copy goes over TLS 1.3 with the paired key. One
device at a time.

Interrupted (network gone, laptop closed)? It retries for half an hour, then stops; open
Transfer on both devices (Send again on the sender) and it goes on where it stopped, without
a new code. A cable is faster than Wi-Fi, but Wi-Fi and NetBird work too.

What can go along (`transfer/items.py`): the installers in `~/Installers` and the desktop
settings. Logins, app data, personal files and user accounts come next.

    zorro-transfer                 the window
    zorro-transfer send            offer this device (the window runs this)
    zorro-transfer find            senders on the network / NetBird
    zorro-transfer get HOST        pair (asks the code) and list what it offers
    zorro-transfer continue [--groups a,b]   fetch / go on
    zorro-transfer apply           put in place
    zorro-transfer status          both sides' progress (JSON)

State: `~/.local/state/zorro-transfer/` (sender.json, receiver.json, 0600). Received files wait
in `~/.local/share/zorro-transfer/SESSION/` until they are put in place. Port 47820 (TCP) and
47821 (UDP, finding devices on the local network).
