"""Unit tests for the check-phi heuristic detectors.

The detectors are high-precision tripwires that gate PRs for protected health
information, so they're exactly the kind of regex/heuristic code that silently
regresses on refactor. These tests pin each detector's positive and negative
behavior, including the `csv_phi_header` line-1 / suffix edge cases.

check-phi.py isn't an importable module name (the hyphen), so load it by path.
"""

import importlib.util
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent.parent / "check-phi.py"
_spec = importlib.util.spec_from_file_location("check_phi", _MOD_PATH)
assert _spec is not None and _spec.loader is not None, f"Could not load {_MOD_PATH}"
check_phi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_phi)


# ── SSN ──────────────────────────────────────────────────────────────────────

def test_ssn_matches_a_valid_number():
    hits = check_phi._detect_ssn("f.txt", 1, "patient ssn 123-45-6789 on file")
    assert len(hits) == 1
    assert "Social Security" in hits[0][1]


def test_ssn_never_echoes_the_value():
    # Findings must report only the detector message, never the matched digits.
    hits = check_phi._detect_ssn("f.txt", 1, "123-45-6789")
    assert hits  # must fire so the no-echo check below is non-vacuous
    assert all("123-45-6789" not in message for _, message in hits)


def test_ssn_reports_a_one_based_column():
    # col is the 1-based character offset of the match (m.start() + 1).
    hits = check_phi._detect_ssn("f.txt", 1, "ssn 123-45-6789")
    assert len(hits) == 1
    assert hits[0][0] == 5  # "123" begins at index 4


def test_ssn_rejects_areas_the_ssa_never_issues():
    for bad in ("000-12-3456", "666-12-3456", "900-12-3456"):
        assert check_phi._detect_ssn("f.txt", 1, bad) == []


def test_ssn_rejects_zero_group_or_serial():
    assert check_phi._detect_ssn("f.txt", 1, "123-00-4567") == []
    assert check_phi._detect_ssn("f.txt", 1, "123-45-0000") == []


def test_ssn_ignores_longer_digit_runs():
    # The (?<!\d) lookbehind and (?!\d) lookahead guards keep it off zip+4 and
    # longer ID fragments.
    assert check_phi._detect_ssn("f.txt", 1, "00123-45-67890") == []


def test_valid_ssn_helper():
    assert check_phi._valid_ssn("123", "45", "6789") is True
    assert check_phi._valid_ssn("000", "45", "6789") is False
    assert check_phi._valid_ssn("900", "45", "6789") is False
    assert check_phi._valid_ssn("123", "00", "6789") is False
    assert check_phi._valid_ssn("123", "45", "0000") is False


# ── MRN ──────────────────────────────────────────────────────────────────────

def test_mrn_matches_labeled_numbers():
    for line in ("MRN: 123456", "medical record number 1234567", "mrn=987654321"):
        assert len(check_phi._detect_mrn("f.txt", 1, line)) == 1


def test_mrn_requires_enough_digits():
    # 5–12 digits required, so a 4-digit value doesn't trip it.
    assert check_phi._detect_mrn("f.txt", 1, "mrn: 1234") == []


def test_mrn_accepts_the_twelve_digit_upper_bound():
    # The \d{5,12} bound should still fire at exactly 12 digits.
    assert len(check_phi._detect_mrn("f.txt", 1, "mrn 123456789012")) == 1


def test_mrn_needs_the_label():
    assert check_phi._detect_mrn("f.txt", 1, "record 123456 archived") == []


# ── DOB ──────────────────────────────────────────────────────────────────────

def test_dob_matches_labeled_dates():
    for line in ("DOB: 01/02/1990", "date of birth 1990-01-02", "birth_date 1/2/90"):
        assert len(check_phi._detect_dob("f.txt", 1, line)) == 1


def test_dob_needs_a_date_after_the_label():
    assert check_phi._detect_dob("f.txt", 1, "date of birthday party next week") == []


# ── CSV header detector (incl. the diff-scope edge case) ─────────────────────

def test_csv_header_flags_phi_column_on_line_one():
    hits = check_phi._detect_csv_phi_header("data.csv", 1, "ssn,name\n")
    assert len(hits) == 1
    assert hits[0][0] == 1  # first column


