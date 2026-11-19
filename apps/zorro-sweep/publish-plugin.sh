#!/usr/bin/env bash
# Publish Sweep or Keep (obsidian-plugin/) to its own public GitHub repository and make a
# release. The source stays here in zorro-desktop; the plugin repo gets a copy of that folder
# (git subtree), with its history. The release itself is made by the workflow in
# obsidian-plugin/.github/workflows/release.yml when the version tag arrives.
#
# Once:  gh repo create victor-zorro/sweep-or-keep --public
#        git remote add sweep-or-keep https://github.com/victor-zorro/sweep-or-keep.git
# Each release:
#   1. raise "version" in obsidian-plugin/manifest.json, add it to versions.json
#      ("<version>": "<minAppVersion>") and a "## <version>" section to CHANGELOG.md
#   2. commit, then: apps/zorro-sweep/publish-plugin.sh
set -euo pipefail
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
dir=apps/zorro-sweep/obsidian-plugin
v=$(python3 -c "import json;print(json.load(open('$dir/manifest.json'))['version'])")
python3 - "$dir" "$v" <<'PY'
import json, sys
d, v = sys.argv[1], sys.argv[2]
assert v in json.load(open(f'{d}/versions.json')), f'{v} missing in versions.json'
assert f'## {v}\n' in open(f'{d}/CHANGELOG.md').read(), f'## {v} missing in CHANGELOG.md'
PY
git diff --quiet HEAD -- "$dir" || { echo "commit $dir first"; exit 1; }
git remote get-url sweep-or-keep >/dev/null || { echo "no remote 'sweep-or-keep' (see the top of this file)"; exit 1; }
git subtree split --prefix "$dir" -b sweep-or-keep-release
git push sweep-or-keep sweep-or-keep-release:main
git push sweep-or-keep "sweep-or-keep-release:refs/tags/$v"
git branch -D sweep-or-keep-release
echo "Pushed $v; the release appears at https://github.com/victor-zorro/sweep-or-keep/releases"
