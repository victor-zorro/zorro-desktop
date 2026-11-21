# Build spec (Nov 2026 run)

What was decided on the plan page, as the contract for the build. Rules: `RULES.md`.

## The apps

| App | What | Where |
|---|---|---|
| Desktop | use: look and how you work | `apps/zorro-thinkpad` (`zorro-settings --app desktop`) |
| System | settings and hardware, monitors | same package (`--app system`) |
| Connect | Transfer, bootstrap (one-liner, USB, ISO), install apps, NetBird link | same package (`--app connect`) |
| DEVS | catalogue of features, bugs, wishes, backlog; tests per device; the plan | `apps/zorro-devs`, a web page served from the laptop |
| Intelligence | search + AI over chosen folders; stands apart, not in the switcher | `apps/zorro-intel` |
| zorro-ai | the one AI service every app asks | `apps/zorro-ai` |

The switcher in the top bar: Desktop, System, DEVS, Connect.

Dialer parts: Apps, Music, Notes, AI, Messages, Files. The System part goes: its tiles
live in the System app; the centre shows the time plus connection and battery.
Messages = notifications and SMS in one list, newest first. AI = Intelligence's chat
(a short history, or only the last answer: a setting). Music gets the fast output
picker: audio Bluetooth devices ticked in System → Bluetooth, greyed when not
connected, one tap connects and plays there.

## AI decisions

- Engines: `claude` (the `claude` CLI, the user's plan), `mistral` (Mistral's cloud,
  API key), `local` (llama.cpp on the laptop, several models to choose from, small
  ones included).
- The user chooses per place (dialer, intel, devs): one engine, or `auto`.
  `auto` = Claude; when it cannot be reached, Mistral cloud; offline, local.
- Local model choice may follow the power state: one model on the charger, a smaller
  one on battery.
- A switch "nothing leaves this laptop": only `local` is used.
- The AI reads only folders the user chose. Every answer says which engine answered
  and which files were sent.
- In DEVS the AI sorts new items, writes test steps, fills the catalogue from the repo
  and works on bugs. Changing code happens only after the user approves.

## zorro-ai: the protocol

A user service listening on `$XDG_RUNTIME_DIR/zorro-ai.sock` (unix stream socket,
mode 0600). One request per connection: one JSON line in, JSON lines out.

Request:

```json
{"op": "ask", "place": "dialer", "messages": [{"role": "user", "content": "…"}],
 "context": [{"path": "/home/u/notes/a.md", "text": "…"}], "engine": null}
```

- `place`: `dialer` | `intel` | `devs`. `engine`: null = the place's setting, or
  `claude` | `mistral` | `local` | `local:<model id>` to force one.
- `context`: excerpts the caller already chose (zorro-ai never reads files itself).

Replies, one JSON object per line:

```json
{"type": "start", "engine": "claude", "model": "…", "sent": ["/home/u/notes/a.md"]}
{"type": "text", "delta": "…"}
{"type": "note", "text": "Claude not reachable: answering with Mistral"}
{"type": "done", "engine": "claude", "seconds": 3.2}
{"type": "error", "code": "no_engine", "message": "…"}
```

After `done` or `error` the service closes the connection. Closing the connection
from the caller's side cancels the answer.

Other ops (one JSON object back, then close): `{"op": "status"}` → engines with
`ready` and `why`, models, settings; `{"op": "settings", "set": {…}}` → writes
`~/.config/zorro-ai/config.json`; `{"op": "models"}` → local models: id, name, size,
installed, speed note.

Config `~/.config/zorro-ai/config.json`:

```json
{"places": {"dialer": "auto", "intel": "auto", "devs": "claude"},
 "local_only": false, "local_model": "…", "local_model_battery": "…"}
```

The Mistral key lives in `~/.config/zorro-ai/mistral.key` (0600), never in the repo.

## DEVS: the data

Items are files: `~/.local/share/zorro-devs/items/<id>.json`, the folder is a git
repo of its own (history; later a push = the cloud). Never in the public repo.

```json
{"id": "dial-music-output", "kind": "feature", "title": "…", "text": "…",
 "app": "Dialer", "category": "Music", "status": "open",
 "steps": "how to test it", "check": "pages",
 "tests": {"zorro-thinkpad": {"state": "ok", "at": "2026-11-21T12:00:00", "version": "8c7fc4f"}}}
```

`kind`: feature | bug | wish | backlog | decision. `status`: open | doing | done.
`tests.<device>.state`: ok | fail | untested; a test made on an older `version` than
the last change of the app shows as stale. Devices: this one, and each device set up
by Transfer adds itself.

## How every part is built and tested

- Python 3 + GTK 3, like the rest. Shared look: `apps/zorro-fx/zorro_style.py`.
- Never open a window on the user's screen, never touch the user's running apps or
  files. GUI tests run in a private Xvfb with `env -u DISPLAY`, a private
  `XDG_RUNTIME_DIR`, `dbus-run-session`, and a synthetic `HOME`.
- Never kill by name; only PIDs you started. No sudo. No real keys or logins in tests.
- `tools/check-rules` passes before every commit.
