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

# A venv only links to the Python on this Mac. Ship a real interpreter for both
# architectures so the app starts on machines that have no Python installed.
PBS_TAG="20260924"
PBS_VER="3.12.14"
fetch_python() {
  local triple="$1"
  local dest="$2"
  local name="cpython-${PBS_VER}+${PBS_TAG}-${triple}-install_only.tar.gz"
  local tar="build/python-standalone/${name}"
  local url="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/${name}"
  mkdir -p build/python-standalone
  if [[ ! -f "$tar" ]]; then
    curl -fL --retry 3 -o "$tar.partial" "$url"
    mv "$tar.partial" "$tar"
  fi
  local tmp
  tmp="$(mktemp -d)"
  tar -xzf "$tar" -C "$tmp"
  rm -rf "$dest"
  mv "$tmp/python" "$dest"
  rm -rf "$tmp"
}

install_deps() {
  local py="$1"
  shift
  "$@" "$py" -m pip install -q --upgrade pip
  "$@" "$py" -m pip install -q -r requirements.txt 'pywebview==5.4'
}

fetch_python "aarch64-apple-darwin" "$APP/Contents/Resources/python-arm64"
fetch_python "x86_64-apple-darwin" "$APP/Contents/Resources/python-x86_64"
install_deps "$APP/Contents/Resources/python-arm64/bin/python3"
install_deps "$APP/Contents/Resources/python-x86_64/bin/python3" arch -x86_64

clang -arch arm64 -arch x86_64 -O2 -o "$APP/Contents/MacOS/That's Not My Name" macos/launcher.c
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
