#!/usr/bin/env python3
"""Set DS100, DS100M and DS110 matrix input names in a d&b .dbpr file,
or rename sound objects in a Create.Control .dbcc file.

Reads .csv, .xlsx, and .numbers spreadsheets. The columns "Input Number" and
"Input Name" are matched in any capitalization. The stored name is the input
number padded to 3 digits, a space, then the input name (for example "001 KICK").
A blank input name stores just the padded number.

R1 copies that name onto positioning controls and input groups. Those copies
are updated in the same pass so views stay in step with MatrixInputs.

For a .dbcc file, objects are matched by their patching number. Existing
objects can be renamed and missing objects can be added. Rows with a number
but no input name can be included or skipped.

Fill colors are read from the Input Name cell and the Input Number cell, in
Excel and in Numbers. When those two cells have different fills, the Input
Name color is used.
"""

from __future__ import annotations

import argparse
import colorsys
import csv
import shutil
import sqlite3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MATRIX_MODELS = {"DS100", "DS100M", "DS110"}
# DS100 OSC /dbaudio1/matrixinput/channelname max length.
MAX_NAME_LENGTH = 31
NUMBER_HEADER = "input number"
NAME_HEADER = "input name"
# Default Create.Control sound-object palette, index 0–11.
# R1 sound-object colors, stored on Positioning_Source_Position controls.
R1_PALETTE = (
    (0xFA, 0xA0, 0x00),
    (0xFF, 0xC8, 0x00),
    (0xC8, 0xBE, 0x32),
    (0x96, 0x9B, 0x00),
    (0x73, 0x96, 0x46),
    (0x8C, 0xB4, 0x5A),
    (0xCD, 0xCD, 0x96),
    (0x9B, 0xCD, 0xCD),
    (0x50, 0xAA, 0xAA),
    (0x32, 0x9B, 0xCD),
    (0x00, 0x69, 0x9B),
    (0x7D, 0x7D, 0xF0),
    (0xB4, 0x0A, 0x28),
    (0xDC, 0x28, 0x28),
    (0xD2, 0x6E, 0x6E),
    (0xA5, 0x87, 0xA5),
    (0x7D, 0x7D, 0x7D),
    (0xBF, 0xBF, 0xBF),
)
R1_PALETTE_NAMES = (
    "orange",
    "yellow",
    "olive",
    "green-yellow",
    "green",
    "light-green",
    "khaki",
    "pale-cyan",
    "teal",
    "blue",
    "dark-blue",
    "purple",
    "dark-red",
    "red",
    "salmon",
    "mauve",
    "gray",
    "light-gray",
)
PALETTE = (
    (0xEB, 0x53, 0x53),
    (0xFB, 0x6F, 0x23),
    (0xF2, 0xAF, 0x33),
    (0x39, 0xA5, 0x49),
    (0x3C, 0x91, 0x83),
    (0x80, 0x94, 0x63),
    (0x33, 0x9D, 0xD2),
    (0x33, 0x78, 0xFB),
    (0x56, 0x56, 0xC9),
    (0xB2, 0x6F, 0xD4),
    (0xE0, 0x55, 0xB2),
    (0xAD, 0x95, 0x76),
)
PALETTE_NAMES = (
    "red",
    "orange",
    "yellow",
    "green",
    "teal",
    "olive",
    "sky",
    "blue",
    "indigo",
    "purple",
    "pink",
    "brown",
)
THEME_SLOTS = (
    "dk1",
    "lt1",
    "dk2",
    "lt2",
    "accent1",
    "accent2",
    "accent3",
    "accent4",
    "accent5",
    "accent6",
    "hlink",
    "folHlink",
)
DRAWING_NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}


def normalize_model(model: str) -> str:
    return "".join(model.split()).upper()


def cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        nearest = round(value)
        if abs(value - nearest) < 1e-4:
            return str(int(nearest))
        return str(value).strip()
    return str(value).strip()


def header_key(value) -> str:
    text = cell_text(value).casefold().replace("_", " ")
    return " ".join(text.split()).rstrip(":").strip()


