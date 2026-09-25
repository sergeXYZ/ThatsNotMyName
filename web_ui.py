#!/usr/bin/env python3
"""That's Not My Name — local web UI.

Browse uses the macOS file dialog without a UTI filter, because .dbpr and
.dbcc are not registered file types and would otherwise vanish from search.
Create.Control copies always replace every sound object. Device I/O is
switched to 128×64 Extra-large (XL) only when that checkbox is on.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import traceback
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

from mtx_job import inspect_cc, inspect_sheet, run_apply

if getattr(sys, "frozen", False):
    ROOT = Path(getattr(sys, "_MEIPASS"))
else:
    ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
HOST = "127.0.0.1"
PORT = 8765
APP_NAME = "That's Not My Name"
if sys.platform == "win32":
    SUPPORT = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    LOG_PATH = SUPPORT / f"{APP_NAME}.log"
else:
    SUPPORT = Path.home() / "Library/Application Support" / APP_NAME
    LOG_PATH = Path.home() / "Library/Logs" / f"{APP_NAME}.log"
UPLOADS = SUPPORT / "uploads"

KINDS = {
    "sheet": {".csv", ".xlsx", ".xlsm", ".numbers"},
    "r1": {".dbpr"},
    "cc": {".dbcc"},
}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024


def ensure_assets() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    background = ASSETS / "thats-not-my-name-bg.jpg"
    if not background.is_file():
        bundled = (
            Path.home()
            / ".cursor/projects/Users-serge-Documents-Cursor-Projects-Set-R1-MTX-Input-Names-from-a-spreadsheet/assets"
            / "That_s_Not_My_Name-91a0fe56-f079-4422-8027-4aaba5cc7bc2.jpg"
        )
        if bundled.is_file():
            shutil.copy2(bundled, background)
    warning = ASSETS / "warning-dd.png"
    if not warning.is_file():
        for source in (
            ROOT / "macos" / "warning-dd.png",
            Path.home() / "Documents/Cursor Projects/Digico-x-Soundscape/assets/warning-dd.png",
        ):
            if source.is_file():
                shutil.copy2(source, warning)
                break


def log_line(text: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%H:%M:%S")
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {text}\n")
    except OSError:
        pass


def call(work):
    """Run work, capturing stderr. Returns (result, warnings, error)."""
    captured = io.StringIO()
    try:
        with contextlib.redirect_stderr(captured):
            result = work()
        return result, captured.getvalue().strip(), None
    except SystemExit as exc:
        message = exc.code if isinstance(exc.code, str) else captured.getvalue().strip()
        return None, captured.getvalue().strip(), friendly_access_error(message or "Request failed")
    except Exception as exc:
        log_line(traceback.format_exc())
        return None, captured.getvalue().strip(), friendly_access_error(str(exc))


def reveal_in_finder(report: str) -> None:
    """Show the first written copy that lives in the home folder."""
    if os.environ.get("TNMN_NO_REVEAL") == "1":
        return
    home = Path.home().resolve()
    for line in report.splitlines():
        if not (line.startswith("R1 output: ") or line.startswith("Create.Control output: ")):
            continue
        path = Path(line.split(": ", 1)[1].strip())
        try:
            path.resolve().relative_to(home)
        except (ValueError, OSError):
            continue
        if not path.is_file():
            continue
        if sys.platform == "win32":
            subprocess.Popen(["explorer", f"/select,{path}"])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
        return


def applescript(source: str) -> str:
    completed = subprocess.run(
        ["osascript", "-e", source],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return completed.stdout.strip()
    message = (completed.stderr or completed.stdout or "Cancelled").strip()
    if "User canceled" in message or "-128" in message:
        return ""
    raise SystemExit(message)


def applescript_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def kind_extensions(kind: str) -> set[str]:
    try:
        return KINDS[kind]
    except KeyError as exc:
        raise SystemExit(f"Unknown file kind: {kind}") from exc


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>That's Not My Name</title>
<style>
:root {
  --panel: rgba(198, 255, 74, 0.2);
  --text: #102033;
  --muted: #1c3348;
  --accent: #ff2f92;
  --yellow: #e8ff00;
  --err: #d52626;
  --font: "Trebuchet MS", "Segoe UI", system-ui, sans-serif;
  --mono: "SF Mono", Menlo, ui-monospace, monospace;
}
* { box-sizing: border-box; }
html, body {
  position: fixed; inset: 0;
  width: 100%; height: 100%;
  margin: 0; overflow: hidden;
  color: var(--text);
  font-family: var(--font);
  font-size: 14px;
  background: #1f8fe0;
}
body { display: flex; flex-direction: column; }
.hero {
  flex: 0 0 auto;
  line-height: 0;
  background: #1f8fe0;
}
.hero img { width: 100%; height: auto; display: block; }
.scroll {
  flex: 1 1 auto; min-height: 0; overflow-y: auto;
  overscroll-behavior: contain;
  background: #1f8fe0 url("/assets/bg-rays.png") top center / 100% auto no-repeat;
}
main { max-width: 520px; margin: 0 auto; padding: 12px 14px 40px; }
.tagline {
  margin: 0 0 16px; text-align: center; color: #fff; font-weight: 700;
  text-shadow: 0 2px 0 #102033, 0 8px 18px rgba(0,0,0,.35);
}
.panel {
  background: var(--panel); border: 2px solid rgba(198, 255, 74, 0.95);
  border-radius: 18px; padding: 16px; margin-bottom: 14px;
  box-shadow: 0 10px 24px rgba(8, 40, 80, 0.18);
}
.panel h2 { margin: 0 0 12px; font-size: 16px; display: flex; align-items: center; gap: 10px; }
.num {
  width: 24px; height: 24px; border-radius: 999px; display: inline-grid; place-items: center;
  background: var(--accent); color: #fff; font-size: 12px; font-weight: 800;
  box-shadow: 2px 2px 0 #102033;
}
label.field { display: block; margin: 0 0 10px; }
label.field > span { display: block; margin-bottom: 5px; color: var(--muted); font-size: 12px; font-weight: 700; }
.row { display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: end; }
input[type=text] {
  width: 100%; background: #fff; border: 2px solid #d7dde8; border-radius: 10px; padding: 10px 12px;
}
input[type=text]:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(255,47,146,.22); }
input[type=file] { display: none; }
.check {
  position: relative;
  display: flex; gap: 10px; align-items: flex-start; margin: 8px 0; font-weight: 600; cursor: pointer;
}
.check input {
  position: absolute; inset: 0; width: 100%; height: 100%; margin: 0; opacity: 0; cursor: pointer;
}
.check .tick {
  width: 20px; height: 20px; flex-shrink: 0; margin-top: 1px;
  border: 2px solid #102033; border-radius: 5px; background: #fff;
  box-shadow: 2px 2px 0 #102033;
  display: grid; place-items: center;
}
.check input:checked + .tick { background: var(--yellow); }
.check input:checked + .tick::after {
  content: "";
  width: 5px; height: 10px;
  border: solid #000; border-width: 0 3px 3px 0;
  transform: rotate(45deg) translate(-1px, -1px);
}
.check input:focus-visible + .tick { outline: 2px solid #102033; outline-offset: 2px; }
.hint, .detail { font-size: 12px; margin: 4px 0 0; color: var(--muted); }
.error { font-size: 12px; margin: 4px 0 0; color: var(--err); font-weight: 700; }
.note {
  display: flex; align-items: center; gap: 10px; margin: 4px 0 10px; padding: 8px 10px;
  border-radius: 10px; background: rgba(255,212,0,.28); border: 2px solid rgba(255,122,24,.45);
  color: #7a4a00; font-size: 12px; line-height: 1.35; font-weight: 700;
}
.note img { height: 36px; width: auto; flex-shrink: 0; }
.drop {
  border: 2.5px dashed #9aa8bd; border-radius: 12px; padding: 14px 12px; margin-bottom: 10px;
  background: rgba(255,255,255,.55); cursor: pointer;
}
.drop.hot { border-color: var(--accent); background: rgba(255,47,146,.12); }
.drop strong { display: block; margin-bottom: 4px; }
.btn {
  background: var(--yellow); color: #102033; border: 2px solid #102033; border-radius: 10px; padding: 10px 14px;
  font-weight: 800; cursor: pointer; box-shadow: 3px 3px 0 #102033;
}
.btn:hover { background: #f4ff66; }
.btn.primary {
  background: var(--accent); color: #fff;
  min-width: 210px; font-size: 21px; padding: 15px 21px;
  border-width: 3px; border-radius: 15px;
  box-shadow: 4.5px 4.5px 0 #102033;
  transform: none;
}
.btn.primary:hover,
.btn.primary:active,
.btn.primary:focus {
  background: var(--accent);
  transform: none;
  box-shadow: 4.5px 4.5px 0 #102033;
}
.btn.primary:disabled { opacity: .45; cursor: not-allowed; transform: none; box-shadow: 4.5px 4.5px 0 #102033; }
.actions {
  display: flex; flex-direction: column; align-items: center;
  gap: 14px; margin: 18px 0 36px;
}
.actions .hint {
  width: 100%; max-width: 640px; margin: 0; text-align: center;
  color: #fff; font-weight: 700; text-shadow: 0 1px 2px rgba(0,0,0,.55); white-space: pre-wrap;
}
.actions .hint.bad { color: #ffe14a; }
@media (max-width: 700px) { main { padding-top: 12px; } }
</style>
</head>
<body>
<header class="hero">
  <img src="/assets/logo-header.png" alt="That's Not My Name">
</header>
<div class="scroll">
<main>
  <p class="tagline">Spreadsheet names &amp; colors → R1 / Create.Control</p>

  <section class="panel">
    <h2><span class="num">1</span> Spreadsheet</h2>
    <div class="drop" data-file="sheetFile"><strong>Drop spreadsheet here</strong><span class="hint">CSV, Excel, or Numbers</span></div>
    <input type="file" id="sheetFile">
    <div class="row">
      <label class="field" style="margin:0"><span>Path</span><input type="text" id="sheet" placeholder="/path/to/inputs.xlsx"></label>
      <button class="btn" type="button" data-pick="sheet" data-exts="csv,xlsx,xlsm,numbers">Browse…</button>
    </div>
    <p class="detail" id="sheetDetail"></p>
    <p class="hint">Colors are read from Input Name or Input Number. If both differ, Input Name wins.</p>
    <p class="error" id="sheetError" hidden></p>
  </section>

  <section class="panel">
    <h2><span class="num">2</span> R1</h2>
    <div class="drop" data-file="r1File"><strong>Drop R1 file here</strong><span class="hint">.dbpr</span></div>
    <input type="file" id="r1File">
    <div class="row">
      <label class="field" style="margin:0"><span>Path</span><input type="text" id="r1" placeholder="/path/to/show.dbpr"></label>
      <button class="btn" type="button" data-pick="r1" data-exts="dbpr">Browse…</button>
    </div>
    <label class="check"><input type="checkbox" id="r1Matrix"><span class="tick"></span><span>Name matrix inputs</span></label>
    <label class="check"><input type="checkbox" id="r1Positioning"><span class="tick"></span><span>Name existing objects on all positioning views</span></label>
    <label class="check"><input type="checkbox" id="r1Colors"><span class="tick"></span><span>Change object colors using spreadsheet fills</span></label>
  </section>

  <section class="panel">
    <h2><span class="num">3</span> Create.Control</h2>
    <div class="drop" data-file="ccFile"><strong>Drop Create.Control file here</strong><span class="hint">.dbcc</span></div>
    <input type="file" id="ccFile">
    <div class="row">
      <label class="field" style="margin:0"><span>Path</span><input type="text" id="cc" placeholder="/path/to/project.dbcc"></label>
      <button class="btn" type="button" data-pick="cc" data-exts="dbcc">Browse…</button>
    </div>
    <p class="detail" id="ccDetail"></p>
    <p class="error" id="ccError" hidden></p>
    <div class="note">
      <img src="/assets/warning-dd.png" alt="Warning">
      <span>Every existing sound object is replaced.</span>
    </div>
    <label class="check" id="cc128Label"><input type="checkbox" id="cc128"><span class="tick"></span><span>Switch device to 128×64 Extra-large (XL)</span></label>
    <p class="hint" id="wideNote"></p>
    <label class="check"><input type="checkbox" id="ccColors"><span class="tick"></span><span>Take colors from spreadsheet</span></label>
  </section>

  <section class="panel">
    <h2><span class="num">4</span> Output</h2>
    <div class="row">
      <label class="field" style="margin:0"><span>Destination folder</span><input type="text" id="folder" placeholder="/path/to/output folder"></label>
      <button class="btn" type="button" id="pickFolder">Browse…</button>
    </div>
    <label class="field"><span>Filename</span><input type="text" id="filename" placeholder="Show.mtx"></label>
    <p class="hint">Extension is added automatically (.dbpr / .dbcc). Originals stay unchanged.</p>
  </section>

  <div class="actions">
    <button class="btn primary" id="apply" type="button" disabled>Apply</button>
    <p class="hint" id="status">Spreadsheet, destination, filename, and at least one target.</p>
  </div>
</main>
</div>
<script>
const state = { sheet: null, cc: null };
let wideTouched = false;
const $ = id => document.getElementById(id);
const FIELD = { sheet: 'sheet', r1: 'r1', cc: 'cc' };

const DESKTOP = __DESKTOP__;
function pinPage() {
  if (window.scrollX || window.scrollY) window.scrollTo(0, 0);
}
addEventListener('scroll', pinPage, { passive: true });
addEventListener('focusin', () => requestAnimationFrame(pinPage));
if (window.visualViewport) {
  visualViewport.addEventListener('scroll', pinPage);
  visualViewport.addEventListener('resize', pinPage);
}
document.querySelectorAll('.check').forEach(label => {
  label.addEventListener('mousedown', event => event.preventDefault());
});

function say(text, bad) {
  const el = $('status');
  el.textContent = text;
  el.classList.toggle('bad', !!bad);
}

function suggestFrom(path, fillFolder) {
  if (!path) return;
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean);
  const name = parts.pop() || '';
  if (fillFolder && !$('folder').value.trim()) $('folder').value = '/' + parts.join('/');
  if (!$('filename').value.trim()) $('filename').value = name.replace(/\.[^.]+$/, '') + '.mtx';
}

async function post(url, body) {
  let res;
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {})
    });
  } catch (err) {
    throw new Error('The app could not be reached. ' + (err && err.message ? err.message : ''));
  }
  let data = {};
  try { data = await res.json(); } catch (err) { throw new Error('Server did not return JSON'); }
  if (!res.ok) throw new Error(data.error || 'Request failed');
  return data;
}

async function upload(file, kind) {
  const form = new FormData();
  form.append('file', file);
  form.append('kind', kind);
  const res = await fetch('/api/upload', { method: 'POST', body: form });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Upload failed');
  return data;
}

function needs128() {
  return !!(state.sheet && (state.sheet.count > 64 || state.sheet.max > 64));
}

function already128() {
  return !!(state.cc && state.cc.devices && state.cc.devices.length
    && state.cc.devices.every(d => Number(d.inputs) === 128 && (d.outputs == null || Number(d.outputs) === 64)));
}

function refreshWide() {
  const hasCc = !!$('cc').value.trim();
  $('cc128Label').hidden = !hasCc;
  if (!hasCc) {
    $('wideNote').textContent = '';
    return;
  }
  if (already128()) {
    $('wideNote').textContent = 'Device is already 128×64 Extra-large (XL).';
    return;
  }
  $('wideNote').textContent = needs128() ? 'Spreadsheet goes past input 64.' : '';
  if (!wideTouched && needs128()) $('cc128').checked = true;
}

function canApply() {
  const r1 = $('r1').value.trim();
  const r1Ready = r1 && ($('r1Matrix').checked || $('r1Positioning').checked || $('r1Colors').checked);
  return !!($('sheet').value.trim() && $('folder').value.trim() && $('filename').value.trim() && (r1Ready || $('cc').value.trim()));
}

function touch() {
  refreshWide();
  const ok = canApply();
  $('apply').disabled = !ok;
  if (!$('status').dataset.hold) {
    say(ok
      ? 'Ready to write the copy.'
      : 'Spreadsheet, destination, filename, and at least one target.');
  }
}

async function inspectSheet() {
  const path = $('sheet').value.trim();
  $('sheetError').hidden = true;
  $('sheetDetail').textContent = '';
  state.sheet = null;
  if (!path) { touch(); return; }
  try {
    state.sheet = await post('/api/inspect-sheet', { path });
    const colors = state.sheet.colored
      ? `${state.sheet.colored} colored cells`
      : 'no colored cells in Input Name or Input Number';
    $('sheetDetail').textContent = `${state.sheet.count} entries, ${state.sheet.named} named, highest number ${state.sheet.max}. ${colors}`;
  } catch (err) {
    $('sheetError').hidden = false;
    $('sheetError').textContent = err.message;
  }
  touch();
}

async function inspectCc() {
  const path = $('cc').value.trim();
  $('ccError').hidden = true;
  $('ccDetail').textContent = '';
  state.cc = null;
  if (!path) { touch(); return; }
  try {
    state.cc = await post('/api/inspect-cc', { path });
    $('ccDetail').textContent = state.cc.devices.map(d => `${d.name}: ${d.inputs}×${d.outputs} I/O`).join(' · ');
  } catch (err) {
    $('ccError').hidden = false;
    $('ccError').textContent = err.message;
  }
  touch();
}

async function usePath(kind, path) {
  $(FIELD[kind]).value = path;
  suggestFrom(path, true);
  if (kind === 'sheet') await inspectSheet();
  else if (kind === 'cc') await inspectCc();
  else touch();
}

async function useUpload(file, kind) {
  const allowed = { sheet: ['.csv','.xlsx','.xlsm','.numbers'], r1: ['.dbpr'], cc: ['.dbcc'] }[kind];
  const name = (file.name || '').toLowerCase();
  if (!allowed.some(ext => name.endsWith(ext))) {
    say(`Expected ${allowed.join(', ')}, got ${file.name}`);
    return;
  }
  say(`Loading ${file.name}…`);
  try {
    const data = await upload(file, kind);
    $(FIELD[kind]).value = data.path;
    suggestFrom(data.name || data.path, false);
    if (!$('folder').value.trim()) $('folder').value = data.suggested_folder;
    if (kind === 'sheet') await inspectSheet();
    else if (kind === 'cc') await inspectCc();
    else touch();
    say(`Loaded ${file.name}`);
  } catch (err) {
    say(err.message);
  }
}

document.querySelectorAll('.drop').forEach(drop => {
  const input = $(drop.dataset.file);
  const kind = drop.dataset.file.replace('File', '');
  drop.addEventListener('click', () => input.click());
  drop.addEventListener('dragover', event => { event.preventDefault(); drop.classList.add('hot'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('hot'));
  drop.addEventListener('drop', event => {
    event.preventDefault();
    drop.classList.remove('hot');
    const file = event.dataTransfer.files && event.dataTransfer.files[0];
    if (file) useUpload(file, kind);
  });
  input.addEventListener('change', () => {
    const file = input.files && input.files[0];
    if (file) useUpload(file, kind);
    input.value = '';
  });
});

document.querySelectorAll('[data-pick]').forEach(button => {
  button.addEventListener('click', async () => {
    try {
      const data = await post('/api/pick-file', { extensions: button.dataset.exts.split(',') });
      if (!data.path) return;
      await usePath(button.dataset.pick, data.path);
      say(`Selected ${data.path}`);
    } catch (err) {
      say(err.message);
    }
  });
});

$('pickFolder').addEventListener('click', async () => {
  try {
    const data = await post('/api/pick-folder', {});
    if (!data.path) return;
    $('folder').value = data.path.replace(/\/$/, '');
    touch();
  } catch (err) {
    say(err.message);
  }
});

let sheetTimer = null;
let ccTimer = null;
$('sheet').addEventListener('input', () => {
  clearTimeout(sheetTimer);
  sheetTimer = setTimeout(inspectSheet, 400);
  suggestFrom($('sheet').value.trim(), true);
  touch();
});
$('r1').addEventListener('input', () => { suggestFrom($('r1').value.trim(), true); touch(); });
$('cc').addEventListener('input', () => {
  wideTouched = false;
  clearTimeout(ccTimer);
  ccTimer = setTimeout(inspectCc, 400);
  suggestFrom($('cc').value.trim(), true);
  touch();
});
$('cc128').addEventListener('change', () => { wideTouched = true; touch(); });
['r1Matrix','r1Positioning','r1Colors','ccColors','folder','filename'].forEach(id => {
  $(id).addEventListener('input', touch);
  $(id).addEventListener('change', touch);
});

$('apply').addEventListener('click', async () => {
  const job = {
    spreadsheet: $('sheet').value.trim(),
    folder: $('folder').value.trim(),
    filename: $('filename').value.trim()
  };
  const r1 = $('r1').value.trim();
  if (r1 && ($('r1Matrix').checked || $('r1Positioning').checked || $('r1Colors').checked)) {
    job.r1 = {
      path: r1,
      matrix: $('r1Matrix').checked,
      positioning: $('r1Positioning').checked,
      colors: $('r1Colors').checked
    };
  }
  const cc = $('cc').value.trim();
  if (cc) job.cc = { path: cc, replace: true, colors: $('ccColors').checked, inputs128: $('cc128').checked };
  $('apply').disabled = true;
  $('status').dataset.hold = '1';
  say('Writing copies…');
  try {
    const data = await post('/api/apply', job);
    say(data.report || 'Finished, but the app did not report a file path.');
  } catch (err) {
    say(err.message || 'Apply failed.', true);
  } finally {
    $('apply').disabled = !canApply();
  }
});

if (!$('folder').value.trim()) $('folder').value = DESKTOP;
touch();
</script>
</body>
</html>
"""


