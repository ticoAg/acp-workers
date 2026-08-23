#!/bin/bash
# Make the acpw CLI available at or above the version this skill needs,
# then report the result as one JSON line on stdout.
set -euo pipefail

# Bump when the skill starts relying on a newer CLI. Below this, the script upgrades.
required_version="0.7.0"

force=0
update=0
completion=0
selfcheck=1
while [ $# -gt 0 ]; do
  case "$1" in
    --force) force=1 ;;
    --update) update=1 ;;
    --completion) completion=1 ;;
    --no-selfcheck) selfcheck=0 ;;
    -h|--help)
      echo "usage: ensure-acpw.sh [--update] [--force] [--completion] [--no-selfcheck]" >&2
      echo "  --update         reinstall from source to pick up the latest release" >&2
      echo "  --force          reinstall even if the installed version is current" >&2
      echo "  --completion     also run 'acpw install' (writes ~/.bashrc)" >&2
      echo "  --no-selfcheck   skip the post-install 'acpw selfcheck'" >&2
      echo "requires acpw >= $required_version" >&2
      exit 0
      ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

skill_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
local_pkg="$skill_dir/../../packages/acpw"
git_spec='git+https://github.com/ticoAg/acp-workers#subdirectory=packages/acpw'
notes=()

installed_version() {
  command -v acpw >/dev/null 2>&1 || return 0
  # Pre-0.1.0 builds have no version command; an empty answer counts as outdated.
  # New CLI prints markdown (`version: 0.6.4`); older CLI printed one JSON line.
  local out v
  out=$(acpw version 2>/dev/null) || return 0
  v=$(printf '%s\n' "$out" | sed -n 's/.*"version":"\([^"]*\)".*/\1/p' | head -n1)
  if [ -n "$v" ]; then
    printf '%s\n' "$v"
    return
  fi
  printf '%s\n' "$out" | sed -n 's/^version:[[:space:]]*//p' | head -n1
}

older_than() { # older_than WHAT FLOOR
  [ -z "$1" ] && return 0
  [ "$1" = "$2" ] && return 1
  [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -n1)" = "$1" ]
}

selfcheck_state="skipped"

run_selfcheck() {
  [ "$selfcheck" -eq 1 ] || return 0
  local report
  if report=$(acpw selfcheck 2>/dev/null); then
    selfcheck_state="pass"
  else
    selfcheck_state="fail"
    notes+=("acpw selfcheck failed; full report on stderr")
    echo "$report" >&2
  fi
}

emit() {
  local ok="$1" action="$2" source="$3"
  local joined=""
  if [ "${#notes[@]}" -gt 0 ]; then
    joined=$(printf '"%s",' "${notes[@]}")
    joined="${joined%,}"
  fi
  [ "$selfcheck_state" = "fail" ] && ok=false
  printf '{"ok":%s,"action":"%s","version":"%s","required":"%s","acpw":"%s","source":"%s","completion":%s,"selfcheck":"%s","notes":[%s]}\n' \
    "$ok" "$action" "$(installed_version)" "$required_version" "$(command -v acpw || true)" "$source" \
    "$([ "$completion" -eq 1 ] && echo true || echo false)" "$selfcheck_state" "$joined"
}

run_completion() {
  [ "$completion" -eq 1 ] || return 0
  acpw install >/dev/null || notes+=("acpw install failed; shell completion not registered")
}

current="$(installed_version)"
if [ -n "$current" ] && [ "$force" -eq 0 ] && [ "$update" -eq 0 ] && ! older_than "$current" "$required_version"; then
  run_completion
  run_selfcheck
  emit true already existing
  if [ "$selfcheck_state" = "fail" ]; then exit 1; fi
  exit 0
fi

if [ -n "$current" ] && [ "$update" -eq 0 ] && [ "$force" -eq 0 ]; then
  echo "acpw $current is below the required $required_version; upgrading" >&2
fi

if ! command -v uv >/dev/null 2>&1; then
  notes+=("uv is required: https://docs.astral.sh/uv/getting-started/installation/")
  emit false missing-uv none
  exit 1
fi

if [ -f "$local_pkg/pyproject.toml" ]; then
  source_spec="$(cd "$local_pkg" && pwd)"
else
  source_spec="$git_spec"
fi

echo "installing acpw from $source_spec" >&2
# --force reinstalls in place, which is also how a git-sourced tool picks up new commits.
if ! uv tool install --force "$source_spec" >&2; then
  notes+=("uv tool install failed")
  emit false install-failed "$source_spec"
  exit 1
fi

hash -r 2>/dev/null || true
if ! command -v acpw >/dev/null 2>&1; then
  notes+=("acpw installed but not on PATH; add ~/.local/bin to PATH and reopen the shell")
  emit false path-missing "$source_spec"
  exit 1
fi

new="$(installed_version)"
if older_than "$new" "$required_version"; then
  notes+=("installed acpw $new is still below the required $required_version; the source may be stale")
  emit false version-too-old "$source_spec"
  exit 1
fi

run_completion
run_selfcheck
if [ -n "$current" ]; then
  emit true updated "$source_spec"
else
  emit true installed "$source_spec"
fi
if [ "$selfcheck_state" = "fail" ]; then exit 1; fi
