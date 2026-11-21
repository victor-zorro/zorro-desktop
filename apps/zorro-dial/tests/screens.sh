#!/usr/bin/env bash
# The real Dialer window in a private test screen: Xvfb, a made-up HOME, a private runtime
# dir, fake nmcli / pactl / bluetoothctl / dunstctl and a fake zorro-ai. Never the user's
# screen, files or running Dialer. Screenshots go to OUT.
#   tests/screens.sh OUT [DISPLAY, default :91]      (Xvfb from $XVFB or the PATH)
# ANCHOR=orb|centre|bottom-right…, AI_VIEW=history|last, NO_AI=1 (no AI service) change the scene.
set -euo pipefail
here=$(dirname "$(realpath "$0")")
out=$(realpath "${1:?where the screenshots go}")
disp=${2:-:91}
work=$(mktemp -d)
home=$work/home
mkdir -p "$out" "$home/share/applications" "$home/Notes/Work" "$home/Documents" "$home/Downloads" \
    "$home/.config/zorro-dial" "$home/.config/zorro-thinkpad" "$home/.config/obsidian" \
    "$home/.local/state/zorro-intel" "$work/state"
run=$(mktemp -d "${SHORT_TMP:-/tmp}/zd.XXXXXX")       # short: a unix socket's path may be 107 letters
chmod 700 "$run"
for shared in icons mime glib-2.0; do               # the look comes from the system, the apps do not
    ln -s "/usr/share/$shared" "$home/share/$shared"
done
for app in "Editor:accessories-text-editor:TextEditor" "Terminal:utilities-terminal:TerminalEmulator" \
    "Browser:web-browser:WebBrowser" "Player:multimedia-video-player:Video" \
    "Files:system-file-manager:FileManager" "Mail:mail-unread:Email" \
    "Displays:preferences-desktop-display:Settings"; do
    IFS=: read -r name icon cat <<<"$app"
    printf '[Desktop Entry]\nType=Application\nName=%s\nExec=true\nIcon=%s\nCategories=%s;\n' \
        "$name" "$icon" "$cat" >"$home/share/applications/${name,,}.desktop"
done
printf '# Plan\n\n## Monday\n\nWrite the report. #work\n' >"$home/Notes/Work/Plan.md"
printf 'A shopping list. #home\n' >"$home/Notes/Shopping.md"
printf 'hello\n' >"$home/Documents/readme.txt"
printf '{"vaults": {"a": {"path": "%s/Notes", "open": true}}}\n' "$home" >"$home/.config/obsidian/obsidian.json"
printf '{"anchor": "%s", "ai_view": "%s"}\n' "${ANCHOR:-bottom-right}" "${AI_VIEW:-history}" >"$home/.config/zorro-dial/config.json"
printf '{"music_outputs": ["AA:BB:CC:00:00:01", "AA:BB:CC:00:00:02"]}\n' >"$home/.config/zorro-thinkpad/config.json"
cat >"$home/.local/state/zorro-intel/chat.json" <<'JSON'
{"messages": [
 {"role": "user", "content": "How many parts does the hub have?", "at": "2026-11-21T10:00:00"},
 {"role": "assistant", "content": "Six: Apps, Music, Notes, AI, Messages and Files.", "at": "2026-11-21T10:00:02", "engine": "claude"}]}
JSON

"${XVFB:-Xvfb}" "$disp" -screen 0 1920x1080x24 -nolisten tcp >/dev/null 2>&1 &
xvfb=$!
ai=
if [ -z "${NO_AI:-}" ]; then
    python3 "$here/fake_ai.py" "$run/zorro-ai.sock" 0.4 &
    ai=$!
fi
cleanup() {
    kill "$xvfb" $ai 2>/dev/null || true
    for _ in 1 2 3; do                  # the session's own mounts under $run go a moment later
        rm -rf "$work" "$run" 2>/dev/null && break
        sleep 0.5
    done
}
trap cleanup EXIT
sleep 1
env -u DISPLAY -u WAYLAND_DISPLAY -u XDG_CONFIG_HOME -u XDG_STATE_HOME -u XDG_CACHE_HOME -u XDG_DATA_HOME \
    -u DBUS_SESSION_BUS_ADDRESS DISPLAY="$disp" HOME="$home" USER=tester XDG_RUNTIME_DIR="$run" \
    XDG_DATA_DIRS="$home/share" FAKE_STATE="$work/state" PATH="$here/fakebin:$PATH" GDK_BACKEND=x11 NO_AT_BRIDGE=1 \
    ZORRO_DIAL_SCREENS=1 dbus-run-session -- python3 "$here/screens.py" "$out" "$run/zorro-ai.sock"