@app.get("/")
def index():
    return HTML.replace("__DESKTOP__", json.dumps(writable_desktop()))


@app.get("/health")
def health():
    return jsonify({"ok": True, "name": APP_NAME})


@app.get("/assets/<path:name>")
def assets(name: str):
    return send_from_directory(ASSETS, name)


@app.post("/api/inspect-sheet")
def api_inspect_sheet():
    path = (request.get_json(silent=True) or {}).get("path", "").strip()
    if not path:
        return jsonify({"error": "Path required"}), 400
    result, _warnings, error = call(lambda: inspect_sheet(Path(path)))
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@app.post("/api/inspect-cc")
def api_inspect_cc():
    path = (request.get_json(silent=True) or {}).get("path", "").strip()
    if not path:
        return jsonify({"error": "Path required"}), 400
    result, _warnings, error = call(lambda: inspect_cc(Path(path)))
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@app.post("/api/upload")
def api_upload():
    uploaded = request.files.get("file")
    kind = (request.form.get("kind") or "").strip()
    if uploaded is None or not uploaded.filename:
        return jsonify({"error": "No file uploaded"}), 400
    try:
        allowed = kind_extensions(kind)
    except SystemExit as exc:
        return jsonify({"error": str(exc.code)}), 400
    original = Path(uploaded.filename)
    suffix = original.suffix.lower()
    if suffix not in allowed:
        return jsonify({"error": f"Expected {', '.join(sorted(allowed))}, got {original.name}"}), 400
    UPLOADS.mkdir(parents=True, exist_ok=True)
    safe = secure_filename(original.name) or f"upload{suffix}"
    dest = UPLOADS / f"{uuid.uuid4().hex[:8]}-{safe}"
    uploaded.save(dest)
    return jsonify(
        {
            "path": str(dest.resolve()),
            "name": original.name,
            "suggested_folder": writable_desktop(),
        }
    )


