#!/usr/bin/env bash
# Compute the what-changed-since-the-last-reviewed-commit section (gha#709).
#
# A reviewer deriving the incremental range from comment history has
# misstated it -- naming one commit where the range held two -- and then
# approved on the strength of the misstated range (d-morrison/altdoc#125).
# So the workflow computes the range with git itself and hands it to the
# reviewer as authoritative.
#
# Usage: compute-incremental-range.sh <comments-json-file>
#
# The argument is a file holding ONE JSON array of the PR's issue comments
# (all pages merged; the caller runs `gh api --paginate | jq -s 'add // []'`).
# The prior reviewed commit is the last `Reviewed commit: <sha>` line in the
# most recent verdict-bearing bot comment -- the same population
# claude-code-review.yml's gather-context fetch step matches on.
#
# Runs inside the PR checkout. That checkout is fetch-depth: 1, so the prior
# SHA is normally NOT reachable at first: the script deepens the fetch in
# DEEPEN_STEP-commit increments (default 50) until the prior commit is an
# ancestor of HEAD, giving up -- and emitting nothing -- once DEEPEN_MAX
# (default 500) is reached or the repository is no longer shallow (a
# force-pushed-away or otherwise orphaned prior SHA). Without the deepening
# this feature is inert on every real round, which is exactly what gha#717's
# review round 1 measured.
#
# Stdout: the markdown section, or nothing when the range is not computable
# (first round, unparseable comments, unreachable prior, prior == head).
# Every not-computable path exits 0: this is an optional enrichment, and it
# must never redden the review job it feeds (the same rule the guard's
# denied-tools summary follows).
#
# Output uses INDENTED blocks rather than fences, so a commit subject
# carrying backticks cannot close the block early.
set -euo pipefail

COMMENTS_FILE="${1:?usage: compute-incremental-range.sh <comments-json-file> [head-sha] [count-file]}"
HEAD_PARAM="${2:-}"
COUNT_FILE="${3:-}"
DEEPEN_STEP="${DEEPEN_STEP:-50}"
DEEPEN_MAX="${DEEPEN_MAX:-500}"

write_count() {
  if [ -n "$COUNT_FILE" ]; then
    printf '%s\n' "$1" > "$COUNT_FILE"
  fi
}

write_count 0

if [ ! -f "$COMMENTS_FILE" ]; then
  exit 0
fi

