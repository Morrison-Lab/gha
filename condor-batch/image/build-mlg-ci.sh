#!/usr/bin/env bash
# Build mlg-ci.sif from Morrison-Lab/mlg at a ref (gha#2006).
#
# Usage: build-mlg-ci.sh [ref] [image-dir]
#   ref        mlg branch, tag or commit to build from (default: main)
#   image-dir  directory holding lds-ci.sif and receiving mlg-ci.sif
#              (default: /home/morri313/ci/image, the copy cf463-02 reads)
#
# Run it on cf463-02 with Apptainer and read access to Morrison-Lab/mlg, which
# is private, so git needs credentials for github.com. It rebuilds the image
# from the ref's renv.lock, so rerun it whenever renv.lock changes; the image
# is stale otherwise. A condor-batch job that lands on a CSCI desktop-pool head
# reads the image from the runner (the action's image-file input), which is the
# default image-dir. A job on a CSE cluster head reads
# /cluster/home/morri313/ci/image/mlg-ci.sif instead, and cf463-02 cannot see
# /cluster, so copy the finished image there from a machine that mounts it.
#
# After the build it renders mlg in both profiles inside the new image and
# runs mlg's own check, as the CI job does. /opt/TinyTeX is read-only in a job,
# so Quarto cannot install a missing LaTeX package at render time; the test
# render makes such a package fail the build here instead of a CI run. If it
# does, add the package to a tlmgr install line in mlg-ci.def, as
# epi204-ci.def does (gha#1660), and rebuild.
set -euo pipefail

ref="${1:-main}"
image_dir="${2:-/home/morri313/ci/image}"
# Resolve image-dir now: the script cd's into a temp directory below, where a
# relative path would no longer name it.
image_dir="$(cd "$image_dir" && pwd)"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

git clone --quiet https://github.com/Morrison-Lab/mlg.git "$work/mlg"
git -C "$work/mlg" checkout --quiet "$ref"
# Only the public macros submodule: the render needs it, and mln (lds) is
# private and unused by the render.
git -C "$work/mlg" submodule update --quiet --init latex-macros
sha="$(git -C "$work/mlg" rev-parse HEAD)"

cp "$work/mlg/renv.lock" "$work/renv.lock"
cp "$here/mlg-ci.def" "$work/mlg-ci.def"
# The recipe bootstraps from a local lds-ci.sif, so build next to it.
cp "$image_dir/lds-ci.sif" "$work/lds-ci.sif"

cd "$work"
apptainer build mlg-ci.sif mlg-ci.def

# Test render, with the same container flags condor-batch uses.
mkdir -p "$work/mlg/.home" "$work/tmp"
apptainer exec --containall --bind "$work/mlg:/work" --bind "$work/tmp:/tmp" \
  --pwd /work --home /work/.home --env LANG=C.UTF-8 --env TMPDIR=/tmp \
  mlg-ci.sif bash -c 'set -e; quarto render; quarto render --profile solution; python3 tools/check_student_copy.py'

mv mlg-ci.sif "$image_dir/mlg-ci.sif"
echo "Built $image_dir/mlg-ci.sif from mlg $sha"
