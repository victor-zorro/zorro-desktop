# zorro-ai

The one AI service every Zorro app asks. An app sends a question (and the excerpts it
chose) over a socket and gets the answer back as it is written, with the name of the
engine that answered. zorro-ai never reads files itself.

- **Engines:**
  - `claude`: the `claude` program on PATH (Claude Code, your plan), text only, no tools,
    run in an empty folder.
  - `mistral`: Mistral's cloud. Put your API key in `~/.config/zorro-ai/mistral.key` (0600).
  - `local`: llama.cpp's `llama-server` on the laptop with a GGUF model. Started when a
    question comes, stopped after 5 idle minutes so the RAM is free again.
- **Claude model per place:** `claude_models` in the settings: the Dialer asks `haiku`, Intelligence
  and DEVS `sonnet` (the suggestions, used until you choose). Also `opus`, or `default` = what the
  `claude` program picks itself. Passed as `--model` for that one answer; `start` says which.
- **auto:** Claude; when it cannot be reached, Mistral; offline, local. A `note` line says
  when another engine answers. "Reachable" is one TCP connect of at most 2 s, remembered
  for 30 s.
- **Nothing leaves this laptop** (`local_only`): only `local` answers.
- **Local models:** `zai/models.json`, from 0.5 GB to an 8B model, Mistral's open models
  included. `local_model` is used on the charger, `local_model_battery` on battery.
- **Service:** `zorro-ai.service` (user) on `$XDG_RUNTIME_DIR/zorro-ai.sock` (0600). One
  request per connection, JSON lines; the protocol is in `plan/SPEC.md`. Hanging up
  cancels the answer and stops the engine. `done` also carries the `model` that answered;
  when an engine fails before its first word in `auto`, a `note` and a second `start` follow.
- **Files:** settings `~/.config/zorro-ai/config.json`; models, llama-server, its log and
  the measured speeds in `~/.local/share/zorro-ai/`.

```
apps/zorro-ai/install.sh
zorro-ai ask why is the sky blue
zorro-ai ask --place intel --engine local:qwen2.5-0.5b summarise this in one line: ...
zorro-ai ask --place dialer --model opus a harder question   # force a Claude model once
zorro-ai status
zorro-ai models
zorro-ai install-local
zorro-ai pull ministral-3-3b
python3 -m unittest discover apps/zorro-ai/tests
```
