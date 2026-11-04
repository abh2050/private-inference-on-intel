#!/usr/bin/env bash
# Reads lines on stdin and appends them, UTC-timestamped, to the file given as $1.
# Used by `tmux pipe-pane`, which would otherwise expand the % signs in an inline date format.
while IFS= read -r l; do printf '%s %s\n' "$(date -u +%FT%TZ)" "$l"; done >> "$1"
