/* Sweep notes, inside Obsidian (laptop and phone). Plain JavaScript, no build step.
 *
 * Rounds: keep (swipe left) or delete (swipe right) the oldest notes of a notebook; after 10
 * kept ones, drag each onto a notebook (a folder in this vault). Progress lives in this plugin's
 * data.json, which Obsidian Sync carries along, and which the laptop app (apps/zorro-sweep)
 * reads and writes too: keys are paths relative to the vault ('note.md', 'Folder/note.md').
 * Deleted notes go to the vault's .trash folder, like the laptop app. */
'use strict';
const { Plugin, ItemView, MarkdownRenderer, Modal, Component, TFile, TFolder, Notice } = require('obsidian');

const VIEW = 'zorro-sweep';
const ROUND = 10;
const SHAPES = ['hex', 'circle', 'blob', 'oct', 'squircle', 'diamond'];

function hash(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return (h >>> 0) / 4294967295;
}

function ago(ts) {
  const days = (Date.now() - ts) / 86400000;
  if (days < 1) return 'today';
  if (days < 60) return `${Math.floor(days)} days ago`;
  if (days < 730) return `${Math.floor(days / 30.4)} months ago`;
  return `${Math.floor(days / 365.25)} years ago`;
}

function shapeSvg(kind, w, h) {
  const p = (pts) => `<path d="M${pts.map(([x, y]) => `${(x * w).toFixed(1)},${(y * h).toFixed(1)}`).join(' L')}Z"/>`;
  switch (kind) {
    case 'circle': return `<ellipse cx="${w / 2}" cy="${h / 2}" rx="${w / 2}" ry="${h / 2}"/>`;
    case 'squircle': return `<rect width="${w}" height="${h}" rx="${Math.min(w, h) * 0.3}"/>`;
    case 'pill': return `<rect width="${w}" height="${h}" rx="${h / 2}"/>`;
    case 'dash': return `<rect class="zs-dash" width="${w}" height="${h}" rx="12"/>`;
    case 'hex': return p([[.25, 0], [.75, 0], [1, .5], [.75, 1], [.25, 1], [0, .5]]);
    case 'oct': return p([[.3, 0], [.7, 0], [1, .3], [1, .7], [.7, 1], [.3, 1], [0, .7], [0, .3]]);
    case 'diamond': return p([[.5, 0], [1, .5], [.5, 1], [0, .5]]);
    default:                                   // blob
      return `<path d="M${w * .5},0 C${w * .85},0 ${w},${h * .25} ${w * .95},${h * .5} C${w * .9},${h * .8} ${w * .7},${h} ${w * .45},${h * .97} C${w * .15},${h * .95} 0,${h * .75} ${w * .05},${h * .45} C${w * .1},${h * .15} ${w * .25},0 ${w * .5},0Z"/>`;
  }
}

module.exports = class SweepPlugin extends Plugin {
  async onload() {
    await this.loadState();
    this.registerView(VIEW, (leaf) => new SweepView(leaf, this));
    this.addRibbonIcon('brush', 'Sweep notes', () => this.open());
    this.addCommand({ id: 'open', name: 'Open', callback: () => this.open() });
    // obsidian://zorro-sweep?vault=NAME opens that vault with Sweep on top (the vault picker)
    this.registerObsidianProtocolHandler('zorro-sweep', () => this.app.workspace.onLayoutReady(() => this.open()));
  }

  async loadState() {
    const d = Object.assign({ kept: [], stays: [], batch: [], source: '', vaults: [] }, (await this.loadData()) || {});
    d.stats = Object.assign({ deleted: 0, moved: 0 }, d.stats || {});
    this.data = d;
    this.kept = new Set(d.kept);
    this.stays = new Set(d.stays);
  }

  async save() {
    // the laptop app writes this file too: start from what is on disk, keep its other keys
    const disk = (await this.loadData()) || {};
    const d = this.data;
    await this.saveData(Object.assign(disk, {
      kept: [...this.kept], stays: [...this.stays], batch: d.batch, stats: d.stats, source: d.source,
    }));
  }

  async onExternalSettingsChange() {          // Sync or the laptop app changed the progress
    await this.loadState();
    for (const leaf of this.app.workspace.getLeavesOfType(VIEW)) {
      if (leaf.view instanceof SweepView) leaf.view.refresh();
    }
  }

  async open() {
    let leaf = this.app.workspace.getLeavesOfType(VIEW)[0];
    if (!leaf) {
      leaf = this.app.workspace.getLeaf('tab');
      await leaf.setViewState({ type: VIEW, active: true });
    }
    this.app.workspace.revealLeaf(leaf);
  }
};

