#!/bin/bash
# Build That's Not My Name.app with the web UI, yellow checkboxes, and the comic logo.
set -euo pipefail
cd "$(dirname "$0")/.."
unset PYTHONHOME PYTHONPATH PYTHONSTARTUP

PY=".venv/bin/python3"
if [[ ! -x "$PY" ]]; then
  echo "Missing $PY — create the venv and install requirements.txt first." >&2
  exit 1
fi

APP="dist/That's Not My Name.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/app/assets" "$APP/Contents/Resources/app/macos"

cp macos/Info.plist "$APP/Contents/Info.plist"
cp web_ui.py mtx_job.py set_mtx_input_names.py "$APP/Contents/Resources/app/"
cp macos/desktop.py "$APP/Contents/Resources/app/macos/desktop.py"
cp assets/logo-header.png assets/bg-rays.png assets/warning-dd.png assets/thats-not-my-name-bg.png \
  "$APP/Contents/Resources/app/assets/"

mkdir -p build
"$PY" -m pip install -q pillow
"$PY" scripts/build_icon.py

ICONSET="build/AppIcon.iconset"
rm -rf "$ICONSET"
mkdir -p "$ICONSET"
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" build/app-icon-1024.png --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z "$double" "$double" build/app-icon-1024.png --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns"

"$PY" -m venv "$APP/Contents/Resources/python"
APP_PY="$APP/Contents/Resources/python/bin/python3"
"$APP_PY" -m pip install -q -r requirements.txt 'pywebview==5.4'
# pywebview 5.4 on Python 3.9 pulls a WebKit backend via pyobjc.

clang -O2 -o "$APP/Contents/MacOS/That's Not My Name" macos/launcher.c
chmod +x "$APP/Contents/MacOS/That's Not My Name"
codesign --force --deep --sign - "$APP"

STAGE="build/dmg"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "That's Not My Name" -srcfolder "$STAGE" -ov -format UDZO \
  "dist/ThatsNotMyName-mac.dmg"
echo "App: $APP"
echo "Installer: dist/ThatsNotMyName-mac.dmg"
