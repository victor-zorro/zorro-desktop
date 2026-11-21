# DEVS (zorro-devs)

The catalogue of everything built and to be built for this desktop: features, bugs,
wishes, backlog and decisions, each with a test state per device. It is a web page served
from the laptop, so it also opens on other screens at home and over NetBird:
`http://<laptop>:8098`.

- **Menu**: Plan, Features, Bugs, Wishes, Backlog, Decisions, Devices. The item kinds get a
  submenu with the apps (Dialer, Desktop, System…) and their counts; past seven, More.
- **The list**: title, category, status and one mark per device: ✓ tested ok, ✕ failed,
  ○ not tested, a dim ✓ with "retest" when the app changed after the test.
- **Add an item**: type a title above the list and press Enter; kind and app come from where you are.
- **Filter line**: search, "Not tested here" and "Stale".
- **Side panel**: click a row for its text, test steps, status (open / doing / done) and
  ok / fail / untested per device. Every change is saved at once.
- **Devices page**: each device with how many items are ok, failed, untested and stale, and
  the automatic checks with a Run checks button.
- **Automatic checks** (`zorro-devs check`): `rules`, `compile`, `shell`, `json`, `units`.
  An item with `"check": "rules"` gets this device's test state from that check.
- **Plan page**: the build plan (`plan/`) shown inside DEVS; answers go to the same file
  as with `plan/serve.py` (`~/.local/state/zorro-plan/answers.json`).
- **Only private addresses**: the home network, NetBird and the laptop itself may open
  it; anything else gets a 403. There is no login yet.
- **First fill** (`zorro-devs fill`): makes items from CLAUDE.md, each app's README and
  `plan/SPEC.md`. Run it again any time: items that exist are never touched.

Items are files, one each: `~/.local/share/zorro-devs/items/<id>.json`. That folder is a
git repo of its own, with one commit per change, and is never part of the public repo.
Devices are in `~/.local/share/zorro-devs/devices.json`; this laptop adds itself.

```
apps/zorro-devs/install.sh                  link, fill, start the service
zorro-devs serve [--port 8098]
zorro-devs fill
zorro-devs check [rules|compile|shell|json|units]
zorro-devs list [--kind bug] [--app Dialer]
zorro-devs add bug "Clock is late" --app Dialer --category Launcher --text "…"
```

| File | What |
|---|---|
| `zorro-devs` | launcher; the code is the package `devs/` |
| `devs/store.py` | the items: checked fields, atomic writes, the git history |
| `devs/devices.py` | devices, the app → folder table, stale tests |
| `devs/checks.py` | the automatic checks |
| `devs/fill.py`, `fill_readme.py`, `fill_plan.py`, `fill_md.py` | the first fill |
| `devs/server.py`, `api.py`, `plan.py` | web server, JSON API, the plan page |
| `devs/web/` | the page: `index.html`, `style.css`, one small file per part in `js/` |
| `tests/` | `python3 -m unittest discover apps/zorro-devs/tests` |
