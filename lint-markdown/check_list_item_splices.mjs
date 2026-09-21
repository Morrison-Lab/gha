#!/usr/bin/env node
// check-one-function-per-file: allow-multiple
// Flag list-item merge splices: a list item spliced directly onto preceding
// paragraph text without an intervening blank line (#324, #895).
//
// Configuration (env vars, set by the composite action):
//   MARKDOWNLINT_GLOBS             Space-separated git pathspecs of tracked
//                                  files to check (default "*.md").
//   LIST_ITEM_SPLICE_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
//   LIST_ITEM_SPLICE_BASE_REF      Git ref to diff against. If empty, the check
//                                  is skipped (avoiding whole-tree false-positives
//                                  on legacy files). Set to "all" to force a full scan.
//   LIST_ITEM_SPLICE_FAIL          "true" (default) => exit 1 on findings;
//                                  "false" => warn only.

import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { compileIgnores, splitList, trackedFiles } from './_pathspec.mjs';

function getAddedLines(baseRef, pathspecs) {
  try {
    const diff = execFileSync(
      'git',
      ['diff', '--unified=0', '--no-color', `${baseRef}...HEAD`, '--', ...pathspecs],
      { encoding: 'utf8' }
    );
    const added = new Map();
    let currentFile = null;
    let lineNo = 0;

    for (const line of diff.split('\n')) {
      if (line.startsWith('+++ ')) {
        const target = line.slice(4);
        currentFile = target === '/dev/null' ? null : target.replace(/^b\//, '');
        if (currentFile && !added.has(currentFile)) {
          added.set(currentFile, new Set());
        }
        continue;
      }
      if (line.startsWith('@@')) {
        const m = line.match(/^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
        lineNo = m ? parseInt(m[1], 10) : 0;
        continue;
      }
      if (line.startsWith('+') && !line.startsWith('+++')) {

        if (currentFile) {
          added.get(currentFile).add(lineNo);
        }
        lineNo++;
      }
    }
    return added;
  } catch {
    return null;
  }
}

function classifyBoundary(line) {
  if (line === null || line === undefined || line.trim() === '') return 'blank';
  if (/^\s*(`{3,}|~{3,})/.test(line)) return 'fence';
  if (/^\s*#+/.test(line)) return 'heading';
  if (/^\s*([-*_])[ \t]*(?:\1[ \t]*){2,}\s*$/.test(line)) return 'hr';
  if (/^\s*\|/.test(line)) return 'table';
  if (/^\s*>/.test(line)) return 'blockquote';
  if (/^\s*([*+-]|\d+\.)\s+/.test(line)) return 'list-item';
  return 'prose';
}

function findListItemSplices(path, addedLinesSet) {
  const lines = readFileSync(path, 'utf8').split('\n');
  const findings = [];
  let fenceStart = null;
  let fenceChar = null;
  let fenceLen = 0;
  let prevLine = null;
  let prevLineNo = 0;

  for (let i = 0; i < lines.length; i++) {
    const lineNo = i + 1;
    const line = lines[i];
    const fenceMatch = line.match(/^\s*(`{3,}|~{3,})/);

    if (fenceMatch) {
      const fenceStr = fenceMatch[1];
      const fl = fenceStr.length;
      const fc = fenceStr[0];
      if (fenceStart === null) {
        fenceStart = i;
        fenceChar = fc;
        fenceLen = fl;
      } else if (fc === fenceChar && fl >= fenceLen) {
        fenceStart = null;
        fenceChar = null;
        fenceLen = 0;
      }
      prevLine = null;
      prevLineNo = 0;
      continue;
    }
    if (fenceStart !== null) continue;

    const isListItem = /^\s*([*+-]|\d+\.)\s+/.test(line);
    if (isListItem && prevLine !== null) {
      const prevBoundary = classifyBoundary(prevLine);

      if (prevBoundary === 'prose') {
        // Walk back from prevLine to find if it belongs to a preceding list item.
        // A list item continuation can be:
        // 1. An ordinary tight wrapped list item continuation (non-blank block starting with a list marker, #895).
        // 2. An indented paragraph in a loose list item (where blank lines separate indented paragraphs per CommonMark 5.2).
        let isListItemContinuation = false;
        let sawBlank = false;
        let blockStartLine = prevLine;

        const isIndented = (str) => /^(?:\s{2,}|\t)/.test(str);

        for (let j = i - 2; j >= 0; j--) {
          const candidate = lines[j];
          const boundary = classifyBoundary(candidate);

          if (boundary === 'blank') {
            // A blank line can only be crossed if the block below it began with indentation
            // (i.e. an indented block within a loose list item per CommonMark 5.2).
            if (!isIndented(blockStartLine)) break;
            sawBlank = true;
            continue;
          }

          if (boundary === 'fence' || boundary === 'heading' || boundary === 'hr' || boundary === 'table' || boundary === 'blockquote') {
            break;
          }

          if (boundary === 'list-item') {
            isListItemContinuation = true;
            break;
          }

          // If we crossed a blank line, any preceding prose line must also be indented to belong to the list item
          if (sawBlank && !isIndented(candidate)) {
            break;
          }
          blockStartLine = candidate;
        }

        if (!isListItemContinuation) {
          if (!addedLinesSet || addedLinesSet.has(lineNo) || addedLinesSet.has(prevLineNo)) {
            findings.push({
              path,
              line: lineNo,
              prevLineText: prevLine.trim(),
              lineText: line.trim(),
            });
          }
        }
      }
    }
    prevLine = line;
    prevLineNo = lineNo;
  }
  return findings;
}

function report(findings) {
  console.log(`Found ${findings.length} list-item merge splice(s):\n`);
  for (const f of findings) {
    console.log(`::error file=${f.path},line=${f.line}::List-item merged directly onto preceding paragraph text without intervening blank line: ${f.lineText}`);
  }
}

function main() {
  const pathspecs = (process.env.MARKDOWNLINT_GLOBS || '*.md').split(/\s+/).filter(Boolean);
  const ignores = compileIgnores(splitList(process.env.LIST_ITEM_SPLICE_PATHS_IGNORE || ''));
  const baseRef = (process.env.LIST_ITEM_SPLICE_BASE_REF || '').trim();
  const fail = (process.env.LIST_ITEM_SPLICE_FAIL || 'true').trim().toLowerCase() !== 'false';

  if (!baseRef) {
    console.log('::warning::Skipping list-item merge splice check (no base-ref given; not falling back to a whole-tree scan, which would reflag pre-existing list items).');
    return;
  }

  let addedLinesMap = null;
  if (baseRef.toLowerCase() !== 'all') {
    addedLinesMap = getAddedLines(baseRef, pathspecs);
    if (!addedLinesMap) {
      console.log(`::warning::Could not compute diff against base-ref '${baseRef}'; skipping list-item merge splice check.`);
      return;
    }
  }

  const files = trackedFiles(pathspecs, ignores);
  const findings = files.flatMap((path) => {
    const addedSet = addedLinesMap ? (addedLinesMap.get(path) || new Set()) : null;
    return findListItemSplices(path, addedSet);
  });

  if (findings.length === 0) {
    console.log('No list-item merge splices found.');
    return;
  }

  report(findings);
  if (fail) process.exitCode = 1;
}

main();
