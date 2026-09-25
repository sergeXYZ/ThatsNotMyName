# That's Not My Name

Writes matrix input names for **DS100**, **DS100M** and **DS110** devices in a d&b `.dbpr` file, and sound objects in Create.Control `.dbcc` files.

The spreadsheet needs columns named **Input Number** and **Input Name** (any capitalization, so `INPUT NUMBER` and `input name` both work). `.csv`, `.xlsx`, and `.numbers` are accepted. The stored name is the number padded to 3 digits, a space, then the label (`001 KICK`, `012 Snare`, `128 Spare`). A blank Input Name stores just the padded number. Names longer than 31 characters are truncated to the DS100 channel-name limit.

Installers are on the [releases page](https://github.com/sergeXYZ/ThatsNotMyName/releases). The Mac disk image and the Windows setup already include Python. On Windows the setup also installs the Edge WebView2 runtime if it is missing.

Positioning-control labels and matrix-input groups that currently show the old name are updated with it.

## Web UI — That's Not My Name

```bash
.venv/bin/pip install -r requirements.txt
env -u PYTHONHOME -u PYTHONPATH .venv/bin/python3 web_ui.py
```

Opens http://127.0.0.1:8765/. Create.Control always replaces all existing objects. When the sheet needs more than 64 inputs, the device I/O size is switched to 128×64.

## CLI

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/python3 set_mtx_input_names.py names.xlsx project.dbpr -o project.named.dbpr
.venv/bin/python3 set_mtx_input_names.py names.numbers project.dbpr --dry-run
.venv/bin/python3 set_mtx_input_names.py names.csv project.dbpr --in-place
```

Create.Control (`.dbcc`) matches objects by the patching number. `--replace-existing` renames objects that are already in the file. `--add-new` adds numbers that are missing. `--numbered-objects named` skips a blank Input Name; `--numbered-objects all` keeps those rows and names them with the padded number only.

## Notes

**On macOS, a download from the browser is blocked with “Apple could not verify”. The app has no Apple Developer certificate. Open it once, then choose System Settings → Privacy & Security → Open Anyway. On Windows, SmartScreen shows a similar warning; choose Run anyway.**

Cell fills in Excel (`.xlsx`) and Numbers (`.numbers`) are mapped to the nearest Create.Control color, and in a `.dbpr` to the nearest R1 sound-object color on the positioning controls.

The fill can sit on **Input Name** or **Input Number**. Either column is enough. When the two cells in a row have different colors, the **Input Name** color is used. A cell with no fill does not block the color from the other column. Rows where neither cell has a fill are left unchanged.

```bash
.venv/bin/python3 set_mtx_input_names.py names.xlsx project.dbcc -o project.named.dbcc \
  --replace-existing --add-new --numbered-objects named
```