@app.post("/api/pick-file")
def api_pick_file():
    body = request.get_json(silent=True) or {}
    extensions = [str(item).lower().lstrip(".") for item in (body.get("extensions") or []) if str(item).strip()]
    label = "Choose a file"
    if extensions:
        label = "Choose a file (" + ", ".join("." + item for item in extensions) + ")"
    try:
        result = choose_path(False, label, extensions)
    except SystemExit as exc:
        message = exc.code if isinstance(exc.code, str) else "Cancelled"
        return jsonify({"error": friendly_access_error(message)}), 400
    except Exception as exc:
        return jsonify({"error": friendly_access_error(str(exc))}), 400
    if not result:
        return jsonify({"path": ""})
    path = Path(result)
    if extensions and path.suffix.lower().lstrip(".") not in extensions:
        wanted = ", ".join("." + item for item in extensions)
        return jsonify({"error": f"Expected {wanted}, got {path.name}"}), 400
    return jsonify({"path": str(path)})


@app.post("/api/pick-folder")
def api_pick_folder():
    try:
        result = choose_path(True, "Choose destination folder")
    except SystemExit as exc:
        message = exc.code if isinstance(exc.code, str) else "Cancelled"
        return jsonify({"error": friendly_access_error(message)}), 400
    except Exception as exc:
        return jsonify({"error": friendly_access_error(str(exc))}), 400
    return jsonify({"path": (result or "").rstrip("/")})