class NameModal extends Modal {
  constructor(app, title, done) { super(app); this.title = title; this.done = done; }
  onOpen() {
    this.titleEl.setText(this.title);
    const input = this.contentEl.createEl('input', { type: 'text', attr: { placeholder: 'folder name' } });
    input.addClass('zs-input');
    const go = () => { const v = input.value.trim().replace(/[\\/]/g, '-').replace(/^\.+/, ''); this.close(); this.done(v); };
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
    const b = this.contentEl.createEl('button', { text: 'Create and move', cls: 'mod-cta' });
    b.addEventListener('click', go);
    setTimeout(() => input.focus(), 50);
  }
  onClose() { this.contentEl.empty(); }
}

class SweepView extends ItemView {
  constructor(leaf, plugin) {
    super(leaf);
    this.p = plugin;
    this.mode = 'start';
    this.skipped = new Set();
    this.undo = [];
    this.zoom = 1;
    this.busy = false;
    this.ages = new Map();
  }
  getViewType() { return VIEW; }
  getDisplayText() { return 'Sweep notes'; }
  getIcon() { return 'brush'; }

  get vault() { return this.app.vault; }
  get d() { return this.p.data; }

  async onOpen() {
    const root = this.contentEl;
    root.empty();
    root.addClass('zs');
    root.tabIndex = 0;
    this.registerDomEvent(root, 'keydown', (e) => this.onKey(e));
    this.app.workspace.onLayoutReady(() => this.showStart());
  }

  async onClose() { this.dropCard(); }

  onResize() {
    this.contentEl.toggleClass('is-narrow', this.contentEl.clientWidth < 640);
    if (this.mode === 'sort' && this.cardEl) this.placeNotebooks();
  }

  refresh() {
    if (this.mode === 'start') this.showStart();
    else if (!this.busy && !this.drag) this.nextCard();
  }

  // ---- notes ---------------------------------------------------------------------------------
  folder() {
    const f = this.d.source ? this.vault.getAbstractFileByPath(this.d.source) : this.vault.getRoot();
    return f instanceof TFolder ? f : this.vault.getRoot();
  }

  notesIn(folder) {
    return folder.children.filter((f) => f instanceof TFile && f.extension === 'md');
  }

  age(f) {
    if (this.ages.has(f.path)) return this.ages.get(f.path);
    const fm = (this.app.metadataCache.getFileCache(f) || {}).frontmatter || {};
    let t = NaN;
    for (const k of ['created', 'date']) {
      if (fm[k] && isNaN(t)) t = Date.parse(String(fm[k]).slice(0, 16));
    }
    if (isNaN(t)) t = f.stat.mtime;
    this.ages.set(f.path, t);
    return t;
  }

  toScan(folder = this.folder()) {
    return this.notesIn(folder).filter((f) => !this.p.kept.has(f.path));
  }

  queue() {
    const all = this.notesIn(this.folder()).sort((a, b) => this.age(a) - this.age(b));
    if (this.mode === 'sweep') return all.filter((f) => !this.p.kept.has(f.path) && !this.skipped.has(f.path));
    const batch = new Set(this.d.batch);
    return all.filter((f) => this.p.kept.has(f.path) && !this.p.stays.has(f.path) && !this.skipped.has(f.path)
      && (!batch.size || batch.has(f.path)));
  }

  round() { return Math.floor((this.d.stats.moved + this.p.stays.size) / ROUND) + 1; }

  folderName() { return this.d.source ? this.d.source.split('/').pop() : this.vault.getName(); }