# The prior reviewed commit is the last `Reviewed commit: <sha>` line in the
# most recent verdict-bearing bot comment that actually reviewed content --
# excluding rounds that were skipped, restated a prior clean verdict, or
# declared "no new diff" (gha#965).
PRIOR=$(python3 - "$COMMENTS_FILE" << 'EOF' 2>/dev/null || true
import json
import re
import sys

comments_file = sys.argv[1]
try:
    with open(comments_file, "r", encoding="utf-8", errors="replace") as f:
        comments = json.load(f)
except Exception:
    sys.exit(0)

if not isinstance(comments, list):
    sys.exit(0)

_FENCE_OPEN_RE = re.compile(r'^[ \t]*(`{3,}|~{3,})')
_FENCE_CLOSE_RE = re.compile(r'^[ \t]*(`{3,}|~{3,})[ \t]*$')
_BLOCKQUOTE_RE = re.compile(r'^[ \t]*>')

_CONTRACTIONS = [
    (r"\bisn['’]?t\b", "is not"),
    (r"\bwasn['’]?t\b", "was not"),
    (r"\baren['’]?t\b", "are not"),
    (r"\bweren['’]?t\b", "were not"),
    (r"\bdoesn['’]?t\b", "does not"),
    (r"\bdon['’]?t\b", "do not"),
    (r"\bdidn['’]?t\b", "did not"),
    (r"\bcan['’]?t\b", "can not"),
    (r"\bcannot\b", "can not"),
    (r"\bcouldn['’]?t\b", "could not"),
    (r"\bwon['’]?t\b", "will not"),
    (r"\bwouldn['’]?t\b", "would not"),
    (r"\bshouldn['’]?t\b", "should not"),
    (r"\bhasn['’]?t\b", "has not"),
    (r"\bhaven['’]?t\b", "have not"),
    (r"\bhadn['’]?t\b", "had not"),
    (r"\bain['’]?t\b", "is not"),
]

def strip_markup(text):
    out = []
    fence_char = ""
    fence_len = 0
    in_comment = False
    for line in text.splitlines():
        if in_comment:
            idx = line.find("-->")
            if idx == -1:
                continue
            line = line[idx + 3:]
            in_comment = False
        if fence_char:
            m = _FENCE_CLOSE_RE.match(line)
            if m and m.group(1)[0] == fence_char and len(m.group(1)) >= fence_len:
                fence_char = ""
                fence_len = 0
            continue
        m = _FENCE_OPEN_RE.match(line)
        if m:
            fence_char, fence_len = m.group(1)[0], len(m.group(1))
            continue
        if _BLOCKQUOTE_RE.match(line):
            continue
        while True:
            opener = line.find("<!--")
            if opener == -1:
                break
            closer = line.find("-->", opener + 2)
            if closer == -1:
                line = line[:opener]
                in_comment = True
                break
            line = line[:opener] + line[closer + 3:]
        line = re.sub(r'`[^`\n]+`', ' codespan ', line)
        for p, r in _CONTRACTIONS:
            line = re.sub(p, r, line, flags=re.IGNORECASE)
        line = re.sub(r"\b[A-Za-z0-9_]+['’](?:s|d|ll|m|re|ve)\b", " ", line)
        line = re.sub(r'"[^"\n]*"', " ", line)
        line = re.sub(r'“[^”\n]*”', " ", line)
        line = re.sub(r'‘[^’\n]*’', " ", line)
        line = re.sub(r"(?<!\w)'[^'\n]*'(?!\w)", " ", line)
        out.append(line)
    return "\n".join(out)

_NO_DIFF_CANDIDATE_RE = re.compile(
    r"(?i)\b("
    r"verdict\b[: \t*_#-]*\bskipped|"
    r"(?:(?P<determiner>a|an|the|this|that|any|such)\s+)?no\s+new\s+diff(?:\s+(?P<noun>claim|claims|bug|bugs|issue|issues|hazard|hazards|case|cases|check|checks|guard|guards|pattern|patterns|rule|rules|logic|detection|handling|reproduction|finding|findings|observation|observations|skip|skips))?|"
    r"no\s+new\s+content\s+(?:exists|versus|since|in\s+this\s+pr)|"
    r"no\s+new\s+commits(?!\s+(?:claim|bug|issue|hazard|case|check|guard|pattern|rule|logic))|"
    r"no\s+substantive\s+(?:logic\s+)?changes(?!\s+(?:claim|bug|issue|hazard|case|check|guard|pattern|rule|logic))|"
    r"head\s+has\s+not\s+moved|"
    r"unchanged\s+head(?!\s+(?:claim|bug|issue|hazard|case|check|guard|pattern|rule|logic))|"
    r"all\s+(?:content|changes|code).*(?:already\s+reviewed|reviewed\s+in\s+(?:the\s+)?(?:prior|previous)\s+round)|"
    r"already\s+reviewed\s+in\s+(?:the\s+)?(?:prior|previous)\s+round|"
    r"no\s+commits\s+have\s+landed|"
    r"reaffirmed.*no\s+new\s+findings"
    r")\b"
)

def _has_no_diff_claim(stripped_text):
    for m in _NO_DIFF_CANDIDATE_RE.finditer(stripped_text):
        if m.group("determiner") or m.group("noun"):
            continue
        return True
    return False

_PAYLOAD_RE = re.compile(r'<!--\s*review-data:\s*(\{.*?\})\s*-->', re.DOTALL)
_REVIEWED_COMMIT_RE = re.compile(r'Reviewed commit:\s*([0-9a-f]{40})')

prior = ""
for c in comments:
    if not isinstance(c, dict):
        continue
    user = c.get("user") or {}
    login = user.get("login") or ""
    if login not in ("github-actions[bot]", "claude[bot]"):
        continue
    body = c.get("body") or ""
    if not re.search(r'### (Code Review|Verdict)', body):
        continue

    # Check structured payload verdict
    pm = _PAYLOAD_RE.search(body)
    if pm:
        try:
            pdata = json.loads(pm.group(1))
            if pdata.get("verdict", "").strip().upper() in ("SKIPPED", "UNREVIEWED_COMMITS_SKIPPED", "UNREVIEWED-COMMITS-SKIPPED"):
                continue
        except Exception:
            pass

    # Check stripped prose for no-diff claims anywhere in the comment body.
    # Testing the whole stripped body avoids accepting a stale comment with a pre-heading
    # no-diff claim as a valid reviewed boundary (which would wrongly zero out
    # unreviewed-commits and disable the classify-review-verdict fail-closed guard; gha#965).
    if _has_no_diff_claim(strip_markup(body)):
        continue

    matches = _REVIEWED_COMMIT_RE.findall(body)
    if matches:
        prior = matches[-1]

if prior:
    print(prior)
EOF
)

