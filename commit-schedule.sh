#!/usr/bin/env bash
# Staged commits by file group. Each run takes the next message + paths,
# commits only those files, then optionally schedules the next run.
#
# Usage:
#   ./commit-schedule.sh            # commit next chunk
#   ./commit-schedule.sh --schedule # commit and schedule next in ~35 min
#   ./commit-schedule.sh --all      # commit every remaining chunk now
#   ./commit-schedule.sh --dry-run  # print next chunk without committing
#
# Push is OFF by default. Pass --push to push after each commit.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

MSG_FILE="commit-messages.txt"
MAP_FILE="commit-paths.txt"
STATE_FILE="schedule-state.txt"

DO_PUSH=0
DO_SCHEDULE=0
DO_ALL=0
DRY_RUN=0

for arg in "$@"; do
  case "$arg" in
    --push) DO_PUSH=1 ;;
    --schedule) DO_SCHEDULE=1 ;;
    --all) DO_ALL=1 ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      echo "unknown arg: $arg" >&2
      exit 1
      ;;
  esac
done

if [[ ! -f "$MAP_FILE" ]]; then
  echo "missing $MAP_FILE (one path-list per line, comma separated)" >&2
  exit 1
fi

if [[ ! -s "$MSG_FILE" ]]; then
  echo "all scheduled commits done"
  exit 0
fi

commit_one() {
  if [[ ! -s "$MSG_FILE" ]]; then
    echo "all scheduled commits done"
    return 1
  fi
  if [[ ! -s "$MAP_FILE" ]]; then
    echo "no path groups left in $MAP_FILE but messages remain" >&2
    return 1
  fi

  local msg paths
  msg="$(head -n1 "$MSG_FILE")"
  paths="$(head -n1 "$MAP_FILE")"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "DRY RUN"
    echo "  msg:   $msg"
    echo "  paths: $paths"
    return 0
  fi

  # Drop the consumed lines up front so a failed commit does not reuse them blindly.
  # On failure we restore from backup.
  local msg_bak map_bak
  msg_bak="$(mktemp)"
  map_bak="$(mktemp)"
  cp "$MSG_FILE" "$msg_bak"
  cp "$MAP_FILE" "$map_bak"
  sed -i '' '1d' "$MSG_FILE"
  sed -i '' '1d' "$MAP_FILE"

  # shellcheck disable=SC2086
  if ! git add -- $paths; then
    mv "$msg_bak" "$MSG_FILE"
    mv "$map_bak" "$MAP_FILE"
    echo "git add failed for: $paths" >&2
    return 1
  fi

  # Skip empty commits (nothing staged from that path list)
  if git diff --cached --quiet; then
    mv "$msg_bak" "$MSG_FILE"
    mv "$map_bak" "$MAP_FILE"
    echo "nothing staged for: $paths"
    echo "fix the path list or unstage conflicts, then retry"
    git reset -q
    return 1
  fi

  if ! git commit -m "$msg"; then
    mv "$msg_bak" "$MSG_FILE"
    mv "$map_bak" "$MAP_FILE"
    git reset -q
    echo "commit failed" >&2
    return 1
  fi

  rm -f "$msg_bak" "$map_bak"
  echo "committed: $msg"

  if [[ "$DO_PUSH" -eq 1 ]]; then
    git push
  fi

  return 0
}

if [[ "$DO_ALL" -eq 1 ]]; then
  while [[ -s "$MSG_FILE" ]]; do
    commit_one || exit 1
    if [[ "$DRY_RUN" -eq 1 ]]; then
      # dry-run only shows the first remaining chunk
      exit 0
    fi
  done
  echo "finished all chunks"
  exit 0
fi

commit_one || exit 1

if [[ "$DRY_RUN" -eq 1 ]]; then
  exit 0
fi

if [[ "$DO_SCHEDULE" -eq 1 && -s "$MSG_FILE" ]]; then
  NEXT_RUN="$(date -v+35M +"%Y-%m-%d %H:%M:%S" 2>/dev/null || date -d "+35 minutes" +"%Y-%m-%d %H:%M:%S")"
  echo "$NEXT_RUN" > "$STATE_FILE"
  if command -v at >/dev/null 2>&1; then
    echo "cd \"$REPO_ROOT\" && ./commit-schedule.sh --schedule${DO_PUSH:+ --push}" | at now + 35 minutes
    echo "next chunk scheduled around $NEXT_RUN"
  else
    echo "at not available; run again later: ./commit-schedule.sh --schedule"
  fi
fi