def test_csv_header_reports_later_column_offset():
    # col is the 1-based character offset of the offending cell, not its index.
    hits = check_phi._detect_csv_phi_header("data.csv", 1, "id,ssn\n")
    assert len(hits) == 1
    assert hits[0][0] == 4  # after "id," → 1 + len("id") + 1


def test_csv_header_only_fires_on_line_one():
    # The reviewer-flagged edge case: in a diff, the header detector keys off the
    # NEW-file line number, so it must fire only when that number is 1.
    assert check_phi._detect_csv_phi_header("data.csv", 2, "ssn,name") == []


def test_csv_header_only_fires_on_delimited_suffixes():
    assert check_phi._detect_csv_phi_header("notes.txt", 1, "ssn,name") == []


def test_csv_header_uses_the_right_delimiter_per_suffix():
    # .tsv splits on tab; the normalized token drops spaces/underscores.
    assert len(check_phi._detect_csv_phi_header("d.tsv", 1, "patient id\tvalue")) == 1
    assert len(check_phi._detect_csv_phi_header("d.psv", 1, "value|date_of_birth")) == 1


def test_csv_header_ignores_non_phi_columns():
    assert check_phi._detect_csv_phi_header("data.csv", 1, "id,value,count") == []


# ── Study/participant identifier literals ─────────────────────────
# Every value below is synthetic. The exposure this detector was built from is
# reproduced by *shape* only: ten alphanumerics, digit-leading, quoted, in a
# one-off `if <var>="...";` debugging spot-check.

def test_study_id_matches_the_incident_shape():
    # The literal form that motivated the detector, with a synthetic value.
    hits = check_phi._detect_study_id("p.sas", 1, 'if StudyID_c="1ABCDEFGHI";')
    assert len(hits) == 1
    assert "identifier" in hits[0][1]


def test_study_id_matches_regardless_of_the_value_alphabet():
    # The point of keying on the variable name: an all-digit id and a mixed
    # alphanumeric one are both caught, so the rule does not silently cover
    # only the subset that looks numeric.
    for value in ("1234567890", "1ABCDEFGHI", "AB12345678", "a1b2c3d4e5"):
        assert check_phi._detect_study_id("p.sas", 1, f'if StudyID_c="{value}";')


def test_study_id_matches_other_id_variable_names_and_operators():
    for line in (
        'patient_id = "AB12345678"',
        'subject_id: "X9Y8Z7W6V5"',
        "if studyid_c=='1ABCDEFGHI'",
        'participant_ids = "1ABCDEFGHI"',
        'member_identifier = "AB12345678"',
        'if StudyID_c != "1ABCDEFGHI"',
    ):
        assert check_phi._detect_study_id("f.txt", 1, line), line


def test_study_id_matches_r_assignment_arrows():
    # R and Quarto are the target ecosystem, where `<-` is the dominant
    # assignment form; a rule that only saw `=` would miss most of it.
    for line in ('study_id <- "1ABCDEFGHI"', 'study_id <<- "1ABCDEFGHI"'):
        assert check_phi._detect_study_id("a.R", 1, line), line


def test_study_id_matches_an_underscore_prefixed_name():
    # A `\b` finds no boundary before an underscore, so these were skipped
    # until the lookbehind replaced it.
    for line in ('base_patient_id = "1ABCDEFGHI"', '_study_id = "1ABCDEFGHI"'):
        assert check_phi._detect_study_id("a.py", 1, line), line


def test_study_id_matches_subscripted_column_access():
    for line in ('df["patient_id"] = "1ABCDEFGHI"',
                 'df[["patient_id"]] <- "1ABCDEFGHI"'):
        assert check_phi._detect_study_id("a.R", 1, line), line


def test_study_id_still_requires_a_whole_name_not_a_suffix():
    # The lookbehind must not turn into "match anywhere": a name whose id-word
    # is embedded in a longer alphanumeric token is not an id variable.
    assert check_phi._detect_study_id("a.R", 1, 'mystudy_id = "1ABCDEFGHI"') == []