  // ---- start screen: which vault, which notebook --------------------------------------------
  showStart() {
    this.mode = 'start';
    this.dropCard();
    const root = this.contentEl;
    root.empty();
    const page = root.createDiv('zs-start');
    page.createDiv({ cls: 'zs-label', text: 'SWEEP NOTES' });

    page.createDiv({ cls: 'zs-label zs-head', text: 'VAULT' });
    const here = this.vault.getName();
    const names = [...new Set([here, ...(this.d.vaults || [])])];
    for (const name of names) {
      const row = page.createDiv({ cls: 'zs-row' + (name === here ? ' is-on' : '') });
      row.createSpan({ text: (name === here ? '● ' : '') + name });
      row.createSpan({ cls: 'zs-dim', text: name === here ? `${this.toScan(this.vault.getRoot()).length} loose notes to scan` : 'open' });
      if (name !== here) {
        row.addEventListener('click', () => window.open(`obsidian://zorro-sweep?vault=${encodeURIComponent(name)}`));
      }
    }

    page.createDiv({ cls: 'zs-label zs-head', text: 'NOTEBOOK TO CLEAN UP' });
    const folders = [this.vault.getRoot(), ...this.vault.getRoot().children
      .filter((f) => f instanceof TFolder && !f.name.startsWith('.') && !f.name.startsWith('_'))
      .sort((a, b) => a.name.localeCompare(b.name))];
    for (const f of folders) {
      const path = f.isRoot() ? '' : f.path;
      const left = this.toScan(f).length;
      if (!left && path !== this.d.source && !this.notesIn(f).length) continue;
      const row = page.createDiv({ cls: 'zs-row' + (path === this.d.source ? ' is-on' : '') });
      row.createSpan({ text: (path === this.d.source ? '● ' : '') + (f.isRoot() ? 'Loose notes (top)' : f.name) });
      row.createSpan({ cls: 'zs-dim', text: String(left) });
      row.addEventListener('click', async () => {
        if (this.d.source !== path) {
          this.d.source = path;
          this.skipped.clear();
          await this.p.save();
        }
        this.showStart();
      });
    }

    const total = this.notesIn(this.folder()).length;
    const left = this.toScan().length;
    const bar = page.createDiv('zs-bar zs-wide');
    bar.createEl('b').style.width = `${total ? (100 * (total - left) / total) : 100}%`;
    page.createDiv({ cls: 'zs-dim zs-small',
      text: `${total ? Math.round(100 * (total - left) / total) : 100}% DONE · ROUND ${this.round()} · ${this.d.batch.length} / ${ROUND} KEPT` });
    const go = page.createEl('button', { cls: 'zs-go', text: 'CONTINUE' });
    go.addEventListener('click', () => this.play());
    root.focus();
  }

  play() {
    const root = this.contentEl;
    root.empty();
    root.toggleClass('is-narrow', root.clientWidth < 640);
    this.topEl = root.createDiv('zs-top');
    this.stage = root.createDiv('zs-stage');
    this.undoEl = root.createDiv('zs-undo');
    this.undoEl.addEventListener('click', () => this.doUndo());
    this.hintEl = root.createDiv('zs-hint');
    this.toastEl = root.createDiv('zs-toast');
    this.bannerEl = root.createDiv('zs-banner');
    this.mode = this.d.batch.length >= ROUND || (!this.toScan().length && this.d.batch.length) ? 'sort' : 'sweep';
    this.nextCard();
    root.focus();
  }

  setMode(m) {
    if (m === this.mode) return;
    this.mode = m;
    this.skipped.clear();
    this.nextCard();
  }

  drawTop(left) {
    const t = this.topEl;
    t.empty();
    const l = t.createDiv('zs-top-l');
    const sw = l.createSpan({ cls: 'zs-tab' + (this.mode === 'sweep' ? ' is-on' : ''), text: 'KEEP OR DELETE' });
    const so = l.createSpan({ cls: 'zs-tab' + (this.mode === 'sort' ? ' is-on' : ''), text: 'SORT' });
    sw.addEventListener('click', () => this.setMode('sweep'));
    so.addEventListener('click', () => this.setMode('sort'));
    l.createDiv({ cls: 'zs-label zs-fg', text: this.mode === 'sort'
      ? `ROUND ${this.round()} · ${this.d.batch.length - left} / ${this.d.batch.length}` : `ROUND ${this.round()}` });
    const dots = t.createDiv('zs-dots');
    const n = this.d.batch.length;
    for (let i = 0; i < ROUND; i++) {
      const done = this.mode === 'sort' && i < n - left;
      dots.createEl('i', { cls: done ? 'is-done' : (i < n ? 'is-on' : '') });
    }
    const r = t.createDiv('zs-top-r');
    const pick = r.createSpan({ cls: 'zs-btn', text: `${this.vault.getName()}${this.d.source ? ' / ' + this.folderName() : ''} ▾` });
    pick.addEventListener('click', () => this.showStart());
    const total = this.notesIn(this.folder()).length;
    const scan = this.toScan().length;
    r.createDiv({ cls: 'zs-dim zs-small', text: `${scan} TO SCAN · ${total ? Math.round(100 * (total - scan) / total) : 100}% DONE` });
    r.createDiv('zs-bar').createEl('b').style.width = `${total ? 100 * (total - scan) / total : 100}%`;
  }

