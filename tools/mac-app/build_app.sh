#!/bin/bash
# Assemble Simvltanea.app: the Studio files staged by the repository, plus the Swift executable.
#   tools/mac-app/build_app.sh [output-dir]      (default: var/site/mac-app)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
out="${1:-$repo/var/site/mac-app}"
app="$out/Simvltanea.app"
rm -rf "$app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
(cd "$here" && swift build --build-system native -c release --product simvltanea-mac)
cp "$here/.build/release/simvltanea-mac" "$app/Contents/MacOS/simvltanea-mac"
cp "$here/app_info.plist" "$app/Contents/Info.plist"
(cd "$repo" && PYTHONPATH=src python3 -c "
import sys
from pathlib import Path
from simvltanea.browser import stage_studio
stage_studio(Path(sys.argv[1]))" "$app/Contents/Resources/studio")
# An ad-hoc signature is enough for a local build; Photos asks for permission on first import.
codesign --force --sign - "$app"
echo "$app"
