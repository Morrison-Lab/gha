#!/usr/bin/env bash
# Append one sample of a self-hosted runner host's load, memory and swap to a log,
# with the processes holding the most memory, so an overload (high load, full
# swap, "lost communication" failures; gha#1736) can be read back without root.
# `journalctl` and `dmesg` need sudo on the lab hosts, and this needs none.
#
# Usage, from the runner user's crontab (one line per host, every minute):
#   * * * * * bash <gha checkout>/scripts/sample-runner-load.sh
#
# Writes to SAMPLE_LOG (default ~/runner-load.log), one line per sample:
#   <UTC time> load=<1m> <5m> <15m> mem_avail_mb=<n> swap_used_mb=<n> top=<comm:rss_mb,...>
# When the log passes SAMPLE_MAX_KB (default 5120), it is moved to SAMPLE_LOG.1,
# replacing the previous copy, so the two files hold about a day at one sample a minute.
# SAMPLE_TOP (default 5) is the number of processes listed.
#
# SAMPLE_LOADAVG, SAMPLE_MEMINFO and SAMPLE_PS replace /proc/loadavg, /proc/meminfo
# and the `ps` listing for the offline tests.
set -euo pipefail

log="${SAMPLE_LOG:-$HOME/runner-load.log}"
max_kb="${SAMPLE_MAX_KB:-5120}"
top_n="${SAMPLE_TOP:-5}"
loadavg="${SAMPLE_LOADAVG:-/proc/loadavg}"
meminfo="${SAMPLE_MEMINFO:-/proc/meminfo}"

for n in "$max_kb" "$top_n"; do
  case "$n" in
    '' | *[!0-9]*)
      echo "::warning::sample-runner-load: '$n' is not a whole number; using the default." >&2
      max_kb=5120
      top_n=5
      ;;
  esac
done

load=$(awk '{ print $1 " " $2 " " $3 }' "$loadavg")
mem_avail_mb=$(awk '/^MemAvailable:/ { printf "%d", $2 / 1024 }' "$meminfo")
swap_used_mb=$(awk '/^SwapTotal:/ { t = $2 } /^SwapFree:/ { f = $2 } END { printf "%d", (t - f) / 1024 }' "$meminfo")

# Command name and resident memory in MB, largest first.
if [ -n "${SAMPLE_PS:-}" ]; then
  listing=$(cat "$SAMPLE_PS")
else
  listing=$(ps -eo rss=,comm= --sort=-rss)
fi
top=$(printf '%s\n' "$listing" | head -n "$top_n" | awk '{ printf "%s%s:%d", (NR > 1 ? "," : ""), $2, $1 / 1024 }')

if [ -f "$log" ] && [ "$(du -k "$log" | cut -f1)" -ge "$max_kb" ]; then
  mv -f "$log" "$log.1"
fi
printf '%s load=%s mem_avail_mb=%s swap_used_mb=%s top=%s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$load" "$mem_avail_mb" "$swap_used_mb" "$top" >> "$log"
