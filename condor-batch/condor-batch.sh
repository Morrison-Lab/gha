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
# WWU CS IT asks that jobs avoid heavy home-directory I/O and use HTCondor file
# transfer. So the checkout is packed into ONE tarball on the runner, copied to
# $CLUSTER_CI_ROOT/<run>/ on the cluster home (the cf463 home is not visible to
# the execute nodes), and HTCondor transfers it, with the steps file, into the
# execute node's scratch directory. The job unpacks it there and runs every
# step there, with TMPDIR, the uv caches and the contained home all in scratch.
# Nothing the steps write goes to the cluster home, and nothing is transferred
# back except the log. The log streams back when the job ends; the exit code is
# the last failing step's, or 0.
#
# Exit 70 means the cluster could not run the job normally (ssh failed, or the
# job was held or aborted) and 71 means too few steps; the caller may rerun the
# steps on the runner for those two only. A step's own exit 70, 71 or 255 is
# reported as 1, so no step failure can look like an infrastructure failure.
#
# Environment: CONDOR_HEAD (default cse-head.cluster.cs.wwu.edu),
# CONDOR_SSH_KEY (default ~/.ssh/id_ed25519_condor), CLUSTER_CI_ROOT
# (default /cluster/home/morri313/ci), RUN_ID (default GITHUB_RUN_ID or the
# time), MIN_STEPS, REQUEST_CPUS (default 4), REQUEST_MEMORY (default 8GB),
# REQUEST_DISK (default 20GB: scratch space for the unpacked checkout, the uv
# caches and render outputs),
# RSYNC_EXCLUDE (default none: space-separated tar exclude patterns, such as
# .git, for paths the job does not need; the name is kept from when the copy
# was an rsync),
# CONDOR_IMAGE (default none: a path to an Apptainer image on the cluster home,
# read in place; when set, every step runs inside it with the unpacked checkout
# bound at /work, and the home, TMPDIR and uv caches under /work because the
# contained /tmp and home are small tmpfs).
# The run directory (tarball, steps file and log) is deleted after a normal job
# end (any step exit code), to keep the cluster home inside its quota; it is
# kept when the job did not end normally, so condor.log stays readable.
#
# Exit codes: the last failing step's code, or 0; 71 = refused (too few steps);
# 70 = the cluster could not run the job normally (copy or ssh failed, or the
# job was held, removed, aborted, or condor_wait failed); 64 = CONDOR_SSH_KEY
# contains whitespace.
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
transfer_failed() { echo "copying to the cluster head failed" >&2; exit 70; }
# A job that did not end normally keeps its run directory, and enough of them
# fill the cluster home's quota, after which every copy fails ("Disk quota
# exceeded") and every later run falls back to the runner. When the first copy
# fails, remove the run directories older than STALE_MINUTES (default 60, well
# past the longest job) and copy once more. Only digit-led names are removed,
# so an image directory beside them is never touched.
# RSYNC_EXCLUDE (space-separated patterns) keeps paths such as .git, whose pack
# files are the largest part of a checkout, out of the tarball.
excludes=()
read -ra patterns <<< "${RSYNC_EXCLUDE:-}"
for pattern in ${patterns[@]+"${patterns[@]}"}; do excludes+=("--exclude=$pattern"); done
pack_dir=$(mktemp -d)
trap 'rm -rf "$pack_dir"' EXIT
tar -czf "$pack_dir/checkout.tar.gz" ${excludes[@]+"${excludes[@]}"} -C "$checkout" .
copied=0
for attempt in 1 2; do
  if rsync -a --mkpath -e "ssh ${ssh_opts[*]}" "$pack_dir/checkout.tar.gz" "$head_host:$root/$run/checkout.tar.gz" &&
    rsync -a --mkpath -e "ssh ${ssh_opts[*]}" "$steps" "$head_host:$root/$run/.condor-steps"; then
    copied=1
    break
  fi
  [ "$attempt" = 1 ] || break
  echo "copy failed; removing run directories older than ${STALE_MINUTES:-60} minutes from $root" >&2
  ssh "${ssh_opts[@]}" "$head_host" bash -s -- "$root" "${STALE_MINUTES:-60}" <<'SWEEP' || true
