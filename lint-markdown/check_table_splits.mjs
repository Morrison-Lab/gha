#!/usr/bin/env node
// Flag a blank line that splits a GFM table (#558): a table's rows continue
// after a blank line, but the continuation has no delimiter row of its own,
// so GFM ends the table at the blank line and renders every row below it as
// literal pipe-delimited text.
//
// markdownlint's own table rules operate *within* a table block. A blank line
// ends the block, so the orphaned rows are not a table as far as the linter is
// concerned, and there is nothing left to be inconsistent with -- which is why
// this defect survived in README.md from `cacf1df` until #555 and was visible
// only to a person opening the file on GitHub.
//
// That was measured rather than assumed, because MD058 (`blanks-around-tables`)
// sounds like exactly this check and is not: run against the genuinely broken
// README (`git show cacf1df:README.md`) under markdownlint 0.41.0, the bundled
// config reports 0 errors, and enabling *every* rule reports only MD060
// pipe-spacing nits, none of them at the split. So no markdownlint rule --
// MD055, MD056, MD058, or MD060 -- fires on this.
//
// Detection. A "pipe block" is a maximal run of consecutive lines that begin
// (after at most three spaces) with `|`, outside fenced code. A pipe block is
// a real table when its second line is a GFM delimiter row. A pipe block that
// is NOT a real table, and that is separated from another pipe block by
// nothing but blank lines, is the defect: two pieces of one table with a blank
// line between them.
//
// Requiring that neighbour is what keeps the check quiet. The crude form --
// any blank line between two pipe-prefixed lines -- flags two deliberately
// adjacent tables, which are perfectly valid and common; here the second one
// has its own delimiter row, so it is a real table and neither block is
// reported. Conversely a lone pipe-prefixed line elsewhere in prose has no
// pipe-block neighbour, so it is not reported either.
//
// Scope. Only leading-pipe tables are considered. GFM also accepts a table
// whose rows omit the outer pipes (`A | B` over `--- | ---`), but recognizing
// those means treating any prose line containing a `|` as a candidate row,
// which is ambiguous enough to trade this check's near-zero false-positive
// rate for a much smaller gain.
//
// Unlike the list-item merge splice check, this one scans the whole tree
// rather than diff-scoping. That check diff-scopes because a splice is a style
// judgment a legacy file may reasonably be full of, whereas a split table is a
// rendering defect: the rows below the blank line come out as literal text.
// So a pre-existing hit is worth reporting rather than grandfathering.
//
// That is a claim about how tightly the rule matches, not a claim of
// infallibility, and the cross-vendor review of #576 was right to press on it.
// The merge-and-width test above is what earns it: a finding needs a block
// that is not a table, blank-adjacent to one that becomes a table when the
// blank line goes, with every orphan row at the table's own width. `fail` and
// `paths-ignore` remain the escape hatches if a corpus finds a shape this
// still gets wrong.
//
// Configuration (env vars, set by the composite action):
//   MARKDOWNLINT_GLOBS         Space-separated git pathspecs of tracked files
//                              to check (default "*.md").
//   TABLE_SPLIT_PATHS_IGNORE   Comma/newline-separated glob patterns to skip.
//   TABLE_SPLIT_FAIL           "true" (default) => exit 1 on findings;
//                              "false" => warn only.

import { readFileSync } from 'node:fs';
import { compileIgnores, splitList, trackedFiles } from './_pathspec.mjs';

// CommonMark allows at most three leading spaces before a block-level
// construct; four or more opens an indented code block instead.
const PIPE_ROW = /^ {0,3}\|/;

// A GFM delimiter row: one or more hyphen cells, each optionally anchored with
// a colon on either side. GFM makes the outer pipes optional on ANY row, so a
// delimiter can legitimately be written `--- | ---`; that form is accepted here
// only when it contains a pipe, which keeps a bare `---` reading as the
// thematic break or setext underline it usually is.
const DELIMITER_ROW = /^ {0,3}\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$/;

// A line that can be part of a table: a leading-pipe row, or a pipe-bearing
// delimiter row written without its outer pipes.
function isTableLine(line) {
  return PIPE_ROW.test(line) || (line.includes('|') && DELIMITER_ROW.test(line));
}

// GFM cell count. Cells are separated by unescaped pipes, and the outer pipes
// (when present) produce a leading and trailing empty cell that is not a cell.
function cellCount(line) {
  const text = line.trim();
  const cells = [];
  let current = '';
  for (let i = 0; i < text.length; i++) {
    if (text[i] === '\\' && text[i + 1] === '|') {
      current += '|';
      i++;
    } else if (text[i] === '|') {
      cells.push(current);
      current = '';
    } else {
      current += text[i];
    }
  }
  cells.push(current);
  if (cells.length && cells[0].trim() === '') cells.shift();
  if (cells.length && cells[cells.length - 1].trim() === '') cells.pop();
  return cells.length;
}

