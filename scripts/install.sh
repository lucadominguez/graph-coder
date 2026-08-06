#!/usr/bin/env sh
set -eu
DRY_RUN=0
INSTALL_JCODE_VIEW=0
REMOVE_RETIRED=0
PROJECT_ROOT="$(pwd)"
DEST=".agents/skills"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SOURCE_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../skills" && pwd)

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --jcode-view) INSTALL_JCODE_VIEW=1 ;;
    --remove-retired) REMOVE_RETIRED=1 ;;
    --project-root) shift; PROJECT_ROOT="$1" ;;
    --dest) shift; DEST="$1" ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

case "$DEST" in
  # A drive-letter path is absolute under Git Bash; without this it was treated
  # as relative and the skills landed in a nested folder under the repository.
  /* | [A-Za-z]:/* | [A-Za-z]:\\*) DEST_ROOT="$DEST" ;;
  *) DEST_ROOT="$PROJECT_ROOT/$DEST" ;;
esac

mkdir_cmd() {
  if [ "$DRY_RUN" -eq 1 ]; then echo "DRY RUN mkdir -p $1"; else mkdir -p "$1"; fi
}

copy_skill() {
  src="$1"; dst="$2"
  [ -f "$src/SKILL.md" ] || { echo "invalid skill source: $src" >&2; exit 1; }
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "DRY RUN copy $src -> $dst"
  else
    mkdir -p "$dst"
    cp -R "$src"/. "$dst"/
  fi
}

# Skills this lifecycle replaced. Copying never removes them, so a destination
# that predates the rename keeps offering the old phase under the old name and
# a run can select it instead of its replacement.
report_retired() {
  root="$1"
  for pair in "aps-plan:graph-coder" "idea-grill:concept-grill"; do
    name=${pair%%:*}; replacement=${pair#*:}
    [ -f "$root/$name/SKILL.md" ] || continue
    if [ "$REMOVE_RETIRED" -eq 1 ]; then
      if [ "$DRY_RUN" -eq 1 ]; then
        echo "DRY RUN remove retired skill $root/$name"
      else
        rm -rf "$root/$name"
        echo "REMOVED retired skill $root/$name"
      fi
    else
      echo "WARNING: retired skill still installed: $root/$name. It shadows $replacement and a run can select it instead. Re-run with --remove-retired, or delete the directory." >&2
    fi
  done
}

mkdir_cmd "$DEST_ROOT"
for skill in graph-coder concept-grill technical-research plan-forge plan-rehearsal delegation-graph routing-plan execution-manager; do
  copy_skill "$SOURCE_ROOT/$skill" "$DEST_ROOT/$skill"
done
report_retired "$DEST_ROOT"
if [ "$INSTALL_JCODE_VIEW" -eq 1 ]; then
  JCODE_ROOT="$PROJECT_ROOT/.jcode/skills"
  mkdir_cmd "$JCODE_ROOT"
  for skill in graph-coder concept-grill technical-research plan-forge plan-rehearsal delegation-graph routing-plan execution-manager; do
    copy_skill "$SOURCE_ROOT/$skill" "$JCODE_ROOT/$skill"
  done
  report_retired "$JCODE_ROOT"
fi
echo "Graph Coder skills installed idempotently. No secrets read or written."
