#!/usr/bin/env bash
# Run a file of CI steps as ONE HTCondor job on a WWU CS cluster head.
#
# Usage: condor-batch.sh <checkout-dir> <steps-file>
#
# <steps-file> holds one shell command per line. All of them run, in order,
# in one slot: one queue entry however many steps there are. A file with fewer
# than MIN_STEPS (default 2) commands is refused, because a single tiny job
# should run on the runner, not in the cluster queue.
#
# The checkout is rsynced to $CLUSTER_CI_ROOT/<run>/ (a path under the cluster
# home /cluster/home/morri313, which the execute nodes see; the cf463 home is
# not visible there). TMPDIR is on that home too. The log streams back when the
# job ends; the exit code is the last failing step's, or 0.
#
# Exit 70 means the cluster could not run the job normally (ssh failed, or the
# job was held or aborted) and 71 means too few steps; the caller may rerun the
# steps on the runner for those two only. A step's own exit 70, 71 or 255 is
# reported as 1, so no step failure can look like an infrastructure failure.
#
# Environment: CONDOR_HEAD (default cse-head.cluster.cs.wwu.edu),
# CONDOR_SSH_KEY (default ~/.ssh/id_ed25519_condor), CLUSTER_CI_ROOT
# (default /cluster/home/morri313/ci), RUN_ID (default GITHUB_RUN_ID or the
# time), MIN_STEPS, REQUEST_CPUS (default 4), REQUEST_MEMORY (default 8GB).
#
# Exit codes: the last failing step's code, or 0; 2 = refused (too few steps);
# 3 = the job did not end normally (held, removed, aborted, or condor_wait
# failed); 64 = CONDOR_SSH_KEY contains whitespace.
set -euo pipefail

checkout="${1:?usage: condor-batch.sh <checkout-dir> <steps-file>}"
steps="${2:?usage: condor-batch.sh <checkout-dir> <steps-file>}"
head_host="${CONDOR_HEAD:-cse-head.cluster.cs.wwu.edu}"
key="${CONDOR_SSH_KEY:-$HOME/.ssh/id_ed25519_condor}"
root="${CLUSTER_CI_ROOT:-/cluster/home/morri313/ci}"
run="${RUN_ID:-${GITHUB_RUN_ID:-$(date +%Y%m%d-%H%M%S)}}"
min_steps="${MIN_STEPS:-2}"

n=$(grep -c -E '[^[:space:]]' "$steps" || true)
if [ "$n" -lt "$min_steps" ]; then
  echo "refusing to submit $n step(s): need at least $min_steps; run it on the runner" >&2
  exit 71
fi

case "$key" in
  *[[:space:]]*) echo "CONDOR_SSH_KEY must not contain whitespace: $key" >&2; exit 64 ;;
esac
ssh_opts=(-o BatchMode=yes -o IdentitiesOnly=yes -i "$key")
rsync -a --mkpath --delete -e "ssh ${ssh_opts[*]}" "$checkout"/ "$head_host:$root/$run/"
rsync -a --mkpath -e "ssh ${ssh_opts[*]}" "$steps" "$head_host:$root/$run/.condor-steps"

# The remote script runs on the head: it writes the job and submits it once.
ssh "${ssh_opts[@]}" "$head_host" bash -s -- "$root/$run" "${REQUEST_CPUS:-4}" "${REQUEST_MEMORY:-8GB}" <<'REMOTE'
set -euo pipefail
dir=$1 cpus=$2 mem=$3
cd "$dir"
cat > .condor-run.sh <<'RUN'
#!/usr/bin/env bash
# Steps are read on fd 3 and each step gets /dev/null as stdin, so no step can
# eat the steps file (which dropped the first step's output).
cd "$1"; export TMPDIR="$1/.tmp"; mkdir -p "$TMPDIR"; rc=0; i=0
while IFS= read -r cmd <&3; do
  [ -n "${cmd//[[:space:]]/}" ] || continue
  i=$((i+1)); echo "::step $i: $cmd"
  bash -c "$cmd" < /dev/null || { rc=$?; echo "::step $i failed rc=$rc"; }
done 3< "$1/.condor-steps"
exit $rc
RUN
chmod +x .condor-run.sh
cat > .condor.sub <<SUB
universe = vanilla
executable = $dir/.condor-run.sh
arguments = $dir
getenv = False
request_cpus = $cpus
request_memory = $mem
output = $dir/out.log
error = $dir/err.log
log = $dir/condor.log
should_transfer_files = NO
queue 1
SUB
condor_submit .condor.sub
wait_rc=0
condor_wait condor.log || wait_rc=$?
[ ! -f out.log ] || cat out.log
[ ! -f err.log ] || cat err.log >&2
rv=
[ ! -f condor.log ] || rv=$(sed -n 's/.*return value \([0-9]*\)).*/\1/p' condor.log | tail -1)
if [ -n "$rv" ]; then
  case "$rv" in 70|71|255) exit 1 ;; esac
  exit "$rv"
fi
echo "job did not end normally (condor_wait status $wait_rc): see $dir/condor.log" >&2
exit 70
REMOTE
rc=$?
[ "$rc" -ne 255 ] || { echo "ssh to the cluster head failed" >&2; exit 70; }
exit "$rc"
