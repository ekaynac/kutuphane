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
# One run at a time: the run first takes a lock, the container `kutuphane-contract-lock` (created, never started).
# Docker keeps container names unique, so a second create fails: that run exits 2 and changes nothing. A lock left by
# a crashed run or by --keep must be removed by hand: docker rm -f kutuphane-contract-lock.
#
# Data goes one way only. Phase 1: the contract container makes every model call (`--phase calls`). Then this script
# runs the export command on the host, into a file of a private directory (mktemp -d, mode 0700) that no container can
# write to. Phase 2: the contract container runs again (`--phase verify`) with that directory mounted read-only.
#
# Output: one line per check on stdout (docker's own messages go to stderr), then a JSON summary line.
# Exit codes: 0 all checks passed; 1 a check failed (also: the export command failed or ran past its time limit);
# 2 wrong call, the lock is held, a leftover or running `kutuphane-contract` project or network, or a bridge that did
# not answer; 3 all checks passed but the teardown failed (each failed step is named on stderr); 125 a process of the
# export command could not be ended (verify did not run). An earlier failure code is kept.
# Teardown removes only what this run created (containers and volumes with its run id, its network by id, the lock
# last), unless --keep.
set -u -o pipefail

NETWORK=kutuphane-contract
PROJECT=kutuphane-contract
LOCK=kutuphane-contract-lock
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

