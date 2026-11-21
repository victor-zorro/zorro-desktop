"""Get llama.cpp's llama-server (plain CPU build, Linux x86-64) into ~/.local/share/zorro-ai/llama/."""
import json
import re
import shutil
import tarfile

from . import paths
from .download import DownloadError, fetch, open_url, progress_line

API = 'https://api.github.com/repos/ggml-org/llama.cpp/releases'
ASSET = re.compile(r'^llama-b\d+-bin-ubuntu-x64\.tar\.gz$')
POINTER = 'nightly-tag.txt'       # the "latest" release may only point at the newest build


def _json(url):
    with open_url(url) as resp:
        return json.load(resp)


def _cpu_asset(release):
    for asset in release.get('assets', []):
        if ASSET.match(asset['name']):
            return asset
    return None


def latest_asset(api=API):
    """(tag, asset) of the newest release that carries the plain Ubuntu x64 build"""
    release = _json(f'{api}/latest')
    asset = _cpu_asset(release)
    if asset:
        return release['tag_name'], asset
    for a in release.get('assets', []):
        if a['name'] == POINTER:
            with open_url(a['browser_download_url']) as resp:
                tag = resp.read(64).decode().strip()
            if re.fullmatch(r'[\w.-]+', tag):
                release = _json(f'{api}/tags/{tag}')
                asset = _cpu_asset(release)
                if asset:
                    return release['tag_name'], asset
    for release in _json(f'{api}?per_page=10'):
        asset = _cpu_asset(release)
        if asset:
            return release['tag_name'], asset
    raise DownloadError('no llama.cpp release with a plain Ubuntu x64 build was found')


def server_binary():
    """the llama-server we downloaded, else one on PATH, else None"""
    home = paths.llama_dir()
    found = sorted(home.rglob('llama-server')) if home.is_dir() else []
    for p in found:
        if p.is_file():
            return str(p)
    return shutil.which('llama-server')


def install(say=print):
    tag, asset = latest_asset()
    home = paths.llama_dir()
    if (home / 'version').is_file() and (home / 'version').read_text().strip() == tag and server_binary():
        say(f'llama-server {tag} is already installed')
        return tag
    archive = paths.data_dir() / asset['name']
    digest = (asset.get('digest') or '').removeprefix('sha256:') or None
    say(f'llama.cpp {tag}: {asset["size"] / 1e6:.0f} MB')
    fetch(asset['browser_download_url'], archive, digest, progress_line(asset['name']))
    fresh = home.with_name('llama.new')
    shutil.rmtree(fresh, ignore_errors=True)
    fresh.mkdir(parents=True)
    with tarfile.open(archive) as tar:
        tar.extractall(fresh, filter='data')
    (fresh / 'version').write_text(tag + '\n')
    shutil.rmtree(home, ignore_errors=True)
    fresh.rename(home)
    archive.unlink()
    say(f'llama-server {tag} installed in {home}')
    return tag