def format_input_number(raw: str) -> str:
    """Pad 1-digit numbers with 00 and 2-digit numbers with 0."""
    text = raw.strip()
    try:
        number = int(text)
    except ValueError:
        number = float(text)
        nearest = round(number)
        if abs(number - nearest) >= 1e-4:
            raise ValueError(raw)
        number = int(nearest)
    if number < 1:
        raise ValueError(raw)
    digits = str(number)
    if len(digits) == 1:
        return "00" + digits
    if len(digits) == 2:
        return "0" + digits
    return digits


def nearest_palette(rgb: str, palette: tuple[tuple[int, int, int], ...] = PALETTE) -> int | None:
    """Map a fill to the nearest palette color. None when nothing is close.

    Saturated fills weight hue so orange stays orange instead of the closer olive.
    """
    red = int(rgb[0:2], 16)
    green = int(rgb[2:4], 16)
    blue = int(rgb[4:6], 16)
    if max(red, green, blue) < 30:
        return None
    hue, saturation, _value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
    best_index = 0
    best_distance = None
    for index, (palette_red, palette_green, palette_blue) in enumerate(palette):
        distance = (
            (red - palette_red) ** 2
            + (green - palette_green) ** 2
            + (blue - palette_blue) ** 2
        )
        palette_hue, palette_saturation, _ = colorsys.rgb_to_hsv(
            palette_red / 255, palette_green / 255, palette_blue / 255
        )
        if saturation > 0.35 and palette_saturation > 0.15:
            hue_delta = min(abs(hue - palette_hue), 1 - abs(hue - palette_hue))
            distance += (hue_delta * 600) ** 2
        if best_distance is None or distance < best_distance:
            best_index = index
            best_distance = distance
    if best_distance is None or best_distance > 220 ** 2:
        return None
    return best_index


def apply_excel_tint(rgb: str, tint: float) -> str:
    if not tint:
        return rgb
    red, green, blue = (int(rgb[index : index + 2], 16) / 255 for index in (0, 2, 4))
    hue, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
    if tint < 0:
        lightness = lightness * (1 + tint)
    else:
        lightness = lightness * (1 - tint) + tint
    red, green, blue = colorsys.hls_to_rgb(hue, max(0, min(1, lightness)), saturation)
    return f"{round(red * 255):02X}{round(green * 255):02X}{round(blue * 255):02X}"


def theme_colors(workbook) -> list[str]:
    theme = workbook.loaded_theme
    if not theme:
        return ["000000"] * len(THEME_SLOTS)
    root = ET.fromstring(theme)
    scheme = root.find(".//a:clrScheme", DRAWING_NS)
    colors = []
    for slot in THEME_SLOTS:
        element = scheme.find(f"a:{slot}", DRAWING_NS) if scheme is not None else None
        if element is None:
            colors.append("000000")
            continue
        rgb = element.find("a:srgbClr", DRAWING_NS)
        if rgb is not None and rgb.get("val"):
            colors.append(rgb.get("val"))
            continue
        system = element.find("a:sysClr", DRAWING_NS)
        colors.append((system.get("lastClr") if system is not None else None) or "000000")
    return colors


def cell_fill_rgb(cell, themes: list[str]) -> str | None:
    fill = cell.fill
    if fill is None or not fill.patternType or fill.patternType == "none":
        return None
    color = fill.fgColor
    if color is None or not color.type:
        return None
    if color.type == "rgb":
        raw = str(color.rgb or "")
        if len(raw) == 8 and raw[:2] == "00":
            return None
        rgb = raw[-6:]
        if len(rgb) != 6 or rgb == "000000" and raw in {"", "00000000"}:
            return None
        return rgb
    if color.type == "theme" and color.theme is not None and color.theme < len(themes):
        return apply_excel_tint(themes[color.theme], color.tint or 0)
    return None


def prefer_fill(name_rgb: str | None, number_rgb: str | None) -> str | None:
    """Use the Input Name fill when both cells are colored."""
    return name_rgb or number_rgb


def xlsx_row_colors(
    path: Path,
    sheet_name: str,
    number_col: int,
    name_col: int,
    header_index: int,
) -> dict[int, str]:
    import openpyxl

    workbook = openpyxl.load_workbook(path, data_only=False)
    try:
        worksheet = workbook[sheet_name]
        themes = theme_colors(workbook)
        colors: dict[int, str] = {}
        for row_number, row in enumerate(
            worksheet.iter_rows(min_row=header_index + 2),
            start=header_index + 2,
        ):
            number_rgb = cell_fill_rgb(row[number_col], themes) if number_col < len(row) else None
            name_rgb = cell_fill_rgb(row[name_col], themes) if name_col < len(row) else None
            rgb = prefer_fill(name_rgb, number_rgb)
            if rgb:
                colors[row_number] = rgb
        return colors
    finally:
        workbook.close()


