#!/usr/bin/env bash
# Sourced by condor-batch.sh (gha#2093); kept apart so each script
# defines one function.
# A request size as HTCondor reads it: a bare number is MB for memory and KiB
# for disk; K, M, G and T suffixes (with or without B or iB) are binary units.
# Prints the size in the given unit (1 = KiB, 1024 = MiB), or 0 when it cannot
# be read, which leaves that resource out of the fit.
request_size() {
  local value="${1// /}" bare_kib="$2" unit_kib="$3" num suffix kib
  value="${value^^}"
  [[ "$value" =~ ^([0-9]+)([KMGT]?)I?B?$ ]] || { echo 0; return; }
  num="${BASH_REMATCH[1]}" suffix="${BASH_REMATCH[2]}"
  case "$suffix" in
    '') kib=$(( 10#$num * bare_kib )) ;;
    K) kib=$(( 10#$num )) ;;
    M) kib=$(( 10#$num * 1024 )) ;;
    G) kib=$(( 10#$num * 1024 * 1024 )) ;;
    T) kib=$(( 10#$num * 1024 * 1024 * 1024 )) ;;
  esac
  echo $(( kib / unit_kib ))
}