@app.post("/api/apply")
def api_apply():
    job = request.get_json(silent=True) or {}
    folder = Path(str(job.get("folder") or "")).expanduser()
    if str(job.get("folder") or "").strip():
        try:
            folder.resolve().relative_to(ROOT.resolve())
        except ValueError:
            pass
        else:
            return jsonify({"error": "Choose a destination folder outside the app."}), 400
    cc = job.get("cc")
    if isinstance(cc, dict):
        cc["replace"] = True
        cc["inputs128"] = bool(cc.get("inputs128"))
    log_line(f"apply folder={job.get('folder')!r} file={job.get('filename')!r}")
    result, warnings, error = call(lambda: run_apply(job))
    if error:
        log_line(f"apply failed: {error}")
        return jsonify({"error": error}), 400
    report = result if isinstance(result, str) else str(result)
    if warnings:
        report = f"{warnings}\n{report}"
    log_line("apply ok\n" + report)
    reveal_in_finder(report)
    return jsonify({"report": report})


def friendly_access_error(message: str) -> str:
    if message and ("Operation not permitted" in message or "authorization denied" in message):
        return "macOS blocked that folder. Use Browse and choose the file or folder again."
    return message


_SCOPES: list = []


def _windows_filters(extensions: list[str]) -> tuple[str, ...]:
    """pywebview only accepts 'Words (*.ext;*.ext)' — extra parentheses cancel the dialog."""
    pattern = ";".join(f"*.{ext}" for ext in extensions) if extensions else "*.*"
    return (f"Files ({pattern})", "All files (*.*)")


