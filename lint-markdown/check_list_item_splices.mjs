#!/usr/bin/env node
// Flag list-item merge splices: a list item spliced directly onto a previous
// item's continuation line with no intervening blank line (#324).
//
// Configuration (env vars, set by the composite action):
//   MARKDOWNLINT_GLOBS             Space-separated git pathspecs of tracked
//                                  files to check (default "*.md").
//   LIST_ITEM_SPLICE_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
//   LIST_ITEM_SPLICE_BASE_REF      Git ref to diff against. If set, only added
//                                  lines in the diff are checked.
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

function findListItemSplices(path, addedLinesSet) {
  const lines = readFileSync(path, 'utf8').split('\n');
  const findings = [];
  let inCodeBlock = false;
  let prevLine = null;
  let prevLineNo = 0;

  for (let i = 0; i < lines.length; i++) {
    const lineNo = i + 1;
    const line = lines[i];
    const fenceMatch = line.match(/^(`{3,}|~{3,})/);
    if (fenceMatch) {
      inCodeBlock = !inCodeBlock;
      prevLine = null;
      prevLineNo = 0;
      continue;
    }
    if (inCodeBlock) continue;

    const isListItem = /^\s*([*+-]|\d+\.)\s+/.test(line);
    if (isListItem && prevLine !== null) {
      const isPrevBlank = prevLine.trim() === '';
      const isPrevListItem = /^\s*([*+-]|\d+\.)\s+/.test(prevLine);
      const isPrevHeading = /^\s*#+/.test(prevLine);
      const isPrevBlockquote = /^\s*>/.test(prevLine);
      const isPrevTable = /^\s*\|/.test(prevLine);
      const isPrevHR = /^\s*[-*_]{3,}\s*$/.test(prevLine);

      if (!isPrevBlank && !isPrevListItem && !isPrevHeading && !isPrevBlockquote && !isPrevTable && !isPrevHR) {
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
    prevLine = line;
    prevLineNo = lineNo;
  }
  return findings;
}

function report(findings) {
  console.log(`Found ${findings.length} list-item merge splice(s):\n`);
  for (const f of findings) {
    console.log(`::error file=${f.path},line=${f.line}::List-item merged directly onto continuation line without intervening blank line: ${f.lineText}`);
  }
}

function main() {
  const pathspecs = (process.env.MARKDOWNLINT_GLOBS || '*.md').split(/\s+/).filter(Boolean);
  const ignores = compileIgnores(splitList(process.env.LIST_ITEM_SPLICE_PATHS_IGNORE || ''));
  const baseRef = (process.env.LIST_ITEM_SPLICE_BASE_REF || '').trim();
  const fail = (process.env.LIST_ITEM_SPLICE_FAIL || 'true').trim().toLowerCase() !== 'false';

  let addedLinesMap = null;
  if (baseRef) {
    addedLinesMap = getAddedLines(baseRef, pathspecs);
    if (!addedLinesMap) {
      console.log(`::warning::Could not compute diff against base-ref '${baseRef}'; scanning all lines in tracked files.`);
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