// GFM recognizes a table only when a delimiter row follows the header AND the
// two agree on cell count; a mismatch means the whole thing is a paragraph.
// Returns the delimiter's cell count, or 0 when these lines are not a table.
function tableWidth(lines) {
  if (lines.length < 2) return 0;
  if (!DELIMITER_ROW.test(lines[1])) return 0;
  const width = cellCount(lines[1]);
  return width > 0 && cellCount(lines[0]) === width ? width : 0;
}

// Maximal runs of consecutive table lines, skipping fenced code blocks.
// Returns 0-indexed inclusive `{ start, end }` ranges.
function collectPipeBlocks(lines) {
  const blocks = [];
  let fenceChar = null;
  let fenceLen = 0;
  let current = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (fenceChar !== null) {
      // A CLOSING fence may be followed only by whitespace -- an info string is
      // allowed on the opener alone. Matching openers and closers with one
      // pattern let a content line like `~~~ not a closing fence` end the block
      // early, exposing the code inside it to the scan below.
      const closer = line.match(/^ {0,3}(`{3,}|~{3,})[ \t]*$/);
      if (closer && closer[1][0] === fenceChar && closer[1].length >= fenceLen) {
        fenceChar = null;
        fenceLen = 0;
      }
      continue;
    }

    const opener = line.match(/^ {0,3}(`{3,}|~{3,})/);
    if (opener) {
      fenceChar = opener[1][0];
      fenceLen = opener[1].length;
      current = null;
      continue;
    }

    if (isTableLine(line)) {
      if (current === null) {
        current = { start: i, end: i };
        blocks.push(current);
      } else {
        current.end = i;
      }
    } else {
      current = null;
    }
  }
  return blocks;
}

// True when every line strictly between the two indices is blank. Blocks are
// maximal, so there is always at least one line between two of them.
function separatedByBlanksOnly(lines, endOfFirst, startOfSecond) {
  for (let i = endOfFirst + 1; i < startOfSecond; i++) {
    if (lines[i].trim() !== '') return false;
  }
  return true;
}

// A split table is a block that is not a table on its own, sitting blank-line
// adjacent to another block, where deleting the blank lines would produce one
// real table AND every row of the orphan matches that table's width.
//
// Both conditions are load-bearing, and each rules out a false positive the
// other admits. Without the merge test, two unrelated pipe-prefixed paragraphs
// are reported. Without the width test, a real table followed by an unrelated
// pipe-prefixed line is reported, since merging anything onto a real table
// still parses as a table. Requiring the orphan not to be a table already
// exempts two deliberately adjacent tables, which are valid and common.
function findTableSplits(path) {
  const lines = readFileSync(path, 'utf8').split('\n');
  const blocks = collectPipeBlocks(lines);
  const findings = [];

  const linesOf = (block) => lines.slice(block.start, block.end + 1);
  const rowsMatch = (block, width) =>
    linesOf(block).every((line) => cellCount(line) === width);

  for (let b = 0; b < blocks.length; b++) {
    const block = blocks[b];
    if (tableWidth(linesOf(block)) > 0) continue;

    // Both directions are tried, and whichever validates wins. Committing to
    // the `previous` merge whenever one exists loses a real split: an
    // unrelated pipe block sitting above the header half of a split table
    // makes that merge fail, and the header half is then never tested against
    // the delimiter rows below it -- which is the merge that would have
    // validated. Depending on the row widths below, that under-reports the
    // split by one block or misses it entirely.
    const previous = blocks[b - 1];
    const next = blocks[b + 1];
    const candidates = [];

    if (previous && separatedByBlanksOnly(lines, previous.end, block.start)) {
      candidates.push(linesOf(previous).concat(linesOf(block)));
    }
    if (next && separatedByBlanksOnly(lines, block.end, next.start)) {
      candidates.push(linesOf(block).concat(linesOf(next)));
    }

    const width = candidates
      .map((merged) => tableWidth(merged))
      .find((candidate) => candidate > 0 && rowsMatch(block, candidate));
    if (!width) continue;

    findings.push({
      path,
      line: block.start + 1,
      rows: block.end - block.start + 1,
      text: lines[block.start].trim(),
    });
  }
  return findings;
}

function report(findings) {
  console.log(`Found ${findings.length} split GFM table(s):\n`);
  for (const f of findings) {
    console.log(
      `::error file=${f.path},line=${f.line}::A blank line ends the table above, and this block of ${f.rows} row(s) has no delimiter row of its own, so it renders as literal text. Remove the blank line, or give this block its own header and delimiter row: ${f.text}`
    );
  }
}

function main() {
  const pathspecs = (process.env.MARKDOWNLINT_GLOBS || '*.md').split(/\s+/).filter(Boolean);
  const ignores = compileIgnores(splitList(process.env.TABLE_SPLIT_PATHS_IGNORE || ''));
  const fail = (process.env.TABLE_SPLIT_FAIL || 'true').trim().toLowerCase() !== 'false';

  const files = trackedFiles(pathspecs, ignores);
  const findings = files.flatMap((path) => findTableSplits(path));

  if (findings.length === 0) {
    console.log('No split GFM tables found.');
    return;
  }

  report(findings);
  if (fail) process.exitCode = 1;
}

main();
