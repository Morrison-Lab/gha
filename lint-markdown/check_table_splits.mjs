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
// rather than diff-scoping. That check diff-scopes because a splice is a
// style judgment a legacy file may reasonably be full of; a split table is an
// unambiguous rendering defect with no legitimate form, so a pre-existing hit
// is a bug to fix rather than a false positive to suppress.
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
// a colon on either side. Only ever tested against a line already known to be
// a pipe row, so it cannot be confused with a `---` thematic break.
const DELIMITER_ROW = /^ {0,3}\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$/;

// Maximal runs of consecutive pipe rows, skipping fenced code blocks.
// Returns 0-indexed inclusive `{ start, end }` ranges.
function collectPipeBlocks(lines) {
  const blocks = [];
  let fenceChar = null;
  let fenceLen = 0;
  let current = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const fenceMatch = line.match(/^ {0,3}(`{3,}|~{3,})/);

    if (fenceMatch) {
      const fenceStr = fenceMatch[1];
      if (fenceChar === null) {
        fenceChar = fenceStr[0];
        fenceLen = fenceStr.length;
      } else if (fenceStr[0] === fenceChar && fenceStr.length >= fenceLen) {
        fenceChar = null;
        fenceLen = 0;
      }
      current = null;
      continue;
    }
    if (fenceChar !== null) continue;

    if (PIPE_ROW.test(line)) {
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

function isRealTable(lines, block) {
  return block.end > block.start && DELIMITER_ROW.test(lines[block.start + 1]);
}

// True when every line strictly between the two indices is blank. Pipe blocks
// are maximal, so there is always at least one line between two of them.
function separatedByBlanksOnly(lines, endOfFirst, startOfSecond) {
  for (let i = endOfFirst + 1; i < startOfSecond; i++) {
    if (lines[i].trim() !== '') return false;
  }
  return true;
}

function findTableSplits(path) {
  const lines = readFileSync(path, 'utf8').split('\n');
  const blocks = collectPipeBlocks(lines);
  const findings = [];

  for (let b = 0; b < blocks.length; b++) {
    const block = blocks[b];
    if (isRealTable(lines, block)) continue;

    const previous = blocks[b - 1];
    const next = blocks[b + 1];
    const adjacentAbove = previous && separatedByBlanksOnly(lines, previous.end, block.start);
    const adjacentBelow = next && separatedByBlanksOnly(lines, block.end, next.start);
    if (!adjacentAbove && !adjacentBelow) continue;

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
