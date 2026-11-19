# zorro-search

Search your notes and documents by meaning, on the laptop. "rice dish from Indonesia"
finds "nasi goreng"; Dutch and English (and ~100 other languages) mixed.

- **Model:** multilingual-e5-small (MIT, ~120 MB, quantized ONNX), run with Debian's
  onnxruntime and sentencepiece. Downloaded by `install.sh` into
  `~/.local/share/zorro-search/`, checked by sha256. Nothing leaves the laptop.
- **What:** every Obsidian vault, and `~/Documents` (md, txt, pdf via pdftotext).
- **Service:** `zorro-search.service` (user) keeps the model loaded, answers on
  `$XDG_RUNTIME_DIR/zorro-search.sock` in a few milliseconds, and reads new and changed
  files every 10 minutes (niced, idle IO). Index: `~/.cache/zorro-search/`.
- **Dialer:** typing in Notes shows the exact-word hits first, then the notes found by
  meaning (marked ≈).

```
apps/zorro-search/install.sh
zorro-search what was the proxmox backup setup
zorro-search status
```
