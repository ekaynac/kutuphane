#!/usr/bin/env bash
# Release checks for the `release` job of .github/workflows/ci.yml (tests: tests/test_release_check.py).
#   release_check.sh <tag>          the tag is exactly vMAJOR.MINOR.PATCH, pyproject.toml has the same version and
#                                   docs/guide/changelog.md has a heading "## <tag> (" (all compared as plain text)
#   release_check.sh --notes <tag>  print the changelog section of <tag> (after the check)
#   release_check.sh --plan <tag>   print `build` (nothing exists), or `resume` (both images exist, release missing).
#                                   Exit 1 when the release exists or only one image exists: nothing is overwritten.
#                                   Exit 2 when `gh` or `docker` is missing or fails for another reason than the exact "not found" message.
#                                   Needs GITHUB_REPOSITORY, IMAGE and MODELS_IMAGE (image names without the tag).
#   release_check.sh --public <tag> both images can be read with no login (an empty DOCKER_CONFIG). Exit 1 and name the
#                                   image that cannot be read: a new GHCR package is private until the owner sets it
#                                   to Public in the package settings. Needs IMAGE and MODELS_IMAGE.
set -eu

ROOT="${ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
mode=check
if [ "${1:-}" = "--notes" ] || [ "${1:-}" = "--plan" ] || [ "${1:-}" = "--public" ]; then mode="${1#--}"; shift; fi
[ $# -eq 1 ] || { echo "usage: release_check.sh [--notes|--plan|--public] <tag>" >&2; exit 2; }
tag="$1"

semver='^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'
[[ "$tag" =~ $semver ]] || { echo "tag $tag is not vMAJOR.MINOR.PATCH (no pre-release, no build metadata, no leading zero)" >&2; exit 1; }

check() {
  grep -Fxq "version = \"${tag#v}\"" "$ROOT/pyproject.toml" \
    || { echo "pyproject.toml has no line: version = \"${tag#v}\"" >&2; exit 1; }
  awk -v p="## $tag (" 'index($0, p) == 1 { found = 1 } END { exit !found }' "$ROOT/docs/guide/changelog.md" \
    || { echo "docs/guide/changelog.md has no heading starting with '## $tag ('" >&2; exit 1; }
}

notes() {
  awk -v p="## $tag (" '
    index($0, p) == 1 { on = 1; next }
    on && index($0, "## ") == 1 { exit }
    on { print }
  ' "$ROOT/docs/guide/changelog.md"
}

# exists <ref> <command...>: 0 = exists; 1 = absent; 2 = any other failure (the output goes to stderr).
# Absent is only the exact message of the tool with exit status 1: `release not found` (gh) or a last line that ends
# with `<ref>: not found` (docker buildx imagetools inspect). `gh: command not found` (127), a missing credential
# helper, a 403 or a network error are failures, not absence.
exists() {
  local ref="$1" out rc=0 last
  shift
  out="$("$@" 2>&1)" || rc=$?
  [ "$rc" -eq 0 ] && return 0
  if [ "$rc" -eq 1 ]; then
    if [ "$1" = gh ]; then
      [ "$(printf '%s' "$out" | tr -d '\r' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')" = "release not found" ] && return 1
    else
      last="$(printf '%s\n' "$out" | tr -d '\r' | sed -e '/^[[:space:]]*$/d' | tail -n 1)"
      case "$last" in *"$ref: not found") return 1 ;; esac
    fi
  fi
  printf '%s (exit status %s)\n' "$out" "$rc" >&2
  return 2
}

plan() {
  local rc=0 core models
  command -v gh >/dev/null || { echo "gh is not installed" >&2; exit 2; }
  command -v docker >/dev/null || { echo "docker is not installed" >&2; exit 2; }
  exists "$tag" gh release view "$tag" --repo "$GITHUB_REPOSITORY" >/dev/null || rc=$?
  case $rc in 0) echo "the GitHub release $tag exists: nothing is overwritten" >&2; exit 1 ;; 2) exit 2 ;; esac
  rc=0; exists "$IMAGE:$tag" docker buildx imagetools inspect "$IMAGE:$tag" >/dev/null || rc=$?; core=$rc
  rc=0; exists "$MODELS_IMAGE:$tag" docker buildx imagetools inspect "$MODELS_IMAGE:$tag" >/dev/null || rc=$?; models=$rc
  [ "$core" -ne 2 ] && [ "$models" -ne 2 ] || exit 2
  if [ "$core" -eq 1 ] && [ "$models" -eq 1 ]; then echo build; return; fi
  if [ "$core" -eq 0 ] && [ "$models" -eq 0 ]; then echo resume; return; fi
  echo "only one image tag $tag exists: a person must decide (nothing is overwritten)" >&2
  exit 1
}

public() {
  command -v docker >/dev/null || { echo "docker is not installed" >&2; exit 2; }
  local cfg bad=0 ref
  cfg="$(mktemp -d)"
  trap 'rm -rf "$cfg"' EXIT
  for ref in "$IMAGE:$tag" "$MODELS_IMAGE:$tag"; do
    if ! DOCKER_CONFIG="$cfg" docker buildx imagetools inspect "$ref" >/dev/null 2>&1; then
      echo "$ref cannot be read without a login: set the package to Public" >&2
      bad=1
    fi
  done
  exit "$bad"
}

check
case "$mode" in
  check) ;;
  notes) notes ;;
  plan) plan ;;
  public) public ;;
esac