find "$1" -mindepth 1 -maxdepth 1 -type d -name '[0-9]*' -mmin +"$2" -exec rm -rf {} +
SWEEP
done
[ "$copied" = 1 ] || transfer_failed

# A cancelled workflow run kills this script, not the cluster job, which keeps
# running and keeps its run directory (the quota filled this way on
# 2026-11-03). On SIGTERM, SIGINT or SIGHUP, remove the job and the directory.
clean_script='cd "$1" 2>/dev/null || exit 0
[ ! -f .cluster-id ] || condor_rm "$(cat .cluster-id)" || true
sleep 3
cd / && rm -rf "$1"'
trap 'printf "%s\n" "$clean_script" | ssh "${ssh_opts[@]}" "$head_host" bash -s -- "$root/$run" || true; rm -rf "$pack_dir"; exit 143' TERM INT HUP

# The remote script runs on the head: it writes the job and submits it once.
rc=0
ssh "${ssh_opts[@]}" "$head_host" bash -s -- "$root/$run" "${REQUEST_CPUS:-4}" "${REQUEST_MEMORY:-8GB}" "${REQUEST_DISK:-20GB}" "${CONDOR_IMAGE:-}" <<'REMOTE' || rc=$?
set -euo pipefail
dir=$1 cpus=$2 mem=$3 disk=$4 image=${5:-}
cd "$dir"
cat > .condor-run.sh <<'RUN'
#!/usr/bin/env bash
# Runs in the execute node's scratch directory (HTCondor's working directory):
# the tarball and the steps file were transferred here, and everything the
# steps write stays here until HTCondor deletes it when the job ends.
# Steps are read on fd 3 and each step gets /dev/null as stdin, so no step can
# eat the steps file (which dropped the first step's output).
img=${1:-}; scratch=$PWD
mkdir -p "$scratch/work/.home" "$scratch/.tmp"
tar -xzf checkout.tar.gz -C "$scratch/work"
export TMPDIR="$scratch/.tmp"; cd "$scratch/work"; rc=0; i=0
wrap=()
[ -z "$img" ] || wrap=(apptainer exec --containall --bind "$scratch/work:/work" --bind "$TMPDIR:/tmp" --pwd /work --home /work/.home --env LANG=C.UTF-8 --env TMPDIR=/tmp --env UV_CACHE_DIR=/work/.uvcache --env UV_PYTHON_INSTALL_DIR=/work/.uvpy "$img")
while IFS= read -r cmd <&3; do
  [ -n "${cmd//[[:space:]]/}" ] || continue
  i=$((i+1)); echo "::step $i: $cmd"
  "${wrap[@]}" bash -c "$cmd" < /dev/null || { rc=$?; echo "::step $i failed rc=$rc"; }
done 3< "$scratch/.condor-steps"
exit $rc
RUN
chmod +x .condor-run.sh
cat > .condor.sub <<SUB
universe = vanilla
executable = $dir/.condor-run.sh
arguments = $image
getenv = False
request_cpus = $cpus
request_memory = $mem
request_disk = $disk
output = $dir/out.log
error = $dir/err.log
log = $dir/condor.log
should_transfer_files = YES
when_to_transfer_output = ON_EXIT
transfer_input_files = $dir/checkout.tar.gz, $dir/.condor-steps
transfer_output_files = ""
queue 1
SUB
condor_submit .condor.sub | tee .submit.out
sed -n 's/.*submitted to cluster \([0-9][0-9]*\)\..*/\1/p' .submit.out > .cluster-id
wait_rc=0
condor_wait condor.log || wait_rc=$?
[ ! -f out.log ] || cat out.log
[ ! -f err.log ] || cat err.log >&2
rv=
[ ! -f condor.log ] || rv=$(sed -n 's/.*return value \([0-9]*\)).*/\1/p' condor.log | tail -1)
if [ -n "$rv" ]; then
  cd / && rm -rf "$dir" || echo "could not remove $dir" >&2
  case "$rv" in 70|71|255) exit 1 ;; esac
  exit "$rv"
fi
echo "job did not end normally (condor_wait status $wait_rc): see $dir/condor.log" >&2
exit 70
REMOTE
trap - TERM INT HUP
[ "$rc" -ne 255 ] || { echo "ssh to the cluster head failed" >&2; exit 70; }
exit "$rc"
