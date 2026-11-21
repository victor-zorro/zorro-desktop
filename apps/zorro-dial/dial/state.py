"""What changes while the Dialer runs, kept in one place: read and set it as state.NAME."""
import threading
import time

SCREEN_DPI = 96.0                       # set from the screen at each opening (Xft.dpi)
RESIDENT = False                        # True in 'zorro-dial --daemon'
OPEN = []                               # the dial window now shown by the daemon
STATUS = {'net': '', 'power': ''}        # the hub centre's small line: connection and battery

RING_W = (84, 84, 90)                   # the rings' widths, inner to outer
RING_ICON = (46, 52, 58)                # icon size per ring (search, lists): bigger further out
CLOUD_ICON, CLOUD_GROW, CLOUD_MAX = 46, 0.12, 1.5   # the apps' cloud: first row, growth per row, cap
CLOUD_GAP = 1.75                        # least centre to centre distance, in icon sizes
CLOUD_FLOAT = (0.07, 6.0)               # the icons drift: how far (icon sizes), one sway in seconds

FETCHING = {}                           # what is being read now (any opening) -> since when
FETCH_LOCK = threading.Lock()
FETCH_LIMIT = 20                        # seconds; a read that hangs longer no longer blocks a new one


def claim_fetch(key, now=None):
    """a ticket to read `key`, or None while another read of it runs (and is not too old)"""
    now = time.monotonic() if now is None else now
    with FETCH_LOCK:
        since = FETCHING.get(key)
        if since is not None and now - since < FETCH_LIMIT:
            return None
        FETCHING[key] = now
        return now


def owns_fetch(key, ticket):
    with FETCH_LOCK:
        return FETCHING.get(key) == ticket


def release_fetch(key, ticket):
    """done; a read that was overtaken by a newer one leaves the newer one's claim alone"""
    with FETCH_LOCK:
        if FETCHING.get(key) == ticket:
            del FETCHING[key]
