# DaVinci Resolve (Studio or free) on Debian 13

Not in apt and only downloadable after Blackmagic's form, so it isn't installed by
install.sh. Download the Linux zip into `~/Downloads`, then:

    sudo extras/davinci-resolve/install.sh

- GPU: needs OpenCL through ROCm (`rocm-opencl-icd`) and membership of `render` + `video`
  (checked on the T14 Gen 1 AMD: `gfx90c` shows up in `clinfo`, 6 compute units).
- Resolve's bundled GLib clashes with Debian's; the script moves those copies aside.
- The installer takes `DaVinci_Resolve_Studio_*_Linux.zip` from ~/Downloads when it is there,
  else the free zip. Studio: licence key at the first start.
- The free version can't decode H.264/H.265 or AAC on Linux: `zresolve-convert FILE...`
  (also handy with Studio for smooth editing: DNxHR edits lighter than long-GOP H.264)
  makes DNxHR copies (ffmpeg).
