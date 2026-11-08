#!/usr/bin/env bash
# Build epi204-ci.sif from epi204 at a ref (gha#1638).
#
# Usage: build-epi204-ci.sh [ref] [image-dir]
#   ref        epi204 branch, tag or commit to build from (default: main)
#   image-dir  directory holding lds-ci.sif and receiving epi204-ci.sif
#              (default: /cluster/home/morri313/ci/image)
#
# Run it on cf463-02 with Apptainer and push access to Morrison-Lab/epi204.
# It rebuilds the image from the ref's renv.lock, so rerun it whenever renv.lock
# changes; the image is stale otherwise.
set -euo pipefail

ref="${1:-main}"
image_dir="${2:-/cluster/home/morri313/ci/image}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

git clone --quiet https://github.com/Morrison-Lab/epi204.git "$work/epi204"
git -C "$work/epi204" checkout --quiet "$ref"
sha="$(git -C "$work/epi204" rev-parse HEAD)"

cp "$work/epi204/renv.lock" "$work/renv.lock"
tar -czf "$work/epi204.tar.gz" -C "$work" --exclude=.git epi204
cp "$here/epi204-ci.def" "$work/epi204-ci.def"
# The recipe bootstraps from a local lds-ci.sif, so build next to it.
cp "$image_dir/lds-ci.sif" "$work/lds-ci.sif"

cd "$work"
apptainer build epi204-ci.sif epi204-ci.def
mv epi204-ci.sif "$image_dir/epi204-ci.sif"
echo "Built $image_dir/epi204-ci.sif from epi204 $sha"