def numbers_fill_rgb(cell) -> str | None:
    style = getattr(cell, "style", None)
    color = getattr(style, "bg_color", None) if style is not None else None
    if isinstance(color, list):
        color = color[0] if color else None
    if color is None:
        return None
    red, green, blue = int(color.r), int(color.g), int(color.b)
    if (red, green, blue) == (255, 255, 255):
        return None
    return f"{red:02X}{green:02X}{blue:02X}"


def numbers_row_colors(
    path: Path,
    sheet_label: str,
    number_col: int,
    name_col: int,
    header_index: int,
) -> dict[int, str]:
    from numbers_parser import Document

    document = Document(str(path))
    table = None
    for sheet in document.sheets:
        for candidate in sheet.tables:
            if f"{sheet.name} / {candidate.name}" == sheet_label:
                table = candidate
                break
        if table is not None:
            break
    if table is None:
        return {}
    colors: dict[int, str] = {}
    for row in range(header_index + 1, table.num_rows):
        number_rgb = numbers_fill_rgb(table.cell(row, number_col)) if number_col < table.num_cols else None
        name_rgb = numbers_fill_rgb(table.cell(row, name_col)) if name_col < table.num_cols else None
        rgb = prefer_fill(name_rgb, number_rgb)
        if rgb:
            colors[row + 1] = rgb
    return colors


def build_name(number_text: str, name_text: str) -> tuple[int, str]:
    padded = format_input_number(number_text)
    label = name_text.strip()
    if label:
        return int(padded), f"{padded} {label}"
    return int(padded), padded


def find_header(rows: list[list]) -> tuple[int, int, int] | None:
    for index, row in enumerate(rows):
        keys = [header_key(cell) for cell in row]
        try:
            number_col = keys.index(NUMBER_HEADER)
            name_col = keys.index(NAME_HEADER)
        except ValueError:
            continue
        return index, number_col, name_col
    return None


