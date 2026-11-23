#!/bin/bash
# Run the Freerouting autorouter without its window, stopping after a set number of passes.
#   tools/freerouting_capped.sh PASSES in.dsn out.ses
# Freerouting 2.1.0 without its window ignores -mp and always runs 999 passes, saving only at the end
# (its pass limit is a fixed 999 in RouterSettings; only the window ever changes it). This puts a copy of
# that one class, with 999 replaced by PASSES, ahead of the jar on the class path. The jar is not changed.
set -e
PASSES=$1; IN=$2; OUT=$3
JAR=~/.kicad-mcp/freerouting.jar
P="$(cd "$(dirname "$0")/.." && pwd)/build/freerouting_patch"
C=app/freerouting/settings/RouterSettings.class
rm -rf "$P"; mkdir -p "$P"
(cd "$P" && unzip -q -o "$JAR" "$C")
python3 - "$P/$C" "$PASSES" <<'PY'
import sys
path, n = sys.argv[1], int(sys.argv[2])
assert 1 <= n <= 32767
b = open(path, 'rb').read()
old = bytes([0x11, 0x03, 0xE7, 0xB5])          # sipush 999; putfield
k = b.count(old)
assert k == 1, 'expected one "999" pass limit in RouterSettings, found %d: a different Freerouting version?' % k
b = b.replace(old, bytes([0x11, n >> 8, n & 255, 0xB5]))
open(path, 'wb').write(b)
PY
# Its settings file lives in the temporary folder and is lost at a restart; without it Freerouting
# starts with usage reporting on. Write one with reporting off if it is missing.
F="${TMPDIR:-/tmp}/freerouting/freerouting.json"
if [ ! -f "$F" ]; then
    mkdir -p "$(dirname "$F")"
    cat > "$F" <<'JSON'
{
  "profile": {"email": "", "allow_telemetry": false, "allow_contact": false},
  "gui": {"enabled": false},
  "usage_and_diagnostic_data": {"disable_analytics": true}
}
JSON
fi
exec java -cp "$P:$JAR" app.freerouting.Freerouting --gui.enabled=false \
    --usage_and_diagnostic_data.disable_analytics=true --profile.allow_telemetry=false \
    -de "$IN" -do "$OUT" -mt 1