run_id="$(date +%s)-$$-$RANDOM"
label_filter="label=kutuphane.contract.run=$run_id"
lock_id="" network_id="" export_dir="" export_pgid="" export_stuck=0
# The alias the caller gives its bridge is the host name of the URL; only a container with that alias is detached.
bridge_alias=${KUTUPHANE_LLMDAP_URL#*://}; bridge_alias=${bridge_alias%%/*}; bridge_alias=${bridge_alias%%:*}

# Is any live process in the group? A zombie (state Z) has ended: it only waits to be collected, and `kill -0` counts it
# as alive. So on Linux the members are read from /proc/<pid>/stat (field 3 is the state, field 5 the group) and the
# zombies are ignored. Without a readable /proc the check falls back to `kill -0` on the group.
# (LLMDAP_CONTRACT_CI_TEST_GROUP_ALIVE is a hook of tests/test_llmdap_contract_ci.py: a file whose existence means
# "alive". Never set it elsewhere.)
group_alive() {
  local f line rest st ppid pgrp
  if [ -n "${LLMDAP_CONTRACT_CI_TEST_GROUP_ALIVE:-}" ]; then [ -e "$LLMDAP_CONTRACT_CI_TEST_GROUP_ALIVE" ]; return; fi
  if [ -r /proc/self/stat ]; then
    for f in /proc/[0-9]*/stat; do
      read -r line <"$f" 2>/dev/null || continue
      rest=${line##*) }   # the command name (field 2) may hold spaces and parentheses: cut after the last one
      read -r st ppid pgrp _ <<<"$rest"
      if [ "$pgrp" = "$1" ] && [ "$st" != Z ]; then return 0; fi
    done
    return 1
  fi
  kill -0 -- "-$1" 2>/dev/null
}

# Ends a whole process group: TERM, a few seconds of grace, KILL. Returns 1 if a member still lives.
reap_group() {
  local i
  group_alive "$1" || return 0
  kill -TERM -- "-$1" 2>/dev/null
  for i in 1 2 3; do
    group_alive "$1" || return 0
    sleep 1
  done
  kill -KILL -- "-$1" 2>/dev/null
  for i in 1 2 3; do
    group_alive "$1" || return 0
    sleep 1
  done
  return 1
}

cleanup() {
  local rc=$? failed=0 c out ids id names aliases
  local -a valid
  fail() { echo "llmdap_contract_ci: teardown failed: $*" >&2; failed=1; }
  # a process group of the export command that is not ended yet (interrupt, or an earlier failed attempt)
  if [ -n "$export_pgid" ]; then
    reap_group "$export_pgid" && export_pgid="" || fail "a process of the export command is still alive (group $export_pgid)"
  fi
  if [ "$keep" = 1 ] && [ -n "$network_id" ]; then
    echo "llmdap_contract_ci: --keep: containers, the lock $LOCK, network $NETWORK and $export_dir stay (remove them by the label kutuphane.contract.run=$run_id)" >&2
    exit "$rc"
  fi
  # A removal step runs only on ids of a successful listing (stderr of the listing is never captured into the ids).
  if ids=$(docker ps -a -q --no-trunc --filter "$label_filter"); then
    valid=()
    for id in $ids; do   # full ids (--no-trunc), as `docker create` printed the lock's
      if [ "$id" = "$lock_id" ]; then continue; fi   # the lock is removed last
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
  if [ -n "$network_id" ]; then
    # the bridge the caller attached (alias = the URL's host): detach it, then remove the network; all by id. The keys
    # of .Containers are container ids; the alias is read from the same id.
    if names=$(docker network inspect -f '{{range $cid, $c := .Containers}}{{$cid}} {{end}}' "$network_id"); then
      for c in $names; do
        if ! [[ $c =~ ^[0-9a-f]{12,64}$ ]]; then fail "unexpected container id '$c' on the network (not detached)"; continue; fi
        if aliases=$(docker inspect -f "{{range (index .NetworkSettings.Networks \"$NETWORK\").Aliases}}{{.}} {{end}}" "$c"); then
          if printf '%s\n' "$aliases" | tr ' ' '\n' | grep -qx "$bridge_alias"; then
            out=$(docker network disconnect -f "$network_id" "$c" 2>&1) || fail "docker network disconnect $c: $out"
          fi
        else
          fail "cannot inspect container $c on the network (not detached)"
        fi
      done
    else
      fail "cannot inspect the network $network_id (no container detached)"
    fi
    out=$(docker network rm "$network_id" 2>&1) || fail "docker network rm $network_id: $out"
  fi
  [ -z "$export_dir" ] || rm -rf "$export_dir" || fail "cannot remove $export_dir"
  # the lock, by id, as the last step
  if [ -n "$lock_id" ]; then
    out=$(docker rm -f -v "$lock_id" 2>&1) || fail "docker rm of the lock $lock_id: $out"
  fi
  # nothing of this run may be left (a failed query is a failure, not "nothing")
  gone() {
    local what=$1 o; shift
    if o=$("$@"); then [ -z "$o" ] || fail "$what of the run are left"; else fail "cannot check that the $what of the run are gone"; fi
  }
  gone containers docker ps -a -q --no-trunc --filter "$label_filter"
  gone volumes docker volume ls -q --filter "$label_filter"
  [ -z "$network_id" ] || gone networks docker network ls -q --no-trunc --filter "id=$network_id"
  [ "$failed" = 0 ] || [ "$rc" != 0 ] || rc=3
  exit "$rc"
}

# The export command runs on the host, in its own process group (job control), with a time limit. Pure bash: poll with
# kill -0. When the leader ends, or at the limit, the whole group is ended before the file is read. Returns the exit
# status of the command (124 at the limit). If a member of the group could not be ended, it also sets export_stuck=1
# (a variable of its own, so a command that itself exits 125 stays an ordinary failure) and leaves the group in
# $export_pgid for cleanup to retry.
run_export() {
  local waited=0 rc leader
  export_stuck=0
  set -m
  bash -c "$audit_export" </dev/null >"$export_file" 2>"$export_err" &
  leader=$! export_pgid=$!
  set +m
  while kill -0 "$leader" 2>/dev/null; do
    if [ "$waited" -ge "$export_timeout" ]; then
      echo "the export command ran longer than ${export_timeout}s and was killed" >>"$export_err"
      if reap_group "$export_pgid"; then
        export_pgid=""
        wait "$leader" 2>/dev/null   # the group is gone, so the leader is dead: this does not block
      else
        echo "a process of the export command could not be ended" >>"$export_err"
        export_stuck=1   # never wait for a leader that may still live
      fi
      return 124
    fi
    sleep 1
    waited=$((waited + 1))
  done
  wait "$leader"; rc=$?
  if reap_group "$export_pgid"; then export_pgid=""; else
    echo "a process of the export command could not be ended" >>"$export_err"
    export_stuck=1
  fi
  return "$rc"
}

# The lock: the one resource whose name the daemon reserves atomically. A second create fails with a conflict.
lock_id=$(docker create --name "$LOCK" --label "kutuphane.contract.run=$run_id" "$image" true) \
  || die "cannot take the lock $LOCK (another run holds it, or a leftover; or the image cannot be created); nothing was changed"
[[ $lock_id =~ ^[0-9a-f]{12,64}$ ]] || { lock_id=""; die "the lock container has no usable id; remove $LOCK by hand"; }
trap cleanup EXIT
trap 'exit 130' INT TERM

# Under the lock: refuse if anything of the project or the network exists (a leftover, or --keep).
found_containers=$(docker ps -a -q --filter "label=com.docker.compose.project=$PROJECT") \
  || die "cannot list the containers of the project $PROJECT; nothing was created"
found_volumes=$(docker volume ls -q --filter "label=com.docker.compose.project=$PROJECT") \
  || die "cannot list the volumes of the project $PROJECT; nothing was created"
found_networks=$(docker network ls -q --filter "name=^${NETWORK}\$") \
  || die "cannot list the networks; nothing was created"
[ -z "$found_containers$found_volumes$found_networks" ] \
  || die "the compose project or network $NETWORK already exists (a leftover or --keep run is there); nothing was created"
network_id=$(docker network create --internal --label "kutuphane.contract.run=$run_id" "$NETWORK") \
  || die "cannot create the network $NETWORK"
[[ $network_id =~ ^[0-9a-f]{12,64}$ ]] || { network_id=""; die "the network has no usable id; remove $NETWORK by hand"; }
export_dir=$(mktemp -d) || die "cannot create a temporary directory"
export_file="$export_dir/export.jsonl" export_err="$export_dir/export.err"

export CONTRACT_IMAGE=$image CONTRACT_EXPORT_DIR=$export_dir CONTRACT_RUN_ID=$run_id KUTUPHANE_LLMDAP_URL KUTUPHANE_LLMDAP_KEY
CONTRACT_UID=$(id -u) CONTRACT_GID=$(id -g)   # the container reads the export directory as this user
export CONTRACT_UID CONTRACT_GID
CONTRACT_DB_PASSWORD=$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')
export CONTRACT_DB_PASSWORD
dc() { docker compose -f "$compose_file" -p "$PROJECT" --profile run "$@"; }

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
if [ "$export_stuck" = 1 ]; then   # a process of the export command lives: verify must not start
  lines=$(printf '%s\n' "$out1" | grep -E '^(PASS|FAIL) ')
  [ -z "$lines" ] || printf '%s\n' "$lines"
  echo "llmdap_contract_ci: the verify phase did not run: a process of the export command could not be ended" >&2
  exit 125
fi
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
