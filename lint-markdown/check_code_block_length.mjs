#!/usr/bin/env node
// Flag fenced code blocks in Markdown that are long enough to warrant
// decomposing into subfunctions/subscripts, per the lab manual's
// function-length heuristic (coding-practices/function-length-limits.qmd).
//
// Configuration (env vars, set by the composite action):
//   MARKDOWNLINT_GLOBS             Space-separated git pathspecs of tracked
//                                  files to check (default "*.md"), matching
//                                  run_markdownlint.mjs's scope so both
//                                  checks see the same file set.
//   CODEBLOCK_LENGTH_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
//   CODEBLOCK_LENGTH_MAX_LINES     Line-count threshold per fenced code block
//                                  (default 150).
//   CODEBLOCK_LENGTH_FAIL          "true" => exit 1 on findings; "false"
//                                  (default) => warn only, since the lab
//                                  manual documents its threshold as "a
//                                  provisional heuristic trigger ... not a
//                                  hard constraint".

import { readFileSync } from 'node:fs';
import { compileIgnores, splitList, trackedFiles } from './_pathspec.mjs';

// A heuristic tripwire, not a full CommonMark parser: a fence is any line
// starting with 3+ backticks or tildes; a matching close uses the same
// character. Nested fences of the *other* character (rare) are not handled.
function findLongCodeBlocks(path, maxLines) {
  const lines = readFileSync(path, 'utf8').split('\n');
  const findings = [];
  let fenceStart = null;
  let fenceChar = null;

  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(/^(`{3,}|~{3,})/);
    if (!m) continue;
    if (fenceStart === null) {
      fenceStart = i;
      fenceChar = m[1][0];
    } else if (m[1][0] === fenceChar) {
      const nLines = i - fenceStart - 1;
      if (nLines > maxLines) {
        findings.push({ path, line: fenceStart + 1, nLines });
      }
      fenceStart = null;
      fenceChar = null;
    }
  }
  return findings;
}

function report(findings, maxLines) {
  console.log(
    `Found ${findings.length} fenced code block(s) longer than ${maxLines} lines -- ` +
      'consider decomposing into subfunctions or moving the example to a linked file:\n'
  );
  for (const f of findings) {
    console.log(`  ${f.path}:${f.line}: code block is ${f.nLines} lines`);
  }
}

function main() {
  const pathspecs = (process.env.MARKDOWNLINT_GLOBS || '*.md').split(/\s+/).filter(Boolean);
  const ignores = compileIgnores(splitList(process.env.CODEBLOCK_LENGTH_PATHS_IGNORE || ''));
  const maxLines = parseInt(process.env.CODEBLOCK_LENGTH_MAX_LINES || '150', 10);
  const fail = (process.env.CODEBLOCK_LENGTH_FAIL || 'false').trim().toLowerCase() === 'true';

  const findings = trackedFiles(pathspecs, ignores).flatMap((path) => findLongCodeBlocks(path, maxLines));

  if (findings.length === 0) {
    console.log(`No fenced code blocks longer than ${maxLines} lines.`);
    return;
  }

  report(findings, maxLines);
  if (fail) process.exitCode = 1;
}

main();
