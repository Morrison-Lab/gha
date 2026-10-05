#!/usr/bin/env bash
# Compute the what-changed-since-the-last-reviewed-commit section (gha#709).
#
# A reviewer deriving the incremental range from comment history has
# misstated it -- naming one commit where the range held two -- and then
# approved on the strength of the misstated range (d-morrison/altdoc#125).
# So the workflow computes the range with git itself and hands it to the
# reviewer as authoritative.
#
# Usage: compute-incremental-range.sh <comments-json-file> [head-sha] [count-file] [base-ref] [default-branch]
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
# ancestor of HEAD and no commit in PRIOR..HEAD is a shallow boundary (a
# merge of the base brings in commits the walk to the prior alone never
# deepens, which undercounted the range), giving up once DEEPEN_MAX
# (default 500) is reached or the repository is no longer shallow -- and
# emitting nothing if the prior is still unreachable then (a
# force-pushed-away or otherwise orphaned prior SHA). Without the deepening
# this feature is inert on every real round, which is exactly what gha#717's
# review round 1 measured.
#
# Base-branch commits are not PR commits (observed on Morrison-Lab/lds#369).
# A PR branch that merges its base ("Update branch") after a reviewed round
# carries the base's own commits -- squash merges of OTHER PRs -- into
# PRIOR..HEAD. They contribute nothing to the PR's diff, so the reviewer
# truthfully reports "no new content", which classify-review-verdict.sh's
# gha#965 guard reads, with a nonzero count, as a skipped review; such a
# round stamps no `Reviewed commit:` boundary, so the next round's range
# grows instead of moving and the PR can never go green. When BASE_REF (arg
# 4, or the env var) names the PR's base AND equals DEFAULT_BRANCH (arg 5,
# or the env var), the repository's default branch, the script fetches it
# and counts only commits NOT reachable from it.
#
# Only the default branch qualifies. A PR author can push an unreviewed
# commit to a branch of their own, retarget the PR at it, push the commit
# to the PR, and retarget back; retargeting does not re-run the review, so
# excluding commits reachable from an arbitrary base would let that commit
# through unreviewed. Moving the default branch takes write access to it.
#
# Every other case keeps the full PRIOR..HEAD count (fail closed): an empty
# or malformed base ref, a base that is not the default branch, a base that
# cannot be fetched, or a base that never meets HEAD's history within
# DEEPEN_MAX.
#
# Merges stay checked once base commits are excluded: a merge whose result
# differs from git's automatic re-merge of its parents (a conflict resolved
# by taking one side, a base change reverted) counts as unreviewed, and so
# does one the re-merge cannot be computed for.
#
# A range still cut by a shallow boundary at DEEPEN_MAX has no knowable full
# count: the script then excludes nothing, counts the visible part (at least
# 1, so the guard can fire) and says the range is incomplete.
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

COMMENTS_FILE="${1:?usage: compute-incremental-range.sh <comments-json-file> [head-sha] [count-file] [base-ref] [default-branch]}"
HEAD_PARAM="${2:-}"
COUNT_FILE="${3:-}"
BASE_REF="${4:-${BASE_REF:-}}"
DEFAULT_BRANCH="${5:-${DEFAULT_BRANCH:-}}"
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

_DETERMINER_WORDS = r"a|an|the|this|that|any|such|every|each"
_NOUN_WORDS = (
    r"claim|claims|bug|bugs|issue|issues|hazard|hazards|case|cases|"
    r"check|checks|guard|guards|pattern|patterns|rule|rules|logic|"
    r"detection|handling|reproduction|finding|findings|observation|observations|"
    r"skip|skips|phrase|phrases|trigger|triggers|heuristic|heuristics|behavior|"
    r"scenario|scenarios|discussion|discussions"
)