  // ---- the card ---------------------------------------------------------------------------
  dropCard() {
    if (this.cardComp) { this.removeChild(this.cardComp); this.cardComp = null; }
    this.cardEl = null;
  }

  nextCard() {
    if (this.mode === 'start') return;
    this.dropCard();
    let q = this.queue();
    if (!q.length && this.skipped.size) { this.skipped.clear(); q = this.queue(); }
    if (!q.length && this.mode === 'sort') {
      if (this.d.batch.length) {
        const n = this.d.batch.length;
        this.d.batch = [];
        this.p.save();
        this.banner(`ROUND ${this.round() - 1} DONE`, `${n} notes sorted · on to the next ${ROUND}`);
      }
      if (this.toScan().length) { this.setMode('sweep'); return; }
    }
    if (!q.length && this.mode === 'sweep' && this.d.batch.length) {
      this.banner('LAST ROUND', 'sort the last ones you kept');
      this.setMode('sort');
      return;
    }
    this.drawTop(q.length);
    this.stage.empty();
    this.stage.toggleClass('is-sort', this.mode === 'sort');
    this.zoom = 1;
    this.drawUndo();
    this.hintEl.setText(this.mode === 'sort'
      ? 'drag onto a notebook · tap a notebook · 1–9 · space skip · double-click open · ctrl+Z undo'
      : '← keep · → delete · space skip · double-click open · ctrl+Z undo · +/− zoom');
    if (!q.length) {
      const e = this.stage.createDiv('zs-empty');
      e.createDiv({ cls: 'zs-big', text: 'ALL SWEPT' });
      e.createDiv({ cls: 'zs-dim', text: `nothing left to scan in ${this.folderName()}` });
      return;
    }
    if (this.mode === 'sweep') {
      this.stage.createDiv({ cls: 'zs-side zs-side-l', text: '◀ KEEP' });
      this.stage.createDiv({ cls: 'zs-side zs-side-r', text: 'DELETE ▶' });
    }
    this.showCard(q[0]);
    if (this.mode === 'sort') this.placeNotebooks();
  }

