#!/usr/bin/env bash
# LLMDAP contract runner (#243): one command, needs only Docker (with the compose plugin) and bash on the host.
# See deploy/llmdap/README.md, "Contract runner".
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
#
# Data goes one way only. Phase 1: the contract container makes every model call (`--phase calls`). Then this script
# runs the export command on the host, into a file of a private directory (mktemp -d, mode 0700) that no container can
# write to. Phase 2: the contract container runs again (`--phase verify`) with that directory mounted read-only.
#
# Output: one line per check on stdout (docker's own messages go to stderr), then a JSON summary line.
# Exit codes: 0 all checks passed; 1 a check failed (also: the export command failed or ran past its time limit);
# 2 wrong call, a leftover or running `kutuphane-contract` project or network, or a bridge that did not answer;
# 3 all checks passed but the teardown failed (each failed step is named on stderr). An earlier failure code is kept.
# Teardown removes only what this run created (containers and volumes with its run id, its network), unless --keep.
set -u -o pipefail

NETWORK=kutuphane-contract
PROJECT=kutuphane-contract
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
command -v docker >/dev/null 2>&1 || die "docker is not installed"
docker compose version >/dev/null 2>&1 || die "the docker compose plugin is not installed"

# Ownership, step 1: refuse if anything of the project or the network exists (another run, or a leftover). Nothing is
# changed or removed in that case.
found_containers=$(docker ps -a -q --filter "label=com.docker.compose.project=$PROJECT") \
  || die "cannot list the containers of the project $PROJECT; nothing was changed"
found_volumes=$(docker volume ls -q --filter "label=com.docker.compose.project=$PROJECT") \
  || die "cannot list the volumes of the project $PROJECT; nothing was changed"
found_networks=$(docker network ls -q --filter "name=^${NETWORK}\$") \
  || die "cannot list the networks; nothing was changed"
[ -z "$found_containers$found_volumes$found_networks" ] \
  || die "the compose project or network $NETWORK already exists (another run is active, or a leftover or --keep run is there); nothing was changed"
# Step 2: creating the network is the atomic claim. The EXIT trap is installed only after it succeeded.
run_id="$(date +%s)-$$-$RANDOM"
docker network create --internal --label "kutuphane.contract.run=$run_id" "$NETWORK" >/dev/null 2>&1 \
  || die "cannot create the network $NETWORK (it was created by someone else just now); nothing was changed"
export_dir=$(mktemp -d) || { docker network rm "$NETWORK" >/dev/null 2>&1; die "cannot create a temporary directory"; }
export_file="$export_dir/export.jsonl" export_err="$export_dir/export.err"