_CORE_PATTERNS = (
    r"verdict\b[: \t*_#-]*\bskipped|"
    r"no\s+new\s+diff|"
    r"no\s+new\s+content\s+(?:exists|versus|since|in\s+this\s+pr)|"
    r"no\s+new\s+commits|"
    r"no\s+substantive\s+(?:logic\s+)?changes|"
    r"head\s+has\s+not\s+moved|"
    r"unchanged\s+head|"
    r"all\s+(?:content|changes|code).*(?:already\s+reviewed|reviewed\s+in\s+(?:the\s+)?(?:prior|previous)\s+round)|"
    r"already\s+reviewed\s+in\s+(?:the\s+)?(?:prior|previous)\s+round(?!\s+(?:is|was|are|were)?\s*not\b)|"
    r"no\s+commits\s+have\s+landed(?!\s+(?:and\s+stops|(?:since\s+[^\n.,;]+?\s+)?that\s+were\s+(?:skipped|missed|unreviewed)\b))|"
    r"reaffirmed.*no\s+new\s+findings"
)

_NO_DIFF_CANDIDATE_RE = re.compile(
    rf"(?i)\b(?:(?P<determiner>{_DETERMINER_WORDS})\s+)?(?:{_CORE_PATTERNS})(?:\s+(?P<noun>{_NOUN_WORDS}))?\b"
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

# Base exclusion is eligible only when the base IS the repository's default
# branch, and its name is a valid branch name. A PR author can retarget a PR
# at a branch they pushed an unreviewed commit to, and retargeting does not
# re-run the review; the default branch takes write access to move.
BASE_TRACK="refs/gha-incremental-range/base"
BASE_OK=""
if [ -n "$BASE_REF" ] && [ "$BASE_REF" = "$DEFAULT_BRANCH" ] \
   && git check-ref-format "refs/heads/$BASE_REF" 2>/dev/null; then
  # Fetch the base BEFORE the deepen loop, at depth 1 on a shallow checkout,
  # so the loop below deepens it together with HEAD. Fetching it afterwards
  # at a fixed depth placed new shallow boundaries inside history the loop
  # had already deepened, shortening the range. On a full clone no depth is
  # passed, since --depth would make the repository shallow.
  depth_arg=()
  if [ "$(git rev-parse --is-shallow-repository 2>/dev/null)" = "true" ]; then
    depth_arg=(--depth=1)
  fi
  if git fetch -q --no-tags ${depth_arg[@]+"${depth_arg[@]}"} origin \
       "+refs/heads/$BASE_REF:$BASE_TRACK" 2>/dev/null; then
    BASE_OK=1
  fi
fi

# The range is complete when the prior is an ancestor of HEAD and no commit
# in PRIOR..HEAD is a shallow boundary (a boundary hides its parents, which
# can belong to the range: merging the base brings in commits the
# first-parent walk to the prior never deepens).
range_complete() {
  git merge-base --is-ancestor "$PRIOR" "$HEAD_NOW" 2>/dev/null || return 1
  local shallow_file
  shallow_file=$(git rev-parse --git-path shallow 2>/dev/null || true)
  if [ -n "$shallow_file" ] && [ -s "$shallow_file" ] \
     && git rev-list "$PRIOR..$HEAD_NOW" 2>/dev/null | grep -qxF -f "$shallow_file"; then
    return 1
  fi
  return 0
}
# The range is ready when it is complete and, when the base was fetched,
# the base meets HEAD's history.
range_ready() {
  range_complete || return 1
  if [ -n "$BASE_OK" ] && ! git merge-base "$HEAD_NOW" "$BASE_TRACK" >/dev/null 2>&1; then
    return 1
  fi
  return 0
}

# Deepen a shallow checkout until the range is ready. Once the repository
# is no longer shallow, nothing a fetch does will change the answer.
deepened=0
until range_ready; do
  if [ "$(git rev-parse --is-shallow-repository 2>/dev/null)" != "true" ] \
     || [ "$deepened" -ge "$DEEPEN_MAX" ]; then
    break
  fi
  # Deepen against the checked-out SHA explicitly: a bare
  # `git fetch --deepen` covers only the default refs/heads/* refspec, and
  # the ordinary pull_request checkout is refs/pull/<n>/merge -- not on any
  # branch -- so the bare form never reaches the prior there (gha#717
  # review round 2, confirmed against both checkout topologies).
  #
  # Deepen the base by its tip SHA too, never by its refspec. A refspec
  # whose remote value equals the local ref is up to date, and git 2.55
  # sends no want for it, so --deepen never moved the base's boundary: a
  # base that had advanced past the merged point never met HEAD, and every
  # round excluded nothing (git 2.43 still deepened it). An explicit SHA is
  # always sent as a want, as HEAD_NOW already is.
  wants=("$HEAD_NOW")
  if [ -n "$BASE_OK" ]; then
    base_sha=$(git rev-parse -q --verify "$BASE_TRACK^{commit}" 2>/dev/null || true)
    if [ -n "$base_sha" ]; then
      wants+=("$base_sha")
    fi
  fi
  shallow_before=$(cat "$(git rev-parse --git-path shallow 2>/dev/null)" 2>/dev/null || true)
  git fetch -q --no-tags --deepen="$DEEPEN_STEP" origin "${wants[@]}" 2>/dev/null \
    || git fetch -q --deepen="$DEEPEN_STEP" 2>/dev/null || break
  deepened=$((deepened + DEEPEN_STEP))
  # A deepen that moved no boundary will not move one next time either:
  # stop rather than spin to DEEPEN_MAX (which, at a small DEEPEN_STEP, is
  # hundreds of fetches).
  shallow_after=$(cat "$(git rev-parse --git-path shallow 2>/dev/null)" 2>/dev/null || true)
  if [ "$shallow_after" = "$shallow_before" ]; then
    break
  fi
done

# An unreachable prior (orphaned by a force-push, or past DEEPEN_MAX): emit
# nothing, as before.
if ! git merge-base --is-ancestor "$PRIOR" "$HEAD_NOW" 2>/dev/null; then
  exit 0
fi

# The prior is reachable but a shallow boundary still sits inside the range
# (DEEPEN_MAX reached): only part of the range is visible, so its count is
# a lower bound. Say so, exclude nothing, and keep the count nonzero.
INCOMPLETE=""
if ! range_complete; then
  INCOMPLETE=1
fi

# Exclude base commits only from a complete range whose base meets HEAD;
# otherwise keep the full visible count (fail closed).
BASE_TIP=""
if [ -z "$INCOMPLETE" ] && [ -n "$BASE_OK" ] && range_ready; then
  BASE_TIP=$(git rev-parse -q --verify "$BASE_TRACK^{commit}" 2>/dev/null || true)
fi

RANGE=("$PRIOR..$HEAD_NOW")
if [ -n "$BASE_TIP" ]; then
  RANGE+=(--not "$BASE_TIP")
fi

ALL_COUNT=$(git rev-list --count --no-merges "$PRIOR..$HEAD_NOW" 2>/dev/null || echo "0")
if [ "$ALL_COUNT" = "0" ] && [ -z "$INCOMPLETE" ]; then
  exit 0
fi

OWN_COUNT=$(git rev-list --count --no-merges "${RANGE[@]}" 2>/dev/null || echo "$ALL_COUNT")
BASE_COUNT=$((ALL_COUNT - OWN_COUNT))

# Merge commits are not counted by --no-merges, and while every base commit
# was counted that was harmless: a merge of the base brought at least one
# counted commit with it. Once base commits are excluded, a merge is the
# only place a bad resolution shows -- a conflict resolved by taking one
# side, or a base change silently reverted to the PR's old content. A
# combined diff (--cc) hides both, since the result equals one parent. So
# compare each merge with git's own automatic re-merge of its parents
# (`git show --remerge-diff`, git >= 2.36): a merge whose result differs
# from it in any file counts as unreviewed. A merge the re-merge cannot be
# computed for counts too (fail closed).
MERGE_FLAGGED=0
MERGE_LINES=()
if [ -n "$BASE_TIP" ]; then
  while IFS= read -r m; do
    [ -n "$m" ] || continue
    MERGE_LINES+=("    $(git log --oneline -1 "$m" 2>/dev/null || echo "$m")")
    # remerge-diff does not handle octopus merges (git 2.43 says so in a
    # warning on STDOUT, which would otherwise be listed as a file name, and
    # a git that moved it to stderr would leave the output empty -- an
    # uncounted merge). Detect them by parent count and always count them.
    parents=$(git rev-list --parents -n1 "$m" 2>/dev/null | wc -w)
    if [ "$parents" -gt 3 ]; then
      MERGE_FLAGGED=$((MERGE_FLAGGED + 1))
      MERGE_LINES+=("        (octopus merge: re-merge not supported; examine by hand; counted)")
    elif [ "$parents" -lt 3 ]; then
      MERGE_FLAGGED=$((MERGE_FLAGGED + 1))
      MERGE_LINES+=("        (parents could not be read: examine this merge by hand; counted)")
    elif files=$(git show --remerge-diff --format= --name-only "$m" 2>/dev/null) \
         && ! grep -q '^diff: warning:' <<<"$files"; then
      files=$(sed '/^$/d' <<<"$files")
      if [ -n "$files" ]; then
        MERGE_FLAGGED=$((MERGE_FLAGGED + 1))
        while IFS= read -r f; do
          MERGE_LINES+=("        $f")
        done <<<"$files"
      else
        MERGE_LINES+=("        (matches git's automatic merge of its parents)")
      fi
    else
      MERGE_FLAGGED=$((MERGE_FLAGGED + 1))
      MERGE_LINES+=("        (re-merge could not be computed: examine this merge by hand; counted)")
    fi
  done < <(git rev-list --merges "${RANGE[@]}" 2>/dev/null || true)
fi

COMMIT_COUNT=$((OWN_COUNT + MERGE_FLAGGED))
# Backstop: a boundary commit inside the range has its parents hidden, so
# rev-list already counts it (even a merge reads as parentless) and the
# visible count is at least 1; keep that true whatever git does.
if [ -n "$INCOMPLETE" ] && [ "$COMMIT_COUNT" -lt 1 ]; then
  COMMIT_COUNT=1
fi
write_count "$COMMIT_COUNT"

# A branch name may hold backticks; a code span fenced by a backtick run
# longer than any run in the name, padded with spaces, keeps them inside.
longest=0
run=0
for (( i = 0; i < ${#BASE_REF}; i++ )); do
  if [ "${BASE_REF:i:1}" = '`' ]; then
    run=$((run + 1))
    [ "$run" -gt "$longest" ] && longest=$run
  else
    run=0
  fi
done
if [ "$longest" -gt 0 ]; then
  fence=$(printf '%*s' "$((longest + 1))" '' | tr ' ' '`')
  BASE_MD="$fence $BASE_REF $fence"
else
  BASE_MD="\`$BASE_REF\`"
fi

BASE_NOTE=()
if [ "$BASE_COUNT" -gt 0 ] && [ -n "$BASE_TIP" ]; then
  BASE_LOG=$(comm -23 \
    <(git rev-list --no-merges "$PRIOR..$HEAD_NOW" 2>/dev/null | sort) \
    <(git rev-list --no-merges "${RANGE[@]}" 2>/dev/null | sort) \
    | git log --oneline --no-walk=sorted --stdin 2>/dev/null | sed 's/^/    /' || true)
  BASE_NOTE=(
    ''
    "The range also holds $BASE_COUNT commit(s) already on $BASE_MD (the repository's default branch and this PR's base, at \`${BASE_TIP:0:8}\`), which reached this branch only by merging the base. They are not this PR's own commits and are not counted as unreviewed themselves; the merges that brought them in are checked separately, since a merge can still change what the PR does to their files:"
    ''
    "$BASE_LOG"
  )
fi

MERGE_NOTE=()
if [ "${#MERGE_LINES[@]}" -gt 0 ]; then
  MERGE_NOTE=(
    ''
    "Merge commits in the range, each with the files where its result differs from git's own automatic merge of its parents (\`git show --remerge-diff\`): hand-resolved conflicts, a side taken wholesale, or a base change reverted. A merge with any such file is counted as unreviewed. Examine every file listed here:"
    ''
    "${MERGE_LINES[@]}"
  )
fi

INCOMPLETE_NOTE=()
if [ -n "$INCOMPLETE" ]; then
  INCOMPLETE_NOTE=(
    ''
    "**Range incomplete:** the workflow stopped deepening this shallow checkout at its limit with part of ${PRIOR:0:8}..${HEAD_NOW:0:8} still beyond the shallow boundary, so the commits listed here are only the visible part of the range and the count is a lower bound. Review the PR's full diff against its base rather than only the commits listed."
  )
fi

if [ "$COMMIT_COUNT" = "0" ]; then
  printf '%s\n' \
    '## What changed since the last review round (computed)' \
    '' \
    "The prior round reviewed commit \`$PRIOR\`; this checkout's head is \`$HEAD_NOW\`. The workflow computed the range with git itself. It holds no commit of this PR's own, and no merge whose result differs from git's automatic merge: every non-merge commit in ${PRIOR:0:8}..${HEAD_NOW:0:8} is already on the base branch." \
    ${BASE_NOTE[@]+"${BASE_NOTE[@]}"} \
    ${MERGE_NOTE[@]+"${MERGE_NOTE[@]}"} \
    '' \
    "Review the PR's full diff against its base as usual."
  exit 0
fi

LOG=$(git log --oneline --no-merges "${RANGE[@]}" 2>/dev/null | sed 's/^/    /' || true)

if [ -n "$BASE_TIP" ]; then
  # Name the base by its tip SHA: the checkout holds the base only under
  # the private ref, so a branch name here would not resolve.
  LOG_CMD="git log --oneline --no-merges ${PRIOR:0:8}..${HEAD_NOW:0:8} --not ${BASE_TIP:0:8}"
else
  LOG_CMD="git log --oneline --no-merges ${PRIOR:0:8}..${HEAD_NOW:0:8}"
fi

if [ -n "$BASE_TIP" ] && [ "$BASE_COUNT" -gt 0 ]; then
  # A PRIOR..HEAD stat would list the base's files as if the PR changed
  # them; name the files the PR's own commits touch instead (merge commits
  # are listed separately below).
  STAT_CMD="git log --no-merges --name-only --format= ${PRIOR:0:8}..${HEAD_NOW:0:8} --not ${BASE_TIP:0:8} | sort -u"
  STAT=$(git log --no-merges --name-only --format= "${RANGE[@]}" 2>/dev/null | sed '/^$/d' | sort -u | sed 's/^/    /' || true)
else
  STAT_CMD="git diff --stat ${PRIOR:0:8} ${HEAD_NOW:0:8}"
  STAT=$(git diff --stat "$PRIOR" "$HEAD_NOW" 2>/dev/null | sed 's/^/    /' || true)
fi

printf '%s\n' \
  '## What changed since the last review round (computed)' \
  '' \
  "The prior round reviewed commit \`$PRIOR\`; this checkout's head is \`$HEAD_NOW\`. The range below was computed by the workflow with git itself. When you describe what changed since the last round, describe THIS range rather than deriving your own, and examine every commit and file in it:" \
  '' \
  "    \$ $LOG_CMD" \
  "$LOG" \
  '' \
  "    \$ $STAT_CMD" \
  "$STAT" \
  ${MERGE_NOTE[@]+"${MERGE_NOTE[@]}"} \
  ${BASE_NOTE[@]+"${BASE_NOTE[@]}"} \
  ${INCOMPLETE_NOTE[@]+"${INCOMPLETE_NOTE[@]}"} \
  '' \
  "**Mandatory review requirement:** $COMMIT_COUNT unreviewed commit(s) exist in this range (${PRIOR:0:8}..${HEAD_NOW:0:8}). You MUST examine these commits and the diff above. Every commit in this range must be thoroughly reviewed."
