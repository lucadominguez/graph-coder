#!/usr/bin/env sh
set -eu
DRY_RUN=0
INSTALL_JCODE_VIEW=0
PROJECT_ROOT="$(pwd)"
DEST=".agents/skills"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SOURCE_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../skills" && pwd)

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --jcode-view) INSTALL_JCODE_VIEW=1 ;;
    --project-root) shift; PROJECT_ROOT="$1" ;;
    --dest) shift; DEST="$1" ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

case "$DEST" in
  /*) DEST_ROOT="$DEST" ;;
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

mkdir_cmd "$DEST_ROOT"
for skill in graph-coder concept-grill technical-research plan-forge plan-rehearsal delegation-graph routing-plan execution-manager; do
  copy_skill "$SOURCE_ROOT/$skill" "$DEST_ROOT/$skill"
done
if [ "$INSTALL_JCODE_VIEW" -eq 1 ]; then
  JCODE_ROOT="$PROJECT_ROOT/.jcode/skills"
  mkdir_cmd "$JCODE_ROOT"
  for skill in graph-coder concept-grill technical-research plan-forge plan-rehearsal delegation-graph routing-plan execution-manager; do
    copy_skill "$SOURCE_ROOT/$skill" "$JCODE_ROOT/$skill"
  done
fi
echo "Graph Coder skills installed idempotently. No secrets read or written."
