#!/usr/bin/env bash
# LLMDAP contract runner (#243): one command, needs only Docker on the host. See deploy/llmdap/README.md, "Contract runner".
#
#   KUTUPHANE_LLMDAP_URL=http://llmdap:8787 KUTUPHANE_LLMDAP_KEY=<token of svc-kutuphane> \
#     deploy/llmdap_contract_ci.sh --audit-export "<command that prints the verified LLMDAP chain as JSONL>" \
#     [--image <kutuphane image>] [--export-timeout <seconds, default 120>] [--keep]
#
# It creates the Docker network `kutuphane-contract` and the compose project `kutuphane-contract` (scratch Postgres,
# the model stub, and deploy/llmdap_contract.py run in the Kütüphane image against deploy/contract/book). The caller
# attaches its bridge to the network with alias `llmdap`, before or after the start; the runner waits up to 60 s.
# Routes the bridge must have: chat -> stub-chat, emb -> stub-embed (embeddings), rerank -> stub-rerank (rerank),
# all at http://model-stub:8000; GATEWAY_ALLOWED_HOSTS must include `llmdap`.
# Output: one line per check on stdout (docker's own messages go to stderr). Exit 0 only if every check passes.
# Exit codes: 0 all checks passed; 1 a check failed (also: the export command failed or ran past its time limit);
# 2 wrong call, the network exists, or the bridge did not answer; 3 all checks passed but the teardown failed (each failed
# step is named on stderr). An earlier failure code is kept.
# Teardown: the project, its volumes and the network are always removed, unless --keep.
set -u -o pipefail

NETWORK=kutuphane-contract
WAIT_SECONDS=60
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
compose_file="$here/contract/compose.yaml"

die() { echo "llmdap_contract_ci: $*" >&2; exit 2; }

audit_export="" image="" keep=0 export_timeout=120
while [ $# -gt 0 ]; do
  case "$1" in
    --audit-export) [ $# -ge 2 ] || die "--audit-export needs a command"; audit_export=$2; shift 2 ;;
    --image) [ $# -ge 2 ] || die "--image needs an image"; image=$2; shift 2 ;;
    --export-timeout) [ $# -ge 2 ] || die "--export-timeout needs seconds"; export_timeout=$2; shift 2 ;;
    --keep) keep=1; shift ;;
    *) die "unknown argument: $1" ;;
  esac
done
case "$export_timeout" in ''|*[!0-9]*|0) die "--export-timeout must be a whole number of seconds, 1 or more" ;; esac
[ -n "$audit_export" ] || die "--audit-export \"<cmd>\" is required"
[ -n "${KUTUPHANE_LLMDAP_URL:-}" ] || die "set KUTUPHANE_LLMDAP_URL (the bridge as seen from the network $NETWORK, e.g. http://llmdap:8787)"
[ -n "${KUTUPHANE_LLMDAP_KEY:-}" ] || die "set KUTUPHANE_LLMDAP_KEY (the token of subject svc-kutuphane)"
if [ -z "$image" ]; then
  [ -n "${KUTUPHANE_VERSION:-}" ] || die "set KUTUPHANE_VERSION to a release tag, or pass --image <kutuphane image>"
  image=ghcr.io/ekaynac/kutuphane:${KUTUPHANE_VERSION}
fi
command -v docker >/dev/null || die "docker is not installed"

# Ownership: creating the network is the one atomic step. If it fails (the network exists: another run is active, or
# --keep left one), exit 2 at once and touch nothing. The EXIT trap is installed only after it succeeded, so a run
# removes only what it created itself.
docker network create --internal "$NETWORK" >/dev/null 2>&1 \
  || die "cannot create the network $NETWORK (it exists: a run is active, or --keep left one); nothing was changed"
