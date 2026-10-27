#!/usr/bin/env bash
# Install the pinned SkillSpector (skillspector.pin) into its own venv, outside Kütüphane's environment (D71).
#
#   deploy/skillspector/install.sh [PREFIX]        PREFIX: default $SKILLSPECTOR_PREFIX or /opt/skillspector
#
# - Downloads the tag tarball (or uses SKILLSPECTOR_TARBALL=<local file>, for a host without network) and refuses it
#   unless its sha256 is the pinned one.
# - Installs the runtime dependencies from the upstream uv.lock inside that verified tarball, with hash checks, then
#   the project itself without dependencies. No PyPI metadata of Kütüphane names SkillSpector.
# - Copies LICENSE and THIRD_PARTY_NOTICES.md to PREFIX/share/skillspector (Apache-2.0 §4), and the upstream test
#   fixtures safe_skill and malicious_skill to PREFIX/share/skillspector/fixtures for tests/test_skillspector_contract.py.
# - Needs: bash, curl, sha256sum, tar, uv, Python 3.12–3.14 (SKILLSPECTOR_PYTHON, default python3.12).
# Then set KUTUPHANE_SKILLSPECTOR_BIN=PREFIX/bin/skillspector for `kutuphane ingest`, `receive` and `skill rescan`.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=skillspector.pin
. "$here/skillspector.pin"
prefix="$(realpath -m "${1:-${SKILLSPECTOR_PREFIX:-/opt/skillspector}}")"
python="${SKILLSPECTOR_PYTHON:-python3.12}"

if [ -e "$prefix" ] && [ -n "$(ls -A "$prefix" 2>/dev/null)" ]; then
    echo "refused: $prefix exists and is not empty; remove it or give another PREFIX" >&2
    exit 2
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
tarball="$work/skillspector.tar.gz"
if [ -n "${SKILLSPECTOR_TARBALL:-}" ]; then
    cp "$SKILLSPECTOR_TARBALL" "$tarball"
else
    curl --fail --silent --show-error --location --proto '=https' --output "$tarball" "$SKILLSPECTOR_URL"
fi

actual="$(sha256sum "$tarball" | cut -d' ' -f1)"
if [ "$actual" != "$SKILLSPECTOR_SHA256" ]; then
    echo "refused: sha256 mismatch for SkillSpector $SKILLSPECTOR_VERSION" >&2
    echo "  expected $SKILLSPECTOR_SHA256" >&2
    echo "  actual   $actual" >&2
    exit 1
fi

tar -xzf "$tarball" -C "$work"
src="$work/SkillSpector-$SKILLSPECTOR_VERSION"
if ! grep -qx "version = \"$SKILLSPECTOR_VERSION\"" "$src/pyproject.toml"; then
    echo "refused: the tarball is not version $SKILLSPECTOR_VERSION" >&2
    exit 1
fi

# Runtime dependencies only (no dev group, no extras: the [mcp] extra conflicts with Kütüphane's mcp>=2), every
# one pinned and hashed by the upstream lock.
uv export --project "$src" --frozen --no-dev --no-emit-project --format requirements-txt --quiet \
    --output-file "$work/requirements.txt"
uv venv --quiet --python "$python" "$prefix"
uv pip install --quiet --python "$prefix/bin/python" --require-hashes -r "$work/requirements.txt"
uv pip install --quiet --python "$prefix/bin/python" --no-deps "$src"

mkdir -p "$prefix/share/skillspector/fixtures"
cp "$src/LICENSE" "$src/THIRD_PARTY_NOTICES.md" "$prefix/share/skillspector/"
cp -R "$src/tests/fixtures/safe_skill" "$src/tests/fixtures/malicious_skill" "$prefix/share/skillspector/fixtures/"
printf '%s %s\n' "$SKILLSPECTOR_VERSION" "$SKILLSPECTOR_SHA256" > "$prefix/share/skillspector/PINNED"

reported="$(env -i PATH=/usr/bin:/bin HOME="$work" "$prefix/bin/skillspector" --version)"
case "$reported" in
    *"$SKILLSPECTOR_VERSION"*) ;;
    *) echo "refused: installed skillspector reports '$reported', not $SKILLSPECTOR_VERSION" >&2; exit 1 ;;
esac
echo "installed SkillSpector $SKILLSPECTOR_VERSION in $prefix"
echo "KUTUPHANE_SKILLSPECTOR_BIN=$prefix/bin/skillspector"
