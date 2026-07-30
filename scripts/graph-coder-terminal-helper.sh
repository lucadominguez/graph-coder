#!/usr/bin/env sh
set -eu
DRY_RUN=0
CMD="aps status --state .aps/state.json"
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1
if command -v wt.exe >/dev/null 2>&1; then
  if [ "$DRY_RUN" -eq 1 ]; then echo "DRY RUN wt.exe new-tab sh -lc '$CMD'"; else wt.exe new-tab sh -lc "$CMD"; fi
else
  echo "wt.exe not found; run manually: $CMD" >&2
fi
# No Komorebi dependency.
