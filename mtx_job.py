#!/usr/bin/env python3
"""Apply a spreadsheet to R1 and Create.Control copies. Used by the web UI."""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

from set_mtx_input_names import (
    MAX_NAME_LENGTH,
    PALETTE,
    PALETTE_NAMES,
    R1_PALETTE,
    R1_PALETTE_NAMES,
    apply_create_control,
    apply_sound_object_color,
    clear_create_control_objects,
    collapse_names,
    matrix_devices,
    nearest_palette,
    number_only,
    palette_index_for,
    plan_create_control,
    read_names,
)

POSITIONING_VIEW_TYPE = 1001


def copy_database(source: Path, dest: Path) -> None:
    if dest.resolve() == source.resolve():
        raise SystemExit(f"Output path is the same as the original: {source}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    source_conn = sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)
    dest_conn = sqlite3.connect(dest)
    try:
        source_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        source_conn.close()


def sibling_output(source: Path) -> Path:
    return source.with_name(f"{source.stem}.mtx{source.suffix}")


def resolve_output(source: Path, folder: str | None, filename: str | None) -> Path:
    if folder or filename:
        directory = Path(folder).expanduser() if folder else source.parent
        stem = (filename or "").strip()
        if not stem:
            stem = f"{source.stem}.mtx"
        stem = re.sub(r"[\\/]+", "-", stem)
        if stem.lower().endswith(source.suffix.lower()):
            return directory / stem
        return directory / f"{stem}{source.suffix}"
    return sibling_output(source)


def open_copy(source: Path, output: Path | None) -> tuple[Path, sqlite3.Connection]:
    dest = output if output is not None else sibling_output(source)
    copy_database(source, dest)
    connection = sqlite3.connect(dest)
    connection.row_factory = sqlite3.Row
    return dest, connection


def commit_copy(connection: sqlite3.Connection, dest: Path, work) -> object:
    connection.execute("BEGIN")
    try:
        result = work(connection)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise SystemExit(f"Integrity check failed: {integrity}")
        connection.execute("COMMIT")
    except BaseException:
        try:
            connection.rollback()
        except sqlite3.Error:
            pass
        connection.close()
        dest.unlink(missing_ok=True)
        raise
    connection.close()
    return result


def _stored(name: str, truncated: list[str]) -> str:
    if len(name) <= MAX_NAME_LENGTH:
        return name
    short = name[:MAX_NAME_LENGTH]
    truncated.append(f"{name} → {short}")
    return short


def inspect_sheet(path: Path) -> dict:
    names, colors = collapse_names(read_names(path, announce=False))
    named = sum(1 for name in names.values() if not number_only(name))
    colored = sum(1 for color in colors.values() if color)
    return {"count": len(names), "max": max(names) if names else 0, "named": named, "colored": colored}


def inspect_cc(path: Path) -> dict:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT DeviceName, IoSizeInputs, IoSizeOutputs, MainDevice FROM DeviceSettings ORDER BY DeviceId"
        ).fetchall()
    except sqlite3.Error as exc:
        raise SystemExit(f"Not a Create.Control file: {path.name} ({exc})") from exc
    finally:
        connection.close()
    if not rows:
        raise SystemExit(f"No devices in {path.name}")
    return {
        "devices": [
            {
                "name": row["DeviceName"],
                "inputs": row["IoSizeInputs"],
                "outputs": row["IoSizeOutputs"],
                "main": bool(row["MainDevice"]),
            }
            for row in rows
        ]
    }


