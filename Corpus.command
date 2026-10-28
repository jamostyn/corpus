#!/bin/bash
# Double-click this file (or run from Terminal) to launch Corpus.
#
# On first launch, uses the venv at Corpus/dev/.venv/. If it's missing
# or deps are stale, run:
#   cd Corpus/dev
#   python3 -m venv .venv
#   .venv/bin/pip install -r requirements.txt
#
# Corpus runs on its own: once it has started, this Terminal window
# closes itself (Jack, 2026-09-28: "it should close the terminal after
# corpus has been opened"). Quit Corpus by closing its window. Its console
# output goes to ~/.corpus/logs/launcher.out; the event log is still
# ~/.corpus/logs/server.log.
#
# If Corpus dies during startup, the window STAYS OPEN and shows the end
# of the output, so a failed launch is never silent.

set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo "No venv found. Creating one at .venv/ and installing deps…"
    python3 -m venv .venv
    .venv/bin/pip install -q -U pip
    .venv/bin/pip install -q -r requirements.txt
fi

mkdir -p "$HOME/.corpus/logs"
OUT="$HOME/.corpus/logs/launcher.out"
echo "---- $(date '+%Y-%m-%d %H:%M:%S') launch ----" >> "$OUT"

# Detached from this terminal entirely: `setsid` gives Corpus its own
# session with no controlling terminal. A process still attached to the
# window would make Terminal ask "terminate running processes?" on close
# — and answering yes would kill Corpus. (macOS ships no `setsid`
# command, so Python does it.)
DETACH='import os, sys; os.setsid(); os.execv(sys.argv[1], sys.argv[1:])'
.venv/bin/python3 -c "$DETACH" .venv/bin/python3 launcher.py < /dev/null >> "$OUT" 2>&1 &
PID=$!
disown

echo "Starting Corpus…"
sleep 3
if ! kill -0 "$PID" 2>/dev/null; then
    echo
    echo "Corpus stopped during startup. Last output:"
    echo
    tail -n 30 "$OUT"
    exit 1
fi

# Close THIS window a moment after the script exits, with no Terminal
# setting needed. Matched by terminal device, not title. The closer runs
# detached (own session) for the same reason Corpus does: nothing left
# attached to the window means Terminal has nothing to warn about. A
# failed launch exits 1 above and never reaches this, so its window stays.
CLOSE="tell application \"Terminal\" to close (every window whose tty of selected tab is \"$(tty)\")"
CLOSER='import os, sys, time, subprocess; os.setsid(); time.sleep(0.7); subprocess.run(["osascript", "-e", sys.argv[1]])'
.venv/bin/python3 -c "$CLOSER" "$CLOSE" < /dev/null > /dev/null 2>&1 &
disown
exit 0
