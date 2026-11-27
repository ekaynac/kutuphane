#!/usr/bin/env bash
# Release checks for the `release` job of .github/workflows/ci.yml (tests: tests/test_release_check.py).
#   release_check.sh <tag>          the tag is exactly vMAJOR.MINOR.PATCH, pyproject.toml has the same version and
#                                   docs/guide/changelog.md has a heading "## <tag> (" (all compared as plain text)
#   release_check.sh --notes <tag>  print the changelog section of <tag> (after the check)
#   release_check.sh --plan <tag>   print `build` (nothing exists), or `resume` (both images exist, release missing).
#                                   Exit 1 when the release exists or only one image exists: nothing is overwritten.
#                                   Exit 2 when `gh` or `docker` fails for another reason than "not found".
#                                   Needs GITHUB_REPOSITORY, IMAGE and MODELS_IMAGE (image names without the tag).
set -eu

ROOT="${ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
mode=check
if [ "${1:-}" = "--notes" ] || [ "${1:-}" = "--plan" ]; then mode="${1#--}"; shift; fi
[ $# -eq 1 ] || { echo "usage: release_check.sh [--notes|--plan] <tag>" >&2; exit 2; }
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

# exists <command...>: 0 = exists, 1 = "not found", 2 = any other failure
exists() {
  local out
  if out="$("$@" 2>&1)"; then return 0; fi
  case "$out" in *"not found"*|*"Not Found"*|*"NOT_FOUND"*|*"no such manifest"*) return 1 ;; esac
  echo "$out" >&2
  return 2
}

plan() {
  local rc=0 core models
  exists gh release view "$tag" --repo "$GITHUB_REPOSITORY" >/dev/null || rc=$?
  case $rc in 0) echo "the GitHub release $tag exists: nothing is overwritten" >&2; exit 1 ;; 2) exit 2 ;; esac
  rc=0; exists docker buildx imagetools inspect "$IMAGE:$tag" >/dev/null || rc=$?; core=$rc
  rc=0; exists docker buildx imagetools inspect "$MODELS_IMAGE:$tag" >/dev/null || rc=$?; models=$rc
  [ "$core" -ne 2 ] && [ "$models" -ne 2 ] || exit 2
  if [ "$core" -eq 1 ] && [ "$models" -eq 1 ]; then echo build; return; fi
  if [ "$core" -eq 0 ] && [ "$models" -eq 0 ]; then echo resume; return; fi
  echo "only one image tag $tag exists: a person must decide (nothing is overwritten)" >&2
  exit 1
}

check
case "$mode" in
  check) ;;
  notes) notes ;;
  plan) plan ;;
esac