def apply_r1(connection: sqlite3.Connection, names: dict[int, str], colors: dict[int, str | None], options: dict) -> list[str]:
    devices = matrix_devices(connection)
    if not devices:
        raise SystemExit("No DS100, DS100M or DS110 in this R1 file.")

    color_indexes: dict[int, int] = {}
    if options.get("colors"):
        warned: set[str] = set()
        for number, rgb in colors.items():
            if not rgb or rgb in warned:
                continue
            index = nearest_palette(rgb, R1_PALETTE)
            if index is None:
                warned.add(rgb)
                print(f"Note: fill #{rgb} has no close R1 color.", file=sys.stderr)
                continue
            color_indexes[number] = index

    lines = []
    truncated: list[str] = []
    for device in devices:
        device_id = device["DeviceId"]
        matrix_changed = 0
        positioning_changed = 0
        positioning_same = 0
        views: set[str] = set()
        colored: list[str] = []
        missing = 0
        for matrix_input, name in sorted(names.items()):
            stored = _stored(name, truncated)
            current = connection.execute(
                "SELECT Name FROM MatrixInputs WHERE DeviceId = ? AND MatrixInput = ?",
                (device_id, matrix_input),
            ).fetchone()
            if current is None:
                missing += 1
                continue
            if options.get("matrix") and (current["Name"] or "") != stored:
                connection.execute(
                    "UPDATE MatrixInputs SET Name = ? WHERE DeviceId = ? AND MatrixInput = ?",
                    (stored, device_id, matrix_input),
                )
                matrix_changed += 1
            if options.get("positioning"):
                rows = connection.execute(
                    """
                    SELECT c.DisplayName AS DisplayName, v.Name AS ViewName
                    FROM Controls c
                    JOIN Views v ON v.ViewId = c.ViewId
                    WHERE v.Type = ?
                      AND c.Type = 34
                      AND c.TargetType = 2
                      AND c.TargetId = ?
                      AND c.TargetChannel = ?
                      AND c.TargetProperty = 'Positioning_Source_Position'
                    """,
                    (POSITIONING_VIEW_TYPE, device_id, matrix_input),
                ).fetchall()
                for row in rows:
                    views.add(row["ViewName"] or "")
                    if (row["DisplayName"] or "") == stored:
                        positioning_same += 1
                    else:
                        positioning_changed += 1
                if rows:
                    connection.execute(
                        """
                        UPDATE Controls
                        SET DisplayName = ?
                        WHERE Type = 34
                          AND TargetType = 2
                          AND TargetId = ?
                          AND TargetChannel = ?
                          AND TargetProperty = 'Positioning_Source_Position'
                          AND ViewId IN (SELECT ViewId FROM Views WHERE Type = ?)
                        """,
                        (stored, device_id, matrix_input, POSITIONING_VIEW_TYPE),
                    )
            color = color_indexes.get(matrix_input)
            if color is not None and apply_sound_object_color(connection, device_id, matrix_input, color):
                colored.append(f"    {matrix_input:>3}  {stored}  {R1_PALETTE_NAMES[color]}")

        lines.append(f"{device['Model']} \"{device['Name']}\" ({device['InputCount']} inputs)")
        if options.get("matrix"):
            lines.append(f"  Matrix names written: {matrix_changed}")
        if options.get("positioning"):
            view_list = ", ".join(sorted(name for name in views if name)) or "none"
            lines.append(
                f"  Positioning objects: {positioning_changed} renamed, {positioning_same} already matching"
            )
            lines.append(f"  Views: {view_list}")
        if options.get("colors"):
            lines.append(f"  Object colors set: {len(colored)}")
            lines.extend(colored[:12])
            if not colored and colors:
                lines.append("  (no fills mapped to the R1 palette)")
        if missing:
            lines.append(f"  Spreadsheet inputs missing in the matrix: {missing}")
    if truncated:
        lines.append(f"Truncated to {MAX_NAME_LENGTH} characters: {len(truncated)}")
    return lines


def expand_inputs(connection: sqlite3.Connection) -> list[str]:
    """Set every device to the Create.Control XL pair: 128 inputs × 64 outputs.

    The device setup combo only accepts four pairs (64×16, 64×24, 64×64, 128×64).
    The first working write changed IoSizeInputs to 128 and left outputs alone.
    On a 64-output device that is already the XL pair. A 16- or 24-output device
    would become an illegal pair, which Create.Control reports as mismatched I/O,
    so outputs are set to 64 as well.
    """
    rows = connection.execute(
        "SELECT DeviceId, DeviceName, IoSizeInputs, IoSizeOutputs, Slot, MainDevice "
        "FROM DeviceSettings ORDER BY DeviceId"
    ).fetchall()
    if not rows:
        raise SystemExit("No devices in the Create.Control file.")
    lines = []
    for row in rows:
        current_in = int(row["IoSizeInputs"] or 0)
        current_out = int(row["IoSizeOutputs"] or 0)
        if current_in == 128 and current_out == 64:
            lines.append(
                f"  Device \"{row['DeviceName']}\" (slot {row['Slot']}): already 128×64 I/O."
            )
            continue
        connection.execute(
            "UPDATE DeviceSettings SET IoSizeInputs = 128, IoSizeOutputs = 64 WHERE DeviceId = ?",
            (row["DeviceId"],),
        )
        check = connection.execute(
            "SELECT IoSizeInputs, IoSizeOutputs FROM DeviceSettings WHERE DeviceId = ?",
            (row["DeviceId"],),
        ).fetchone()
        lines.append(
            f"  Device \"{row['DeviceName']}\" (slot {row['Slot']}): "
            f"{current_in}×{current_out} → {check['IoSizeInputs']}×{check['IoSizeOutputs']} I/O"
        )
    # Confirm at least one device is now 128×64.
    confirm = connection.execute(
        "SELECT COUNT(*) FROM DeviceSettings WHERE IoSizeInputs = 128 AND IoSizeOutputs = 64"
    ).fetchone()[0]
    if not confirm:
        raise SystemExit("Failed to set any Create.Control device to 128×64 I/O.")
    return lines


