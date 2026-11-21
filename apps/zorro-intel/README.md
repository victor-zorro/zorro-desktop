# zorro-intel

Intelligence: search and AI over your own notes and documents. Its own window, apart
from the Settings apps. The Dialer's AI part is its quick chat: both show the same
conversation.

- **Ask:** the chat. Your question is first searched in your folders (zorro-search); the
  best excerpts (0 to 8, default 4, at most 6000 characters together) go along to the
  engine. Under each answer: which engine and model answered, and the files that were
  sent; a click opens one. Stop keeps what had arrived, marked as stopped.
- **Search:** search by meaning, no AI. Enter or a click opens the file; "Ask about this"
  takes one file to Ask as the only thing sent.
- **Engines:** per place (Dialer, Intelligence, DEVS) Automatic, Claude, Mistral cloud or
  On this laptop; the switch "Nothing leaves this laptop"; whether each engine is ready.
- **Local models:** download models (`zorro-ai pull`), install the local engine
  (`zorro-ai install-local`), choose the model on the charger and on battery. Closing the
  window stops a download; it continues where it stopped next time.
- **Folders:** the only folders the AI may read. Empty at first: nothing is read until
  you add one. A file outside them is never shown or sent, also not through a link.
  zorro-search reads your Obsidian vaults and `~/Documents` today, so a folder outside
  those gives no results yet.
- **Mistral key:** store or remove the key (`~/.config/zorro-ai/mistral.key`, 0600). It
  is never shown.
- **About / privacy:** what leaves the laptop with each engine; delete all chats.

Files: settings `~/.config/zorro-intel/config.json` (`folders`, `excerpts`); the chat
`~/.local/state/zorro-intel/chat.json` (0600, shared with the Dialer; format in
`plan/SPEC.md`), older chats in `chats/` next to it. Answers come from the service
zorro-ai, the search from zorro-search; when one does not run, the page says so and
offers to start it.

```
apps/zorro-intel/install.sh
zorro-intel
zorro-intel --page ask|search|engines|models|folders|key|about
python3 -m unittest discover apps/zorro-intel/tests
python3 apps/zorro-intel/tests/check_pages.py     # every page, in a private test screen
```