  async showCard(file) {
    const card = this.stage.createDiv('zs-card');
    this.cardEl = card;
    this.cardFile = file;
    card.createDiv({ cls: 'zs-stamp zs-keep', text: 'KEEP' });
    card.createDiv({ cls: 'zs-stamp zs-del', text: 'DELETE' });
    card.createDiv({ cls: 'zs-title', text: file.basename });
    const meta = card.createDiv('zs-meta');
    const body = card.createDiv('zs-body markdown-rendered');
    this.cardComp = new Component();
    this.addChild(this.cardComp);

    let text = await this.vault.cachedRead(file);
    if (this.cardEl !== card) return;
    const fm = text.match(/^---\n[\s\S]*?\n---\n?/);
    if (fm) text = text.slice(fm[0].length);
    const words = text.split(/\s+/).filter(Boolean).length;
    const links = Object.keys((this.app.metadataCache.resolvedLinks || {})[file.path] || {}).filter((p) => !p.endsWith('.md'));
    const when = new Date(this.age(file));
    meta.setText([when.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }).toUpperCase(),
      ago(this.age(file)).toUpperCase(), `${words} WORD${words === 1 ? '' : 'S'}`,
      ...(links.length ? [`${links.length} ATTACHMENT${links.length > 1 ? 'S' : ''}`] : [])].join(' · '));
    card.addClass(words < 40 ? 'is-short' : words < 140 ? 'is-medium' : 'is-long');
    if (!text.trim()) body.createDiv({ cls: 'zs-dim', text: '(empty note)' });
    else await MarkdownRenderer.render(this.app, text, body, file.path, this.cardComp);
    // links inside the card don't navigate away (double-click opens the note instead)
    body.addEventListener('click', (e) => { if (e.target.closest('a')) { e.preventDefault(); e.stopPropagation(); } }, true);
    this.hookCard(card);
  }

  setZoom(z) {
    this.zoom = Math.max(0.6, Math.min(3, z));
    if (this.cardEl) this.cardEl.style.setProperty('--zs-zoom', this.zoom);
  }

  hookCard(card) {
    const pts = new Map();
    let pinch = null;
    let lastTap = 0;
    const capture = (id) => { try { card.setPointerCapture(id); } catch (err) { /* already gone */ } };
    card.addEventListener('pointerdown', (e) => {
      if (this.busy) return;
      pts.set(e.pointerId, [e.clientX, e.clientY]);
      if (pts.size === 2) {
        const [a, b] = [...pts.values()];
        pinch = { d: Math.hypot(a[0] - b[0], a[1] - b[1]), z: this.zoom };
        this.drag = null;
        card.style.transform = '';
        return;
      }
      this.drag = { x: e.clientX, y: e.clientY, dx: 0, dy: 0, on: this.mode === 'sort', id: e.pointerId };
      if (this.mode === 'sort') { capture(e.pointerId); card.addClass('is-lifted'); }
    });
    card.addEventListener('pointermove', (e) => {
      if (!pts.has(e.pointerId)) return;
      pts.set(e.pointerId, [e.clientX, e.clientY]);
      if (pinch && pts.size === 2) {
        const [a, b] = [...pts.values()];
        this.setZoom(pinch.z * Math.hypot(a[0] - b[0], a[1] - b[1]) / pinch.d);
        return;
      }
      const g = this.drag;
      if (!g || g.id !== e.pointerId) return;
      g.dx = e.clientX - g.x;
      g.dy = e.clientY - g.y;
      if (!g.on && Math.abs(g.dx) > 10 && Math.abs(g.dx) > Math.abs(g.dy) * 1.2) {
        g.on = true;                                 // a sideways drag: it's a swipe, not a scroll
        capture(e.pointerId);
      }
      if (!g.on) return;
      e.preventDefault();
      if (this.mode === 'sweep') {
        card.style.transform = `translateX(${g.dx}px) rotate(${g.dx / 40}deg)`;
        const k = Math.min(1, Math.abs(g.dx) / (this.stage.clientWidth * 0.22));
        card.style.setProperty('--zs-keep', g.dx < 0 ? k : 0);
        card.style.setProperty('--zs-del', g.dx > 0 ? k : 0);
      } else {
        card.style.transform = `translate(${g.dx}px, ${g.dy}px) scale(.45) rotate(${g.dx / 60}deg)`;
        this.hot(e.clientX, e.clientY);
      }
    });
    const up = (e) => {
      pts.delete(e.pointerId);
      if (pinch) { if (!pts.size) pinch = null; return; }
      const g = this.drag;
      this.drag = null;
      if (!g || g.id !== e.pointerId) return;
      card.removeClass('is-lifted');
      const moved = Math.hypot(g.dx, g.dy) > 8;
      if (!moved && e.type === 'pointerup') {         // a tap; two quick ones open the note
        const now = Date.now();
        if (now - lastTap < 350) { this.openNote(); lastTap = 0; } else lastTap = now;
      }
      if (!g.on) { card.style.transform = ''; return; }
      if (this.mode === 'sweep') {
        if (Math.abs(g.dx) > this.stage.clientWidth * 0.22) this.fly(g.dx > 0 ? 'delete' : 'keep');
        else this.snapBack();
      } else {
        const i = this.hot(e.clientX, e.clientY);
        if (i != null && e.type === 'pointerup') this.sendTo(i, true);
        else this.snapBack();
      }
    };
    card.addEventListener('pointerup', up);
    card.addEventListener('pointercancel', up);
    card.addEventListener('wheel', (e) => {
      if (e.ctrlKey) { e.preventDefault(); this.setZoom(this.zoom * (e.deltaY < 0 ? 1.1 : 0.9)); }
    }, { passive: false });
  }

  snapBack() {
    const c = this.cardEl;
    if (!c) return;
    c.addClass('is-anim');
    c.style.transform = '';
    c.style.setProperty('--zs-keep', 0);
    c.style.setProperty('--zs-del', 0);
    setTimeout(() => c.removeClass('is-anim'), 250);
    this.hot(-1, -1);
  }

  fly(what) {
    const c = this.cardEl;
    if (!c || this.busy) return;
    this.busy = true;
    const w = this.stage.clientWidth;
    c.addClass('is-anim');
    c.style.setProperty(what === 'keep' ? '--zs-keep' : '--zs-del', 1);
    c.style.transform = `translateX(${what === 'keep' ? -w : w}px) rotate(${what === 'keep' ? -18 : 18}deg)`;
    c.style.opacity = '0';
    const file = this.cardFile;
    setTimeout(async () => {
      try { await (what === 'keep' ? this.keep(file) : this.remove(file)); } finally { this.busy = false; }
      this.nextCard();
    }, 240);
  }

  openNote() {
    if (this.cardFile) this.app.workspace.getLeaf('tab').openFile(this.cardFile);
  }

  // ---- notebooks (sort) ----------------------------------------------------------------------
  dests() {
    const root = this.vault.getRoot();
    const attach = (this.vault.getConfig && this.vault.getConfig('attachmentFolderPath')) || '';
    const out = root.children
      .filter((f) => f instanceof TFolder && !f.name.startsWith('.') && !f.name.startsWith('_')
        && f.path !== this.d.source && f.path !== attach.replace(/^\.?\/?/, ''))
      .sort((a, b) => a.name.localeCompare(b.name))
      .map((f) => ({ name: f.name, path: f.path, n: this.countMd(f) }));
    out.push({ name: `Stays in ${this.folderName()}`, stay: true });
    out.push({ name: '+ New folder', make: true });
    return out;
  }

  countMd(folder) {
    let n = 0;
    for (const c of folder.children) {
      if (c instanceof TFolder) n += this.countMd(c);
      else if (c.extension === 'md') n++;
    }
    return n;
  }

  placeNotebooks() {
    for (const el of this.stage.querySelectorAll('.zs-nb')) el.remove();
    this.nbs = this.dests();
    const W = this.stage.clientWidth, H = this.stage.clientHeight;
    const narrow = W < 640;
    const cz = narrow ? { x: W * 0.1, y: H * 0.34, w: W * 0.8, h: H * 0.32 }
      : { x: W * 0.31, y: H * 0.04, w: W * 0.38, h: H * 0.62 };
    if (this.cardEl) {                         // the card sits in the middle zone
      const c = this.cardEl.style, w = Math.min(cz.w, 380);
      Object.assign(c, { width: `${w}px`, marginLeft: `${-w / 2}px`, top: `${cz.y}px`, maxHeight: `${cz.h}px` });
    }
    let cols = narrow ? 2 : 4, rows = narrow ? 6 : 3, cells = [];
    for (let tries = 0; tries < 8; tries++) {
      cells = [];
      const cw = W / cols, ch = H / rows;
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const x = c * cw, y = r * ch;
          const hit = x < cz.x + cz.w && x + cw > cz.x && y < cz.y + cz.h && y + ch > cz.y;
          if (!hit) cells.push({ x, y, w: cw, h: ch });
        }
      }
      if (cells.length >= this.nbs.length) break;
      if (narrow ? cols <= rows / 3 : cols <= rows) cols++; else rows++;
    }
    const plain = this.nbs.filter((d) => !d.stay && !d.make);
    const most = Math.max(1, ...plain.map((d) => d.n));
    // the two special ones take the lowest cells; the notebooks the rest, top to bottom
    const order = [...cells].sort((a, b) => (a.y - b.y) || (a.x - b.x));
    const special = order.slice(-2);
    const mid = cz.y + cz.h / 2;                 // notebooks first close to the card, above and below
    const rest = order.slice(0, -2).sort((a, b) => (Math.abs(a.y + a.h / 2 - mid) - Math.abs(b.y + b.h / 2 - mid)) || (a.x - b.x));
    this.nbs.forEach((d, i) => {
      const cell = d.stay ? special[0] : d.make ? special[1] : rest[plain.indexOf(d)];
      if (!cell) return;
      const kind = d.stay ? 'pill' : d.make ? 'dash' : SHAPES[i % SHAPES.length];
      const f = d.stay || d.make ? 0.7 : 0.6 + 0.4 * Math.sqrt(d.n / most);
      const aspect = kind === 'pill' || kind === 'dash' ? 0.5 : kind === 'circle' || kind === 'diamond' ? 0.9 : 0.72;
      let w = Math.min(cell.w * 0.9, (cell.h * 0.9) / aspect) * f;
      let h = w * aspect;
      w = Math.max(w, 110); h = Math.max(h, 56);
      const jx = (hash(d.name) - 0.5) * Math.max(0, cell.w - w) * 0.8;
      const jy = (hash(d.name + '.') - 0.5) * Math.max(0, cell.h - h) * 0.8;
      const el = this.stage.createDiv('zs-nb');
      const x = Math.max(4, Math.min(W - w - 4, cell.x + (cell.w - w) / 2 + jx));
      const y = Math.max(4, Math.min(H - h - 4, cell.y + (cell.h - h) / 2 + jy));
      el.style.cssText = `left:${x}px;top:${y}px;width:${w}px;height:${h}px`;
      el.innerHTML = `<svg width="${w}" height="${h}" viewBox="-1 -1 ${w + 2} ${h + 2}">${shapeSvg(kind, w, h)}</svg>`;
      if (i < 9) el.createDiv({ cls: 'zs-nb-k', text: String(i + 1) });
      const t = el.createDiv('zs-nb-t');
      t.createDiv({ text: d.name });
      if (d.n != null) t.createDiv({ cls: 'zs-nb-n', text: `${d.n} notes` });
      el.addEventListener('click', () => { if (!this.busy) this.sendTo(i, false); });
      d.el = el;
    });
  }

  hot(x, y) {
    let found = null;
    (this.nbs || []).forEach((d, i) => {
      if (!d.el) return;
      const r = d.el.getBoundingClientRect();
      const on = x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
      d.el.toggleClass('is-hot', on);
      if (on) found = i;
    });
    return found;
  }

  async sendTo(i, dropped) {
    const d = (this.nbs || [])[i];
    const file = this.cardFile;
    if (!d || !file || this.busy) return;
    this.busy = true;
    try {
      if (d.stay) await this.stay(file);
      else if (d.make) {
        const name = await new Promise((res) => new NameModal(this.app, 'New folder', res).open());
        if (!name) { this.snapBack(); return; }
        if (!this.vault.getAbstractFileByPath(name)) await this.vault.createFolder(name);
        await this.send(file, { name, path: name });
      } else await this.send(file, d);
    } catch (e) {
      new Notice(`Sweep: ${e.message || e}`);
      this.snapBack();
      return;
    } finally { this.busy = false; }
    if (dropped && this.cardEl) this.cardEl.addClass('is-gone');
    setTimeout(() => this.nextCard(), dropped ? 120 : 0);
  }

  // ---- what the actions do ------------------------------------------------------------------
  free(path) {
    if (!this.vault.getAbstractFileByPath(path)) return path;
    const dot = path.lastIndexOf('.');
    for (let i = 2; i < 1000; i++) {
      const p = `${path.slice(0, dot)} ${i}${path.slice(dot)}`;
      if (!this.vault.getAbstractFileByPath(p)) return p;
    }
    return path;
  }

  async keep(file) {
    this.p.kept.add(file.path);
    if (!this.d.batch.includes(file.path)) this.d.batch.push(file.path);
    this.undo.push({ what: 'keep', path: file.path, label: `kept “${file.basename}”` });
    await this.p.save();
    const n = this.d.batch.length;
    if (n >= ROUND) {
      this.banner(`ROUND ${this.round()}`, `${n} kept · now sort them into notebooks`);
      this.mode = 'sort';
      this.skipped.clear();
    } else this.toast(`kept · ${n} of ${ROUND}`);
  }

  ownAttachments(file) {
    const all = this.app.metadataCache.resolvedLinks || {};
    const mine = Object.keys(all[file.path] || {}).filter((p) => !p.endsWith('.md'));
    return mine.filter((t) => !Object.entries(all).some(([src, to]) => src !== file.path && to[t]))
      .map((p) => this.vault.getAbstractFileByPath(p)).filter((f) => f instanceof TFile);
  }

  async remove(file) {
    // to the vault's .trash folder: gone everywhere (Sync), still on this device for a while
    const files = [...this.ownAttachments(file), file];
    const saved = [];
    for (const f of files) saved.push({ path: f.path, data: await this.vault.readBinary(f) });
    for (const f of files) await this.vault.trash(f, false);
    this.d.stats.deleted++;
    this.undo.push({ what: 'delete', saved, label: `deleted “${file.basename}”` });
    await this.p.save();
    this.toast('deleted · undo brings it back');
  }

  async send(file, d) {
    const from = file.path;
    const to = this.free(`${d.path}/${file.name}`);
    await this.app.fileManager.renameFile(file, to);        // links to it are updated
    this.p.kept.delete(from);
    this.p.stays.delete(from);
    this.d.stats.moved++;
    this.undo.push({ what: 'send', from, to, label: `“${file.basename}” → ${d.name}` });
    await this.p.save();
    this.toast(`→ ${d.name}`);
  }

  async stay(file) {
    this.p.stays.add(file.path);
    this.undo.push({ what: 'stay', path: file.path, label: `“${file.basename}” stays` });
    await this.p.save();
    this.toast(`stays in ${this.folderName()}`);
  }

  async doUndo() {
    const u = this.undo.pop();
    if (!u || this.busy) return;
    this.busy = true;
    try {
      if (u.what === 'keep') {
        this.p.kept.delete(u.path);
        this.d.batch = this.d.batch.filter((p) => p !== u.path);
        if (this.mode === 'sort' && this.d.batch.length < ROUND) this.mode = 'sweep';
      } else if (u.what === 'stay') {
        this.p.stays.delete(u.path);
      } else if (u.what === 'send') {
        const f = this.vault.getAbstractFileByPath(u.to);
        if (f instanceof TFile) await this.app.fileManager.renameFile(f, this.free(u.from));
        this.p.kept.add(u.from);
        this.d.stats.moved = Math.max(0, this.d.stats.moved - 1);
      } else if (u.what === 'delete') {
        for (const s of u.saved) {
          const dir = s.path.includes('/') ? s.path.slice(0, s.path.lastIndexOf('/')) : '';
          if (dir && !this.vault.getAbstractFileByPath(dir)) await this.vault.createFolder(dir);
          await this.vault.createBinary(this.free(s.path), s.data);
          const t = `.trash/${s.path.split('/').pop()}`;        // and not twice: out of .trash
          try {
            const st = await this.vault.adapter.stat(t);
            if (st && st.size === s.data.byteLength) await this.vault.adapter.remove(t);
          } catch (e) { /* not there */ }
        }
        this.d.stats.deleted = Math.max(0, this.d.stats.deleted - 1);
      }
      await this.p.save();
      this.toast(`undone: ${u.label}`);
    } catch (e) {
      new Notice(`Sweep: could not undo: ${e.message || e}`);
    } finally { this.busy = false; }
    this.skipped.clear();
    this.nextCard();
  }

  drawUndo() {
    const u = this.undo[this.undo.length - 1];
    this.undoEl.setText(u ? `↶ undo · ${u.label}` : '');
    this.undoEl.toggleClass('is-on', !!u);
  }

  toast(text) {
    this.toastEl.setText(text);
    this.toastEl.addClass('is-on');
    clearTimeout(this.toastT);
    this.toastT = setTimeout(() => this.toastEl.removeClass('is-on'), 1400);
  }

  banner(big, small) {
    const b = this.bannerEl;
    b.empty();
    b.createDiv({ cls: 'zs-big', text: big });
    b.createDiv({ cls: 'zs-dim', text: small });
    b.addClass('is-on');
    clearTimeout(this.bannerT);
    this.bannerT = setTimeout(() => b.removeClass('is-on'), 1800);
  }

  // ---- keys (laptop) ------------------------------------------------------------------------
  onKey(e) {
    if (this.mode === 'start') {
      if (e.key === 'Enter') { e.preventDefault(); this.play(); }
      return;
    }
    if (e.target && e.target.tagName === 'INPUT') return;
    const k = e.key;
    if ((e.ctrlKey || e.metaKey) && k.toLowerCase() === 'z' || k === 'Backspace') { e.preventDefault(); this.doUndo(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey || this.busy || !this.cardEl) return;
    let used = true;
    if (k === ' ') { this.skipped.add(this.cardFile.path); this.nextCard(); }
    else if (k === 'o' || k === 'O') this.openNote();
    else if (k === '+' || k === '=') this.setZoom(this.zoom * 1.15);
    else if (k === '-') this.setZoom(this.zoom / 1.15);
    else if (k === '0') this.setZoom(1);
    else if (this.mode === 'sweep' && k === 'ArrowLeft') this.fly('keep');
    else if (this.mode === 'sweep' && k === 'ArrowRight') this.fly('delete');
    else if (this.mode === 'sort' && /^[1-9]$/.test(k)) this.sendTo(Number(k) - 1, false);
    else if (k === 'PageDown' || k === 'PageUp') {
      const b = this.cardEl.querySelector('.zs-body');
      if (b) b.scrollBy(0, (k === 'PageDown' ? 1 : -1) * b.clientHeight * 0.8);
    } else used = false;
    if (used) e.preventDefault();
  }
}