def test_study_id_matches_sas_word_operators():
    # SAS writes comparisons as words. `if StudyID_c ne "..." then delete;` is
    # how one real site escaped every `=`-keyed search during the exposure
    # this detector was built from.
    for line in ('if StudyID_c ne "1ABCDEFGHI" then delete;',
                 'if StudyID_c eq "1ABCDEFGHI";'):
        assert check_phi._detect_study_id("p.sas", 1, line), line


def test_study_id_word_operators_require_surrounding_space():
    # Without the space requirement, `ne`/`eq` would match inside a longer
    # variable name and turn the operator alternation into a wildcard.
    assert check_phi._detect_study_id("p.sas", 1, 'study_idne = "1ABCDEFGHI"') == []


def test_study_id_matches_sas_membership_operator():
    # SAS's `in (...)` is the third comparison shape, alongside `=` and the
    # word operators. `where StudyID_c in ("...");` is how a real identifier
    # escaped this detector while every name-keyed check reported clean.
    # `in (` and `in(` are both valid SAS, and SAS is usually written upper
    # case, which the pattern's leading `(?i)` already covers.
    for line in ('\twhere StudyID_c in ("1ABCDEFGHI");',
                 'where StudyID_c IN ("1ABCDEFGHI");',
                 'where StudyID_c in("1ABCDEFGHI");',
                 'where StudyID_c in ( "1ABCDEFGHI" );',
                 "where patient_id in ('AB12345678');"):
        assert check_phi._detect_study_id("p.sas", 1, line), line


def test_study_id_matches_negated_sas_membership_operator():
    # The other operator families each carry both polarities (`==`/`!=`,
    # `eq`/`ne`), so membership must not reach only the affirmative. Excluding a
    # named participant is as ordinary a place for a hard-coded id as selecting
    # one, and the leading `(?i)` covers the upper-case form SAS usually writes.
    for line in ('where StudyID_c not in ("1ABCDEFGHI");',
                 'where StudyID_c NOT IN ("1ABCDEFGHI");',
                 'if StudyID_c not in ("1ABCDEFGHI") then delete;',
                 'where StudyID_c  not   in  ("1ABCDEFGHI");'):
        assert check_phi._detect_study_id("p.sas", 1, line), line


def test_study_id_negated_membership_keeps_the_token_boundary():
    # The negated form must not relax the guard the affirmative one carries:
    # `not` needs whitespace on both sides, or a longer variable name and a
    # one-word `notin` would each read as a membership test.
    for line in ('study_idnot in ("1ABCDEFGHI")',
                 'where study_id notin ("1ABCDEFGHI");',
                 'patient_id not_in ("1ABCDEFGHI")'):
        assert check_phi._detect_study_id("p.sas", 1, line) == [], line


def test_study_id_membership_list_needs_only_one_hit():
    # A multi-value list flags the line on its first element; the detector
    # reports the line, not an inventory of the values on it.
    hits = check_phi._detect_study_id(
        "p.sas", 1, 'where StudyID_c in ("1ABCDEFGHI","AB12345678");')
    assert len(hits) == 1


def test_study_id_membership_cannot_span_lines():
    # The scan is line-based, so a wrapped list is missed in full rather than
    # past its first element: the opening line carries the name and operator
    # with no literal, and the literal lines carry no name.
    for line in ("where StudyID_c in (",
                 '    "1ABCDEFGHI",',
                 '    "AB12345678"',
                 ");"):
        assert check_phi._detect_study_id("p.sas", 1, line) == [], line


def test_study_id_membership_operator_requires_a_preceding_space():
    # The negative control for the `in` branch, and the reason it carries the
    # same `\s+` as `eq`/`ne`: without it, an ordinary function call whose name
    # merely ends in `id` would read as a membership test on an id variable.
    for line in ('study_idin ("1ABCDEFGHI")', 'patient_idin("1ABCDEFGHI")'):
        assert check_phi._detect_study_id("p.sas", 1, line) == [], line


def test_study_id_membership_still_requires_a_quoted_literal():
    # The `in` branch must not relax the right-hand side: a subquery or a bare
    # column list inside the parens is not an identifier literal.
    for line in ("where study_id in (subject_id);",
                 "where study_id in (select id from cohort);",
                 'where patient_id in ("2026-01-01");'):
        assert check_phi._detect_study_id("p.sas", 1, line) == [], line