io_dir=$(mktemp -d) || { docker network rm "$NETWORK" >/dev/null 2>&1; die "cannot create a temporary directory"; }
export CONTRACT_IMAGE=$image CONTRACT_IO_DIR=$io_dir KUTUPHANE_LLMDAP_URL KUTUPHANE_LLMDAP_KEY
CONTRACT_UID=$(id -u) CONTRACT_GID=$(id -g)   # the container runs as this user, so only this user writes in $io_dir
export CONTRACT_UID CONTRACT_GID
CONTRACT_DB_PASSWORD=$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')
export CONTRACT_DB_PASSWORD
dc() { docker compose -f "$compose_file" -p kutuphane-contract --profile run "$@"; }
# The alias the caller gives its bridge is the host name of the URL; only a container with that alias is detached.
bridge_alias=${KUTUPHANE_LLMDAP_URL#*://}; bridge_alias=${bridge_alias%%/*}; bridge_alias=${bridge_alias%%:*}

serve_pid=""
cleanup() {
  local rc=$? failed=0 c out
  [ -n "$serve_pid" ] && { pkill -P "$serve_pid" 2>/dev/null; kill "$serve_pid" 2>/dev/null; }
  if [ "$keep" = 1 ]; then
    echo "llmdap_contract_ci: --keep: project and network $NETWORK stay up (docker compose -f $compose_file -p kutuphane-contract --profile run down -v; docker network rm $NETWORK)" >&2
  else
    fail() { echo "llmdap_contract_ci: teardown failed: $*" >&2; failed=1; }
    out=$(dc down -v --remove-orphans 2>&1) || fail "docker compose down: $out"
    # the bridge the caller attached (alias = the URL's host): detach it, then remove the network
    for c in $(docker network inspect -f '{{range .Containers}}{{.Name}} {{end}}' "$NETWORK" 2>/dev/null); do
      if docker inspect -f "{{range (index .NetworkSettings.Networks \"$NETWORK\").Aliases}}{{.}} {{end}}" "$c" 2>/dev/null \
          | tr ' ' '\n' | grep -qx "$bridge_alias"; then
        out=$(docker network disconnect -f "$NETWORK" "$c" 2>&1) || fail "docker network disconnect $c: $out"
      fi
    done
    out=$(docker network rm "$NETWORK" 2>&1) || fail "docker network rm $NETWORK: $out"
    rm -rf "$io_dir" || fail "cannot remove $io_dir"
    [ "$failed" = 0 ] || [ "$rc" != 0 ] || rc=3
  fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

# The audit export is a command of the host (it usually runs `docker exec` into the bridge), but the contract runs in a
# container. The container asks through $io_dir/want; the host runs the command (under a time limit) and answers with
# export.jsonl, rc and done. $io_dir is 0700 and owned by this user, and so is the user of the container. The host never
# follows a link: a request must be a regular file of this user, and every answer is a new mktemp file moved into place.
owned_file() { [ -f "$1" ] && [ ! -L "$1" ] && [ "$(stat -c %u "$1")" = "$CONTRACT_UID" ]; }
put() {   # put <name> <content file>: move a finished file into place (rename replaces a planted link, never follows it)
  mv -f "$2" "$io_dir/$1"
}
serve_export() {
  local out err rcf dn rc
  while :; do
    if [ -e "$io_dir/want" ] || [ -L "$io_dir/want" ]; then
      out=$(mktemp "$io_dir/out.XXXXXX") err=$(mktemp "$io_dir/err.XXXXXX") rcf=$(mktemp "$io_dir/rc.XXXXXX")
      if owned_file "$io_dir/want"; then
        timeout --kill-after=5 "$export_timeout" bash -c "$audit_export" >"$out" 2>"$err"
        rc=$?
        [ "$rc" != 124 ] || echo "the export command ran longer than ${export_timeout}s and was killed" >>"$err"
      else
        rc=1; echo "the request file is not a regular file of this user; refused" >"$err"
      fi
      rm -f "$io_dir/want"
      echo "$rc" >"$rcf"
      put export.jsonl "$out"; put export.err "$err"; put rc "$rcf"
      dn=$(mktemp "$io_dir/done.XXXXXX"); put done "$dn"
      return
    fi
    sleep 0.2
  done
}
# The command the contract runs inside the container: ask, wait at most export_timeout + 10 s, then replay the answer.
container_export="sh -c 'touch /io/want; n=0; while [ ! -f /io/done ]; do [ \$n -lt $(( (export_timeout + 10) * 5 )) ] || exit 124; n=\$((n+1)); sleep 0.2; done; cat /io/export.jsonl; exit \$(cat /io/rc)'"

echo "network $NETWORK ready: attach the bridge with --alias llmdap" >&2
dc up -d --wait postgres model-stub >&2 || { dc logs >&2; die "scratch stack did not start"; }

# Wait for the bridge: any HTTP answer (even 401) from the URL means it is up.
probe='import sys, urllib.request, urllib.error
try:
    urllib.request.urlopen(sys.argv[1], timeout=3)
except urllib.error.HTTPError:
    pass
'
deadline=$((SECONDS + WAIT_SECONDS))
until dc run --rm -T --no-deps --entrypoint python contract -I -c "$probe" "$KUTUPHANE_LLMDAP_URL" >/dev/null 2>&1; do
  [ $SECONDS -lt $deadline ] || die "the bridge did not answer at $KUTUPHANE_LLMDAP_URL within ${WAIT_SECONDS}s (attach it to $NETWORK with alias llmdap)"
  sleep 2
done

serve_export &
serve_pid=$!
dc run --rm -T contract /contract/book --chat chat stub-chat --embed emb stub-embed --rerank rerank stub-rerank \
  --audit-export "$container_export"
rc=$?
owned_file "$io_dir/export.err" && [ -s "$io_dir/export.err" ] && sed 's/^/audit-export: /' "$io_dir/export.err" >&2
exit "$rc"
