#!/usr/bin/env bash
# LLMDAP contract runner (#243): one command, needs only Docker on the host. See deploy/llmdap/README.md, "Contract runner".
#
#   KUTUPHANE_LLMDAP_URL=http://llmdap:8787 KUTUPHANE_LLMDAP_KEY=<token of svc-kutuphane> \
#     deploy/llmdap_contract_ci.sh --audit-export "<command that prints the verified LLMDAP chain as JSONL>" \
#     [--image <kutuphane image>] [--keep]
#
# It creates the Docker network `kutuphane-contract` and the compose project `kutuphane-contract` (scratch Postgres,
# the model stub, and deploy/llmdap_contract.py run in the Kütüphane image against deploy/contract/book). The caller
# attaches its bridge to the network with alias `llmdap`, before or after the start; the runner waits up to 60 s.
# Routes the bridge must have: chat -> stub-chat, emb -> stub-embed (embeddings), rerank -> stub-rerank (rerank),
# all at http://model-stub:8000; GATEWAY_ALLOWED_HOSTS must include `llmdap`.
# Output: one line per check on stdout (docker's own messages go to stderr). Exit 0 only if every check passes.
# Teardown: the project, its volumes and the network are always removed, unless --keep.
set -u -o pipefail

NETWORK=kutuphane-contract
WAIT_SECONDS=60
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
compose_file="$here/contract/compose.yaml"

die() { echo "llmdap_contract_ci: $*" >&2; exit 2; }

audit_export="" image="" keep=0
while [ $# -gt 0 ]; do
  case "$1" in
    --audit-export) [ $# -ge 2 ] || die "--audit-export needs a command"; audit_export=$2; shift 2 ;;
    --image) [ $# -ge 2 ] || die "--image needs an image"; image=$2; shift 2 ;;
    --keep) keep=1; shift ;;
    *) die "unknown argument: $1" ;;
  esac
done
[ -n "$audit_export" ] || die "--audit-export \"<cmd>\" is required"
[ -n "${KUTUPHANE_LLMDAP_URL:-}" ] || die "set KUTUPHANE_LLMDAP_URL (the bridge as seen from the network $NETWORK, e.g. http://llmdap:8787)"
[ -n "${KUTUPHANE_LLMDAP_KEY:-}" ] || die "set KUTUPHANE_LLMDAP_KEY (the token of subject svc-kutuphane)"
if [ -z "$image" ]; then
  [ -n "${KUTUPHANE_VERSION:-}" ] || die "set KUTUPHANE_VERSION to a release tag, or pass --image <kutuphane image>"
  image=ghcr.io/ekaynac/kutuphane:${KUTUPHANE_VERSION}
fi
command -v docker >/dev/null || die "docker is not installed"
docker network inspect "$NETWORK" >/dev/null 2>&1 && die "the network $NETWORK exists: a run is already active (or left by --keep); remove it first"

io_dir=$(mktemp -d)
chmod 777 "$io_dir"   # the image runs as another user
export CONTRACT_IMAGE=$image CONTRACT_IO_DIR=$io_dir KUTUPHANE_LLMDAP_URL KUTUPHANE_LLMDAP_KEY
CONTRACT_DB_PASSWORD=$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')
export CONTRACT_DB_PASSWORD
dc() { docker compose -f "$compose_file" -p kutuphane-contract --profile run "$@"; }

serve_pid=""
cleanup() {
  [ -n "$serve_pid" ] && kill "$serve_pid" 2>/dev/null
  if [ "$keep" = 1 ]; then
    echo "llmdap_contract_ci: --keep: project and network $NETWORK stay up (docker compose -f $compose_file -p kutuphane-contract --profile run down -v; docker network rm $NETWORK)" >&2
  else
    dc down -v --remove-orphans >&2 2>&1
    # the caller's bridge is still attached: detach every container, then remove the network
    for c in $(docker network inspect -f '{{range .Containers}}{{.Name}} {{end}}' "$NETWORK" 2>/dev/null); do
      docker network disconnect -f "$NETWORK" "$c" >/dev/null 2>&1
    done
    docker network rm "$NETWORK" >/dev/null 2>&1
  fi
  rm -rf "$io_dir"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

# The audit export is a command of the host (it usually runs `docker exec` into the bridge), but the contract runs in a
# container. The container asks through $io_dir/want; the host runs the command and answers with export.jsonl and rc.
serve_export() {
  while :; do
    if [ -f "$io_dir/want" ]; then
      rm -f "$io_dir/want"
      bash -c "$audit_export" >"$io_dir/export.jsonl.tmp" 2>"$io_dir/export.err"
      echo $? >"$io_dir/rc.tmp"
      mv "$io_dir/export.jsonl.tmp" "$io_dir/export.jsonl"
      mv "$io_dir/rc.tmp" "$io_dir/rc"
      chmod a+r "$io_dir/export.jsonl" "$io_dir/rc"
      touch "$io_dir/done"
      return
    fi
    sleep 0.2
  done
}
# The command the contract runs inside the container.
container_export="sh -c 'touch /io/want; while [ ! -f /io/done ]; do sleep 0.2; done; cat /io/export.jsonl; exit \$(cat /io/rc)'"

docker network create --internal "$NETWORK" >/dev/null || die "cannot create the network $NETWORK"
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
[ -s "$io_dir/export.err" ] && sed 's/^/audit-export: /' "$io_dir/export.err" >&2
exit "$rc"