export CONTRACT_IMAGE=$image CONTRACT_EXPORT_DIR=$export_dir CONTRACT_RUN_ID=$run_id KUTUPHANE_LLMDAP_URL KUTUPHANE_LLMDAP_KEY
CONTRACT_UID=$(id -u) CONTRACT_GID=$(id -g)   # the container reads the export directory as this user
export CONTRACT_UID CONTRACT_GID
CONTRACT_DB_PASSWORD=$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')
export CONTRACT_DB_PASSWORD
dc() { docker compose -f "$compose_file" -p "$PROJECT" --profile run "$@"; }
# The alias the caller gives its bridge is the host name of the URL; only a container with that alias is detached.
bridge_alias=${KUTUPHANE_LLMDAP_URL#*://}; bridge_alias=${bridge_alias%%/*}; bridge_alias=${bridge_alias%%:*}
label_filter="label=kutuphane.contract.run=$run_id"

export_pid=""
cleanup() {
  local rc=$? failed=0 c out ids id names
  local -a valid
  [ -n "$export_pid" ] && reap_group "$export_pid"
  if [ "$keep" = 1 ]; then
    echo "llmdap_contract_ci: --keep: containers, network $NETWORK and $export_dir stay (remove them by the label kutuphane.contract.run=$run_id)" >&2
    exit "$rc"
  fi
  fail() { echo "llmdap_contract_ci: teardown failed: $*" >&2; failed=1; }
  # A removal step runs only on ids of a successful listing (stderr of the listing is never captured into the ids).
  if ids=$(docker ps -a -q --filter "$label_filter"); then
    valid=()
    for id in $ids; do
      if [[ $id =~ ^[0-9a-f]{12,64}$ ]]; then valid+=("$id"); else fail "unexpected container id '$id' (not removed)"; fi
    done
    if [ "${#valid[@]}" -gt 0 ]; then
      out=$(docker rm -f -v "${valid[@]}" 2>&1) || fail "docker rm of the run's containers: $out"
    fi
  else
    fail "cannot list the run's containers (none removed)"
  fi
  if ids=$(docker volume ls -q --filter "$label_filter"); then
    valid=()
    for id in $ids; do
      if [[ $id =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then valid+=("$id"); else fail "unexpected volume name '$id' (not removed)"; fi
    done
    if [ "${#valid[@]}" -gt 0 ]; then
      out=$(docker volume rm "${valid[@]}" 2>&1) || fail "docker volume rm: $out"
    fi
  else
    fail "cannot list the run's volumes (none removed)"
  fi
  # the bridge the caller attached (alias = the URL's host): detach it, then remove the network
  if names=$(docker network inspect -f '{{range .Containers}}{{.Name}} {{end}}' "$NETWORK" 2>/dev/null); then
    for c in $names; do
      if docker inspect -f "{{range (index .NetworkSettings.Networks \"$NETWORK\").Aliases}}{{.}} {{end}}" "$c" 2>/dev/null \
          | tr ' ' '\n' | grep -qx "$bridge_alias"; then
        out=$(docker network disconnect -f "$NETWORK" "$c" 2>&1) || fail "docker network disconnect $c: $out"
      fi
    done
  fi
  out=$(docker network rm "$NETWORK" 2>&1) || fail "docker network rm $NETWORK: $out"
  rm -rf "$export_dir" || fail "cannot remove $export_dir"
  # nothing of this run may be left (a failed query is a failure, not "nothing")
  gone() {
    local what=$1 o; shift
    if o=$("$@"); then [ -z "$o" ] || fail "$what of the run are left"; else fail "cannot check that the $what of the run are gone"; fi
  }
  gone containers docker ps -a -q --filter "$label_filter"
  gone volumes docker volume ls -q --filter "$label_filter"
  gone networks docker network ls -q --filter "name=^${NETWORK}\$"
  [ "$failed" = 0 ] || [ "$rc" != 0 ] || rc=3
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

# Ends a whole process group: TERM, a few seconds of grace, KILL. Returns 1 if a member still lives.
reap_group() {
  local i
  kill -0 -- "-$1" 2>/dev/null || return 0
  kill -TERM -- "-$1" 2>/dev/null
  for i in 1 2 3; do
    kill -0 -- "-$1" 2>/dev/null || return 0
    sleep 1
  done
  kill -KILL -- "-$1" 2>/dev/null
  for i in 1 2 3; do
    kill -0 -- "-$1" 2>/dev/null || return 0
    sleep 1
  done
  return 1
}

# The export command runs on the host, in its own process group (job control), with a time limit. Pure bash: poll with
# kill -0. When the leader ends, or at the limit, the whole group is ended before the file is read: the verify phase
# never starts while a member lives. Returns the exit status of the command, 124 at the limit, 125 if a member of the
# group could not be ended.
run_export() {
  local waited=0 rc pgid
  set -m
  bash -c "$audit_export" </dev/null >"$export_file" 2>"$export_err" &
  export_pid=$! pgid=$!
  set +m
  while kill -0 "$export_pid" 2>/dev/null; do
    if [ "$waited" -ge "$export_timeout" ]; then
      echo "the export command ran longer than ${export_timeout}s and was killed" >>"$export_err"
      reap_group "$pgid" || echo "a process of the export command could not be ended" >>"$export_err"
      wait "$export_pid" 2>/dev/null
      export_pid=""
      return 124
    fi
    sleep 1
    waited=$((waited + 1))
  done
  wait "$export_pid"; rc=$?
  if ! reap_group "$pgid"; then
    echo "a process of the export command could not be ended" >>"$export_err"
    rc=125
  fi
  export_pid=""
  return "$rc"
}

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

contract_args=(/contract/book --chat chat stub-chat --embed emb stub-embed --rerank rerank stub-rerank)
# Phase 1: every model call and the authentication checks.
out1=$(dc run --rm -T contract "${contract_args[@]}" --phase calls); rc1=$?
# The export, on the host, into the private file.
run_export; export_rc=$?
[ ! -s "$export_err" ] || sed 's/^/audit-export: /' "$export_err" >&2
# Phase 2: the audit checks against the rows of phase 1, the export read from the read-only mount.
out2=$(dc run --rm -T contract "${contract_args[@]}" --phase verify \
         --audit-export-file /export/export.jsonl --audit-export-status "$export_rc"); rc2=$?

lines=$(printf '%s\n%s\n' "$out1" "$out2" | grep -E '^(PASS|FAIL) ')
[ -z "$lines" ] || printf '%s\n' "$lines"
passed=$(printf '%s\n' "$lines" | grep -c '^PASS ')
failed_checks=$(printf '%s\n' "$lines" | grep -c '^FAIL ')
printf '{"passed": %s, "of": %s}\n' "$passed" "$((passed + failed_checks))"
[ "$rc1" = 0 ] && [ "$rc2" = 0 ] && [ "$failed_checks" = 0 ] && exit 0
exit 1