def _on_windows_ui(window, action):
    """WinForms file dialogs only open on the window thread. A Flask thread is ignored."""
    from webview.platforms import winforms

    form = winforms.BrowserView.instances.get(window.uid)
    if form is None or not form.InvokeRequired:
        return action()
    box: dict = {}

    def run():
        try:
            box["value"] = action()
        except Exception as exc:
            box["error"] = exc
        return None

    from System import Func, Type

    form.Invoke(Func[Type](run))
    if "error" in box:
        raise box["error"]
    return box.get("value")


def windows_choose(directory: bool, prompt: str, extensions: list[str]) -> str:
    try:
        import webview
    except Exception:
        webview = None

    if webview is not None and webview.windows:
        window = webview.windows[0]

        def show():
            kind = webview.FOLDER_DIALOG if directory else webview.OPEN_DIALOG
            filters = () if directory else _windows_filters(extensions)
            return window.create_file_dialog(kind, directory="", file_types=filters)

        chosen = _on_windows_ui(window, show)
        if not chosen:
            return ""
        return str(chosen[0] if isinstance(chosen, (list, tuple)) else chosen)

    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass
    if directory:
        chosen = filedialog.askdirectory(title=prompt, parent=root)
    else:
        pattern = " ".join(f"*.{ext}" for ext in extensions) if extensions else "*.*"
        chosen = filedialog.askopenfilename(
            title=prompt,
            parent=root,
            filetypes=[(prompt, pattern), ("All files", "*.*")],
        )
    root.destroy()
    return chosen or ""