def test_study_id_never_echoes_the_value():
    hits = check_phi._detect_study_id("p.sas", 1, 'if StudyID_c="1ABCDEFGHI";')
    assert hits  # must fire so the no-echo check below is non-vacuous
    assert all("1ABCDEFGHI" not in message for _, message in hits)


def test_study_id_reports_a_one_based_column():
    hits = check_phi._detect_study_id("p.sas", 1, 'if StudyID_c="1ABCDEFGHI";')
    assert len(hits) == 1
    assert hits[0][0] == 4  # "StudyID_c" begins at index 3


def test_study_id_rejects_an_unquoted_right_hand_side():
    # Almost always another variable rather than a literal.
    for line in ("study_id = another_var;", "studyid_c = subject_id;",
                 "study_id = 1ABCDEFGHI;"):
        assert check_phi._detect_study_id("f.txt", 1, line) == [], line


def test_study_id_rejects_short_or_all_alphabetic_literals():
    for line in ('patient_id = "1234"',        # too short
                 'study_id = "ABCDEFGH"',      # no digit: a category label
                 'subject_id = "config1"'):    # under the eight-char floor
        assert check_phi._detect_study_id("f.txt", 1, line) == [], line


def test_study_id_rejects_prose_with_no_assignment():
    assert check_phi._detect_study_id("d.md", 1, "study id 1234567890 was dropped") == []


def test_study_id_fires_on_a_placeholder_so_pseudonyms_need_an_allowlist():
    # Documented limit rather than an oversight: a repository that redacts in
    # place to STUDYIDnn must allowlist that shape, or its own redacted files
    # re-trip the check.
    assert check_phi._detect_study_id("p.sas", 1, 'if StudyID_c="STUDYID20";')


def test_study_id_is_registered_and_on_by_default():
    assert "study_id" in check_phi.DETECTORS
    assert "study_id" in check_phi.DEFAULT_DETECTORS


# ── Off-by-default line detectors ────────────────────────────────────────────

def test_phone_needs_separators():
    assert len(check_phi._detect_phone("f.txt", 1, "call 555-123-4567")) == 1
    assert len(check_phi._detect_phone("f.txt", 1, "(555) 123-4567")) == 1
    # A bare 10-digit run is treated as an arbitrary ID, not a phone number.
    assert check_phi._detect_phone("f.txt", 1, "id 5551234567 here") == []


def test_email_detector():
    assert len(check_phi._detect_email("f.txt", 1, "contact a.b+c@example.com")) == 1
    assert check_phi._detect_email("f.txt", 1, "no address here") == []


# ── Path-ignore glob translation ─────────────────────────────────────────────

def test_bare_dir_ignore_is_recursive():
    ignores = check_phi._compile_ignores(["docs"])
    assert check_phi._ignored("docs/sub/data.csv", ignores) is True
    assert check_phi._ignored("docs", ignores) is True


def test_wildcard_ignore_stays_single_segment():
    ignores = check_phi._compile_ignores(["tests/*"])
    assert check_phi._ignored("tests/a.csv", ignores) is True
    assert check_phi._ignored("tests/sub/a.csv", ignores) is False


def test_double_star_ignore_is_recursive():
    ignores = check_phi._compile_ignores(["**/*.csv"])
    assert check_phi._ignored("any/depth/data.csv", ignores) is True
    assert check_phi._ignored("data.csv", ignores) is True


# ── Misc helpers ─────────────────────────────────────────────────────────────

def test_split_list_handles_commas_and_newlines():
    assert check_phi._split_list("ssn, mrn\n dob ") == ["ssn", "mrn", "dob"]
    assert check_phi._split_list("") == []


def test_inline_pragma_matches_phi_allow_but_not_allowlist():
    # A `phi-allow` token on a line suppresses it; the word boundary keeps the
    # pragma from also firing on "phi-allowlist" (e.g. a path mention).
    assert check_phi.INLINE_PRAGMA_RE.search("ssn 123-45-6789  # phi-allow")
    assert not check_phi.INLINE_PRAGMA_RE.search("see .github/phi-allowlist.txt")