def read_csv_rows(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [row for row in csv.reader(handle)]


def read_xlsx_tables(path: Path) -> list[tuple[str, list[list]]]:
    try:
        import openpyxl
    except ImportError as exc:
        raise SystemExit(
            "Reading .xlsx needs openpyxl. Install with: .venv/bin/pip install -r requirements.txt"
        ) from exc
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        return [
            (sheet.title, [list(row) for row in sheet.iter_rows(values_only=True)])
            for sheet in workbook.worksheets
        ]
    finally:
        workbook.close()


def read_numbers_tables(path: Path) -> list[tuple[str, list[list]]]:
    try:
        from numbers_parser import Document
    except ImportError as exc:
        raise SystemExit(
            "Reading .numbers needs numbers-parser. Install with: .venv/bin/pip install -r requirements.txt"
        ) from exc
    document = Document(str(path))
    tables = []
    for sheet in document.sheets:
        for table in sheet.tables:
            rows = [
                [table.cell(row, column).value for column in range(table.num_cols)]
                for row in range(table.num_rows)
            ]
            tables.append((f"{sheet.name} / {table.name}", rows))
    return tables


def load_tables(path: Path) -> list[tuple[str, list[list]]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return [("CSV", read_csv_rows(path))]
    if suffix in {".xlsx", ".xlsm"}:
        return read_xlsx_tables(path)
    if suffix == ".numbers":
        return read_numbers_tables(path)
    raise SystemExit(f"Unsupported spreadsheet {path.name}. Use .csv, .xlsx, or .numbers.")


def read_names(path: Path, announce: bool = True) -> list[tuple[int, str, int, str | None]]:
    """Return (matrix_input, name, row_number, fill rgb) in file order. Later rows win."""
    tables = load_tables(path)
    chosen = None
    for sheet_name, rows in tables:
        located = find_header(rows)
        if located is not None:
            chosen = (sheet_name, rows, located)
            break
    if chosen is None:
        seen = []
        for sheet_name, rows in tables:
            for row in rows[:8]:
                labels = [cell_text(cell) for cell in row if cell_text(cell)]
                if labels:
                    seen.append(f"  {sheet_name}: {', '.join(labels)}")
                    break
        detail = "\n".join(seen) if seen else "  (no header cells found)"
        raise SystemExit(
            'Could not find columns "Input Number" and "Input Name" (any capitalization).\n'
            f"Headers seen:\n{detail}"
        )

    sheet_name, rows, (header_index, number_col, name_col) = chosen
    if announce:
        print(f'Using "{sheet_name}" — Input Number column {number_col + 1}, Input Name column {name_col + 1}.')
    row_colors: dict[int, str] = {}
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        row_colors = xlsx_row_colors(path, sheet_name, number_col, name_col, header_index)
    elif suffix == ".numbers":
        row_colors = numbers_row_colors(path, sheet_name, number_col, name_col, header_index)
    entries: list[tuple[int, str, int, str | None]] = []
    for row_number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        number_raw = cell_text(row[number_col]) if number_col < len(row) else ""
        name_raw = cell_text(row[name_col]) if name_col < len(row) else ""
        if not number_raw:
            continue
        try:
            matrix_input, name = build_name(number_raw, name_raw)
        except ValueError:
            raise SystemExit(
                f"{path.name} {sheet_name} row {row_number}: invalid input number {number_raw!r}"
            ) from None
        entries.append((matrix_input, name, row_number, row_colors.get(row_number)))
    if not entries:
        raise SystemExit(f"No input rows found in {path}")
    return entries


def matrix_devices(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    rows = connection.execute(
        """
        SELECT d.DeviceId, d.Model, d.Name, dm.InputCount
        FROM Devices d
        JOIN DevicesMatrix dm ON dm.DeviceId = d.DeviceId
        ORDER BY d.DeviceId
        """
    ).fetchall()
    return [row for row in rows if normalize_model(row["Model"] or "") in MATRIX_MODELS]


def palette_index_for(rgb: str | None, palette: tuple[tuple[int, int, int], ...], label: str) -> int | None:
    if not rgb:
        return None
    index = nearest_palette(rgb, palette)
    if index is None:
        print(f"Warning: fill #{rgb} has no close {label} color.", file=sys.stderr)
    return index


def apply_sound_object_color(
    connection: sqlite3.Connection,
    device_id: int,
    matrix_input: int,
    color: int,
) -> int:
    cursor = connection.execute(
        """
        UPDATE Controls
        SET MainColor = ?, SubColor = ?
        WHERE TargetType = 2
          AND TargetId = ?
          AND TargetChannel = ?
          AND TargetProperty = 'Positioning_Source_Position'
          AND Type = 34
        """,
        (color, color, device_id, matrix_input),
    )
    return cursor.rowcount


def apply_names(
    connection: sqlite3.Connection,
    names: dict[int, str],
    colors: dict[int, str | None] | None = None,
) -> dict:
    devices = matrix_devices(connection)
    if not devices:
        raise SystemExit("No DS100, DS100M or DS110 matrix device in this project.")

    report = {
        "devices": [],
        "truncated": [],
        "missing": [],
        "changed": 0,
        "unchanged": 0,
        "number_only": sum(1 for name in names.values() if name.isdigit()),
        "colors": [],
    }
    color_indexes: dict[int, int] = {}
    warned: set[str] = set()
    for number, rgb in (colors or {}).items():
        if not rgb or rgb in warned:
            continue
        index = nearest_palette(rgb, R1_PALETTE)
        if index is None:
            warned.add(rgb)
            print(f"Warning: fill #{rgb} has no close R1 color.", file=sys.stderr)
            continue
        color_indexes[number] = index

    for device in devices:
        device_id = device["DeviceId"]
        device_changes = 0
        for matrix_input, name in names.items():
            stored = name
            if len(stored) > MAX_NAME_LENGTH:
                report["truncated"].append(
                    (device["Name"], matrix_input, stored, stored[:MAX_NAME_LENGTH])
                )
                stored = stored[:MAX_NAME_LENGTH]

            current = connection.execute(
                "SELECT Name FROM MatrixInputs WHERE DeviceId = ? AND MatrixInput = ?",
                (device_id, matrix_input),
            ).fetchone()
            if current is None:
                report["missing"].append((device["Name"], matrix_input))
                continue

            old = current["Name"] or ""
            if old == stored:
                report["unchanged"] += 1
            else:
                connection.execute(
                    "UPDATE MatrixInputs SET Name = ? WHERE DeviceId = ? AND MatrixInput = ?",
                    (stored, device_id, matrix_input),
                )
                _sync_controls(connection, device_id, matrix_input, old, stored)
                _sync_groups(connection, device_id, matrix_input, old, stored)
                report["changed"] += 1
                device_changes += 1

            color = color_indexes.get(matrix_input)
            if color is not None and apply_sound_object_color(connection, device_id, matrix_input, color):
                report["colors"].append((matrix_input, stored, R1_PALETTE_NAMES[color]))

        report["devices"].append(
            {
                "id": device_id,
                "model": device["Model"],
                "name": device["Name"],
                "inputs": device["InputCount"],
                "changed": device_changes,
            }
        )
    return report


def _sync_controls(
    connection: sqlite3.Connection,
    device_id: int,
    matrix_input: int,
    old: str,
    new: str,
) -> None:
    """R1 positioning controls display the matrix input name."""
    targets = []
    if old:
        targets.append(old)
    else:
        targets.append(f"Input {matrix_input}")
    display = new if new else f"Input {matrix_input}"
    for previous in targets:
        connection.execute(
            """
            UPDATE Controls
            SET DisplayName = ?
            WHERE TargetType = 2
              AND TargetId = ?
              AND TargetChannel = ?
              AND DisplayName = ?
            """,
            (display, device_id, matrix_input, previous),
        )


def _sync_groups(
    connection: sqlite3.Connection,
    device_id: int,
    matrix_input: int,
    old: str,
    new: str,
) -> None:
    """Type 2 groups are the matrix inputs inside R1 views."""
    if old:
        if new:
            connection.execute(
                """
                UPDATE Groups SET Name = ?
                WHERE Type = 2 AND TargetId = ? AND TargetChannel = ? AND Name = ?
                """,
                (new, device_id, matrix_input, old),
            )
        else:
            connection.execute(
                """
                UPDATE Groups SET Name = NULL
                WHERE Type = 2 AND TargetId = ? AND TargetChannel = ? AND Name = ?
                """,
                (device_id, matrix_input, old),
            )
        return
    if new:
        connection.execute(
            """
            UPDATE Groups SET Name = ?
            WHERE Type = 2 AND TargetId = ? AND TargetChannel = ? AND Name IS NULL
            """,
            (new, device_id, matrix_input),
        )


def collapse_names(
    entries: list[tuple[int, str, int, str | None]],
) -> tuple[dict[int, str], dict[int, str | None]]:
    names: dict[int, str] = {}
    colors: dict[int, str | None] = {}
    seen: dict[int, int] = {}
    for matrix_input, name, row_number, color in entries:
        if matrix_input in seen:
            print(
                f"Warning: input {matrix_input} repeated on rows {seen[matrix_input]} and {row_number}; using row {row_number}.",
                file=sys.stderr,
            )
        seen[matrix_input] = row_number
        names[matrix_input] = name
        colors[matrix_input] = color
    return names, colors


def print_report(report: dict, preview: list[tuple[int, str, str]]) -> None:
    print("Devices:")
    for device in report["devices"]:
        print(
            f"  {device['model']} \"{device['name']}\" (id {device['id']}, {device['inputs']} inputs) — {device['changed']} names written"
        )
    print(f"Changed: {report['changed']}")
    print(f"Already matching: {report['unchanged']}")
    print(f"Input Name empty (name is the padded number only): {report['number_only']}")
    if report["missing"]:
        print(f"Spreadsheet inputs with no matrix channel: {len(report['missing'])}")
        for device_name, matrix_input in report["missing"][:20]:
            print(f"  {device_name} input {matrix_input}")
    if report.get("colors"):
        print(f"Sound object colors written: {len(report['colors'])}")
        for matrix_input, name, color_name in report["colors"][:12]:
            print(f"  {matrix_input:>3}  {name}  {color_name}")
    if report["truncated"]:
        print(f"Truncated to {MAX_NAME_LENGTH} characters: {len(report['truncated'])}")
        for device_name, matrix_input, full, short in report["truncated"]:
            print(f"  {device_name} input {matrix_input}: {full!r} -> {short!r}")
    if preview:
        print("Preview:")
        for matrix_input, old, new in preview:
            print(f"  {matrix_input:>3}  {old!r}  ->  {new!r}")


def preview_changes(
    connection: sqlite3.Connection,
    names: dict[int, str],
    limit: int = 12,
) -> list[tuple[int, str, str]]:
    devices = matrix_devices(connection)
    if not devices:
        return []
    device_id = devices[0]["DeviceId"]
    preview = []
    for matrix_input in sorted(names):
        current = connection.execute(
            "SELECT Name FROM MatrixInputs WHERE DeviceId = ? AND MatrixInput = ?",
            (device_id, matrix_input),
        ).fetchone()
        if current is None:
            continue
        old = current["Name"] or ""
        new = names[matrix_input][:MAX_NAME_LENGTH]
        if old != new:
            preview.append((matrix_input, old, new))
        if len(preview) >= limit:
            break
    return preview


def number_only(name: str) -> bool:
    return name.isdigit()


def names_for_objects(
    names: dict[int, str],
    colors: dict[int, str | None],
    numbered_objects: str,
) -> tuple[dict[int, str], dict[int, str | None]]:
    if numbered_objects == "all":
        return names, colors
    kept = {number: name for number, name in names.items() if not number_only(name)}
    return kept, {number: colors.get(number) for number in kept}


def plan_create_control(
    connection: sqlite3.Connection,
    names: dict[int, str],
    colors: dict[int, str | None],
    replace_existing: bool,
    add_new: bool,
    recolor_existing: bool = False,
) -> list[dict]:
    rows = connection.execute(
        "SELECT SoundObjectId, Name, Patching, Color FROM SoundObjects"
    ).fetchall()
    by_patch: dict[int, list[sqlite3.Row]] = {}
    for row in rows:
        if row["Patching"] is None:
            continue
        by_patch.setdefault(row["Patching"], []).append(row)

    actions = []
    for number in sorted(names):
        name = names[number]
        color = palette_index_for(colors.get(number), PALETTE, "Create.Control")
        matches = by_patch.get(number, [])
        if matches and replace_existing:
            for match in matches:
                old = match["Name"] or ""
                color_changes = color is not None and color != match["Color"]
                actions.append(
                    {
                        "action": "unchanged" if old == name and not color_changes else "replace",
                        "sound_object_id": match["SoundObjectId"],
                        "patching": number,
                        "old": old,
                        "new": name,
                        "color": color,
                    }
                )
        elif matches and recolor_existing:
            for match in matches:
                color_changes = color is not None and color != match["Color"]
                actions.append(
                    {
                        "action": "recolor" if color_changes else "unchanged",
                        "sound_object_id": match["SoundObjectId"],
                        "patching": number,
                        "old": match["Name"] or "",
                        "new": name,
                        "color": color,
                    }
                )
        elif matches:
            actions.append(
                {
                    "action": "kept",
                    "sound_object_id": matches[0]["SoundObjectId"],
                    "patching": number,
                    "old": matches[0]["Name"] or "",
                    "new": name,
                    "color": color,
                }
            )
        elif add_new:
            actions.append(
                {
                    "action": "add",
                    "sound_object_id": None,
                    "patching": number,
                    "old": "",
                    "new": name,
                    "color": color,
                }
            )
        else:
            actions.append(
                {
                    "action": "skipped",
                    "sound_object_id": None,
                    "patching": number,
                    "old": "",
                    "new": name,
                    "color": color,
                }
            )
    return actions


def clear_create_control_objects(connection: sqlite3.Connection) -> int:
    """Remove every sound object and the rows that point at them."""
    count = connection.execute("SELECT COUNT(*) FROM SoundObjects").fetchone()[0]
    connection.execute("DELETE FROM AnimationSoundObjects")
    connection.execute("DELETE FROM SnapshotSoundObjectParameters")
    connection.execute("DELETE FROM GroupPatching")
    connection.execute("DELETE FROM SoundObjects")
    return count


def apply_create_control(connection: sqlite3.Connection, actions: list[dict]) -> None:
    next_object_id = connection.execute(
        "SELECT COALESCE(MAX(SoundObjectId), -1) + 1 FROM SoundObjects"
    ).fetchone()[0]
    next_parameter_id = connection.execute(
        "SELECT COALESCE(MAX(SnapshotSoundObjectParameterId), -1) + 1 FROM SnapshotSoundObjectParameters"
    ).fetchone()[0]
    snapshots = [
        row[0]
        for row in connection.execute("SELECT SnapshotId FROM Snapshots ORDER BY SnapshotId")
    ]

    for action in actions:
        if action["action"] == "replace":
            if action["color"] is None:
                connection.execute(
                    "UPDATE SoundObjects SET Name = ? WHERE SoundObjectId = ?",
                    (action["new"], action["sound_object_id"]),
                )
            else:
                connection.execute(
                    "UPDATE SoundObjects SET Name = ?, Color = ? WHERE SoundObjectId = ?",
                    (action["new"], action["color"], action["sound_object_id"]),
                )
        elif action["action"] == "recolor":
            connection.execute(
                "UPDATE SoundObjects SET Color = ? WHERE SoundObjectId = ?",
                (action["color"], action["sound_object_id"]),
            )
        elif action["action"] == "add":
            connection.execute(
                """
                INSERT INTO SoundObjects
                    (SoundObjectId, Name, Patching, Color, Patching2, Patching3, Patching4)
                VALUES (?, ?, ?, ?, NULL, NULL, NULL)
                """,
                (next_object_id, action["new"], action["patching"], action["color"] if action["color"] is not None else 0),
            )
            for snapshot_id in snapshots:
                connection.execute(
                    """
                    INSERT INTO SnapshotSoundObjectParameters (
                        SnapshotSoundObjectParameterId, SoundObjectId, SnapshotId,
                        Mute, Level, EnSpace, CoordinateX, CoordinateY, CoordinateZ,
                        Spread, DelayMode, MuteRecall, LevelRecall, EnSpaceRecall,
                        CoordinateRecall, SpreadRecall, DelayModeRecall, AnimationRecall
                    ) VALUES (?, ?, ?, 0, 0.0, -120.0, 0.0, 0.0, 0.0, 0.5, 2, 1, 1, 1, 1, 1, 1, 1)
                    """,
                    (next_parameter_id, next_object_id, snapshot_id),
                )
                next_parameter_id += 1
            action["sound_object_id"] = next_object_id
            next_object_id += 1


def print_create_control_report(actions: list[dict], skipped_unnamed: int, numbered_objects: str) -> None:
    counts: dict[str, int] = {}
    for action in actions:
        counts[action["action"]] = counts.get(action["action"], 0) + 1
    print(f"Numbered objects without a name: {numbered_objects}")
    print(f"Replaced: {counts.get('replace', 0)}")
    print(f"Added: {counts.get('add', 0)}")
    print(f"Already matching: {counts.get('unchanged', 0)}")
    print(f"Left unchanged (replace not selected): {counts.get('kept', 0)}")
    print(f"Not added (add not selected): {counts.get('skipped', 0)}")
    colored = sum(1 for action in actions if action.get("color") is not None and action["action"] in {"replace", "add"})
    print(f"Skipped because Input Name is empty: {skipped_unnamed}")
    print(f"Colors taken from the spreadsheet: {colored}")
    preview = [action for action in actions if action["action"] in {"replace", "add"}][:12]
    if preview:
        print("Preview:")
        for action in preview:
            color = action.get("color")
            color_label = PALETTE_NAMES[color] if color is not None else "default"
            if action["action"] == "replace":
                print(f"  {action['patching']:>3}  {action['old']!r}  ->  {action['new']!r}  {color_label}")
            else:
                print(f"  {action['patching']:>3}  add  {action['new']!r}  {color_label}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "spreadsheet",
        type=Path,
        help='CSV, XLSX, or Numbers file with columns "Input Number" and "Input Name".',
    )
    parser.add_argument("project", type=Path, help="d&b .dbpr project or Create.Control .dbcc file.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write a copy here. Omit only together with --in-place.",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Modify the project file itself.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the changes and leave every file untouched.",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Create.Control: rename sound objects whose patching number is in the spreadsheet.",
    )
    parser.add_argument(
        "--add-new",
        action="store_true",
        help="Create.Control: add sound objects for spreadsheet numbers that are not in the file yet.",
    )
    parser.add_argument(
        "--numbered-objects",
        choices=("all", "named"),
        default="named",
        help="Create.Control: all = also objects that only have a number; named = skip an empty Input Name. Default: named.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if not args.spreadsheet.exists():
        raise SystemExit(f"Spreadsheet not found: {args.spreadsheet}")
    if not args.project.is_file():
        raise SystemExit(f"Project not found: {args.project}")
    if args.in_place and args.output:
        raise SystemExit("Use either --output or --in-place, not both.")
    if not args.in_place and not args.output and not args.dry_run:
        raise SystemExit("Pass --output for a copy, or --in-place to modify the project.")

    names, colors = collapse_names(read_names(args.spreadsheet))
    source = args.project.resolve()
    kind = source.suffix.lower()
    if kind == ".dbcc":
        return _run_create_control(args, names, colors, source)
    if kind != ".dbpr":
        raise SystemExit(f"Unsupported project {source.name}. Use .dbpr or .dbcc.")
    if args.replace_existing or args.add_new:
        raise SystemExit("--replace-existing and --add-new are for a Create.Control .dbcc file.")

    if args.dry_run:
        connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            preview = preview_changes(connection, names)
            # Count against the live file without writing.
            devices = matrix_devices(connection)
            if not devices:
                raise SystemExit("No DS100, DS100M or DS110 matrix device in this project.")
            print(f"Dry run: {len(names)} names, {len(devices)} matrix device(s). No file written.")
            print_report(
                {
                    "devices": [
                        {
                            "id": device["DeviceId"],
                            "model": device["Model"],
                            "name": device["Name"],
                            "inputs": device["InputCount"],
                            "changed": "n/a",
                        }
                        for device in devices
                    ],
                    "truncated": [
                        (devices[0]["Name"], number, name, name[:MAX_NAME_LENGTH])
                        for number, name in names.items()
                        if len(name) > MAX_NAME_LENGTH
                    ],
                    "missing": [],
                    "changed": sum(
                        1
                        for number, name in names.items()
                        if _would_change(connection, devices[0]["DeviceId"], number, name)
                    ),
                    "unchanged": 0,
                    "number_only": sum(1 for name in names.values() if name.isdigit()),
                },
                preview,
            )
        finally:
            connection.close()
        return 0

    if args.in_place:
        target = source
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, args.output)
        target = args.output.resolve()

    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    try:
        preview = preview_changes(connection, names)
        connection.execute("BEGIN")
        report = apply_names(connection, names, colors)
        connection.execute("COMMIT")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise SystemExit(f"Integrity check failed: {integrity}")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    print(f"Wrote {target}")
    print_report(report, preview)
    return 0


def _run_create_control(
    args: argparse.Namespace,
    names: dict[int, str],
    colors: dict[int, str | None],
    source: Path,
) -> int:
    if not args.replace_existing and not args.add_new:
        raise SystemExit("For a Create.Control file pass --replace-existing, --add-new, or both.")
    selected, selected_colors = names_for_objects(names, colors, args.numbered_objects)
    skipped_unnamed = len(names) - len(selected)

    if args.dry_run:
        connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            actions = plan_create_control(
                connection, selected, selected_colors, args.replace_existing, args.add_new
            )
        finally:
            connection.close()
        print(f"Dry run: {source.name}. No file written.")
        print_create_control_report(actions, skipped_unnamed, args.numbered_objects)
        return 0

    if args.in_place:
        target = source
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, args.output)
        target = args.output.resolve()

    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN")
        actions = plan_create_control(
            connection, selected, selected_colors, args.replace_existing, args.add_new
        )
        apply_create_control(connection, actions)
        connection.execute("COMMIT")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise SystemExit(f"Integrity check failed: {integrity}")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    print(f"Wrote {target}")
    print_create_control_report(actions, skipped_unnamed, args.numbered_objects)
    return 0


def _would_change(connection: sqlite3.Connection, device_id: int, matrix_input: int, name: str) -> bool:
    current = connection.execute(
        "SELECT Name FROM MatrixInputs WHERE DeviceId = ? AND MatrixInput = ?",
        (device_id, matrix_input),
    ).fetchone()
    if current is None:
        return False
    return (current["Name"] or "") != name[:MAX_NAME_LENGTH]


if __name__ == "__main__":
    raise SystemExit(main())