def choose_path(directory: bool, prompt: str, extensions: list[str] | None = None) -> str:
    extensions = extensions or []
    if sys.platform == "win32":
        return windows_choose(directory, prompt, extensions)
    if sys.platform == "darwin" and os.environ.get("TNMN_APP") == "1":
        return cocoa_choose(directory, prompt)
    if directory:
        source = "POSIX path of (choose folder with prompt " + applescript_string(prompt) + ")"
    else:
        source = f"POSIX path of (choose file with prompt {applescript_string(prompt)})"
    return applescript(source)


def cocoa_choose(directory: bool, prompt: str) -> str:
    """Open the macOS file panel on the UI thread and keep its security scope."""
    from AppKit import NSOpenPanel
    from Foundation import NSOperationQueue

    box: dict = {}
    done = threading.Event()

    def show() -> None:
        try:
            panel = NSOpenPanel.openPanel()
            panel.setCanChooseFiles_(not directory)
            panel.setCanChooseDirectories_(directory)
            panel.setCanCreateDirectories_(directory)
            panel.setAllowsMultipleSelection_(False)
            panel.setMessage_(prompt)
            panel.setPrompt_("Choose")
            if int(panel.runModal()) != 1:
                box["path"] = ""
                return
            url = panel.URLs()[0]
            granted = bool(url.startAccessingSecurityScopedResource())
            log_line(f"scope granted={granted} {url.path()}")
            _SCOPES.append(url)
            box["path"] = str(url.path())
        except Exception as exc:
            box["error"] = exc
        finally:
            done.set()

    if threading.current_thread() is threading.main_thread():
        show()
    else:
        NSOperationQueue.mainQueue().addOperationWithBlock_(show)
        if not done.wait(timeout=300):
            raise SystemExit("The file dialog timed out.")
    if "error" in box:
        raise box["error"]
    return box.get("path", "")


def writable_desktop() -> str:
    desktop = Path.home() / "Desktop"
    probe = desktop / ".thats-not-my-name-write-test"
    try:
        probe.write_text("", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError:
        return ""
    return str(desktop)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} web UI")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    ensure_assets()
    UPLOADS.mkdir(parents=True, exist_ok=True)
    url = f"http://{args.host}:{args.port}/"
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    print(f"{APP_NAME}: {url}", flush=True)
    app.run(host=args.host, port=args.port, debug=False, threaded=True, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