def apply_cc(
    connection: sqlite3.Connection,
    names: dict[int, str],
    colors: dict[int, str | None],
    options: dict,
) -> list[str]:
    # Every spreadsheet input becomes an object. A blank Input Name is stored as the padded number.
    use_colors = bool(options.get("colors"))
    replace = bool(options.get("replace"))
    number_only_count = sum(1 for name in names.values() if number_only(name))
    lines = []

    if replace:
        removed = clear_create_control_objects(connection)
        actions = []
        for number in sorted(names):
            if use_colors:
                color = palette_index_for(colors.get(number), PALETTE, "Create.Control")
            else:
                color = None
            actions.append(
                {
                    "action": "add",
                    "sound_object_id": None,
                    "patching": number,
                    "old": "",
                    "new": names[number],
                    "color": color,
                }
            )
        apply_create_control(connection, actions)
        lines.append(f"  Cleared existing objects: {removed}")
        lines.append(f"  Written from spreadsheet: {len(actions)}")
    elif use_colors:
        actions = plan_create_control(
            connection,
            names,
            {number: colors.get(number) if use_colors else None for number in names},
            replace_existing=False,
            add_new=False,
            recolor_existing=True,
        )
        apply_create_control(connection, actions)
        lines.append(f"  Colors changed: {sum(1 for action in actions if action['action'] == 'recolor')}")
    else:
        actions = []

    # Only when the Create.Control checkbox is on. A long sheet does not switch I/O by itself.
    if options.get("inputs128"):
        lines.extend(expand_inputs(connection))
    else:
        widest = connection.execute("SELECT MIN(IoSizeInputs) FROM DeviceSettings").fetchone()[0]
        if names and widest is not None and max(names) > int(widest):
            print(
                f"Note: input {max(names)} is above the device size {widest}.",
                file=sys.stderr,
            )

    if use_colors:
        colored = sum(
            1
            for action in actions
            if action.get("color") is not None and action["action"] in {"replace", "add", "recolor"}
        )
        lines.append(f"  Colors from spreadsheet: {colored}")
        preview = [action for action in actions if action["action"] in {"replace", "add", "recolor"}][:8]
        for action in preview:
            color = action.get("color")
            label_name = PALETTE_NAMES[color] if color is not None else "default"
            if action["action"] == "add":
                lines.append(f"    {action['patching']:>3}  {action['new']}  {label_name}")
            elif action["action"] == "recolor":
                lines.append(f"    {action['patching']:>3}  {action['old']}  {label_name}")
            else:
                lines.append(f"    {action['patching']:>3}  {action['old']} → {action['new']}  {label_name}")
    if number_only_count and replace:
        lines.append(f"  Objects named with the number only: {number_only_count}")
    return lines


def run_apply(job: dict) -> str:
    spreadsheet = Path(job["spreadsheet"])
    if not spreadsheet.is_file():
        raise SystemExit(f"Spreadsheet not found: {spreadsheet}")
    names, colors = collapse_names(read_names(spreadsheet, announce=False))
    filled = sum(1 for color in colors.values() if color)
    blocks = [
        f"Spreadsheet: {len(names)} inputs, "
        f"{sum(1 for name in names.values() if not number_only(name))} named, "
        f"{filled} colored cells"
    ]
    r1 = job.get("r1")
    cc = job.get("cc")
    if not r1 and not cc:
        raise SystemExit("No R1 or Create.Control file selected.")
    wants_color = bool((r1 and r1.get("colors")) or (cc and cc.get("colors")))
    if wants_color and filled == 0:
        blocks.insert(
            0,
            f"No cell colors in {spreadsheet.name}. "
            "Color the Input Name or Input Number cells. "
            "If both are colored, the Input Name color is used.",
        )

    if r1:
        if not any(r1.get(key) for key in ("matrix", "positioning", "colors")):
            raise SystemExit("No R1 option selected.")
        source = Path(r1["path"])
        if not source.is_file():
            raise SystemExit(f"R1 file not found: {source}")
        if r1.get("output"):
            output = Path(r1["output"])
        else:
            output = resolve_output(source, job.get("folder"), job.get("filename"))
        dest, connection = open_copy(source, output)
        lines = commit_copy(connection, dest, lambda conn: apply_r1(conn, names, colors, r1))
        blocks.append("")
        blocks.append(f"R1 output: {dest}")
        blocks.extend(lines)

    if cc:
        if not any(cc.get(key) for key in ("replace", "colors", "inputs128")):
            raise SystemExit("No Create.Control option selected.")
        source = Path(cc["path"])
        if not source.is_file():
            raise SystemExit(f"Create.Control file not found: {source}")
        if cc.get("output"):
            output = Path(cc["output"])
        else:
            output = resolve_output(source, job.get("folder"), job.get("filename"))
        dest, connection = open_copy(source, output)
        lines = commit_copy(connection, dest, lambda conn: apply_cc(conn, names, colors, cc))
        blocks.append("")
        blocks.append(f"Create.Control output: {dest}")
        blocks.extend(lines)

    blocks.append("")
    blocks.append("Originals were left unchanged.")
    return "\n".join(blocks)


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[1] == "--inspect-sheet":
        print(json.dumps(inspect_sheet(Path(argv[2]))))
        return 0
    if len(argv) >= 3 and argv[1] == "--inspect-cc":
        print(json.dumps(inspect_cc(Path(argv[2]))))
        return 0
    if len(argv) >= 3 and argv[1] == "--apply":
        job = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
        print(run_apply(job))
        return 0
    raise SystemExit("Usage: mtx_job.py --inspect-sheet FILE | --inspect-cc FILE | --apply JOB.json")


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            raise SystemExit(1) from None
        raise
