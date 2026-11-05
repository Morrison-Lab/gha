"""Summarize per-file render times, slowest first."""


def timing_summary(timings, top=25):
    """Markdown for the `top` slowest renders plus per-format totals.

    `timings` is a list of (file, format, seconds) tuples.  The per-format
    totals show where a long publish spends its time (gha#1420 asks to split
    the formats into parallel jobs; this shows whether that would help).
    """
    totals = {}
    counts = {}
    for _, fmt, seconds in timings:
        totals[fmt] = totals.get(fmt, 0.0) + seconds
        counts[fmt] = counts.get(fmt, 0) + 1
    lines = ["### Per-file render times", "",
             "| Format | Files | Total (s) |", "| --- | ---: | ---: |"]
    for fmt in sorted(totals):
        lines.append(f"| {fmt} | {counts[fmt]} | {totals[fmt]:.0f} |")
    lines += ["", f"Slowest {min(top, len(timings))} renders:", "",
              "| File | Format | Seconds |", "| --- | --- | ---: |"]
    for rel, fmt, seconds in sorted(timings, key=lambda t: -t[2])[:top]:
        lines.append(f"| {rel} | {fmt} | {seconds:.0f} |")
    return "\n".join(lines) + "\n"