HEAD_NOW="${HEAD_PARAM:-$(git rev-parse HEAD 2>/dev/null || true)}"

if [ -z "$PRIOR" ] || [ -z "$HEAD_NOW" ] || [ "$PRIOR" = "$HEAD_NOW" ]; then
  exit 0
fi

# Deepen a shallow checkout until the prior commit is an ancestor of HEAD.
# Order matters inside the loop: once the repository is no longer shallow,
# an un-reached prior is orphaned (force-push) and no fetch will change
# that -- give up rather than loop.
deepened=0
until git merge-base --is-ancestor "$PRIOR" "$HEAD_NOW" 2>/dev/null; do
  if [ "$(git rev-parse --is-shallow-repository 2>/dev/null)" != "true" ]; then
    exit 0
  fi
  if [ "$deepened" -ge "$DEEPEN_MAX" ]; then
    exit 0
  fi
  # Deepen against the checked-out SHA explicitly: a bare
  # `git fetch --deepen` covers only the default refs/heads/* refspec, and
  # the ordinary pull_request checkout is refs/pull/<n>/merge -- not on any
  # branch -- so the bare form never reaches the prior there (gha#717
  # review round 2, confirmed against both checkout topologies).
  git fetch -q --deepen="$DEEPEN_STEP" origin "$HEAD_NOW" 2>/dev/null || git fetch -q --deepen="$DEEPEN_STEP" 2>/dev/null || exit 0
  deepened=$((deepened + DEEPEN_STEP))
done

LOG=$(git log --oneline --no-merges "$PRIOR..$HEAD_NOW" 2>/dev/null | sed 's/^/    /' || true)
if [ -z "$LOG" ]; then
  exit 0
fi

COMMIT_COUNT=$(git rev-list --count --no-merges "$PRIOR..$HEAD_NOW" 2>/dev/null || echo "0")
write_count "$COMMIT_COUNT"

STAT=$(git diff --stat "$PRIOR" "$HEAD_NOW" 2>/dev/null | sed 's/^/    /' || true)

printf '%s\n' \
  '## What changed since the last review round (computed)' \
  '' \
  "The prior round reviewed commit \`$PRIOR\`; this checkout's head is \`$HEAD_NOW\`. The range below was computed by the workflow with git itself. When you describe what changed since the last round, describe THIS range rather than deriving your own, and examine every commit and file in it:" \
  '' \
  "    \$ git log --oneline --no-merges ${PRIOR:0:8}..${HEAD_NOW:0:8}" \
  "$LOG" \
  '' \
  "    \$ git diff --stat ${PRIOR:0:8} ${HEAD_NOW:0:8}" \
  "$STAT" \
  '' \
  "**Mandatory review requirement:** $COMMIT_COUNT unreviewed commit(s) exist in this range (${PRIOR:0:8}..${HEAD_NOW:0:8}). You MUST examine these commits and the diff above. Every commit in this range must be thoroughly reviewed."
