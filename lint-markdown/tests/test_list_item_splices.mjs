import { execFileSync } from 'node:child_process';
import { writeFileSync, unlinkSync, mkdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import assert from 'node:assert';

const testDir = join(process.cwd(), 'lint-markdown', 'tests', 'temp_fixture');

try {
  mkdirSync(testDir, { recursive: true });

  // 1. Positive control: splice fixture (list item spliced onto paragraph continuation line)
  const spliceFile = join(testDir, 'splice.md');
  const spliceContent = `# Fixture

## Bug fixes

An entry whose text wraps onto a continuation line, ending with a
reference to \`data-raw/precompute-true-effects-chunk.R\` (#429).
* The \`docs\` workflow's "Build site" step no longer times out intermittently.

* A normally separated item, for contrast.
`;
  writeFileSync(spliceFile, spliceContent);

  // Run check_list_item_splices.mjs with base-ref='all'
  const scriptPath = join(process.cwd(), 'lint-markdown', 'check_list_item_splices.mjs');

  let failed = false;
  let stdout = '';
  try {
    stdout = execFileSync('node', [scriptPath], {
      env: { ...process.env, MARKDOWNLINT_GLOBS: spliceFile, LIST_ITEM_SPLICE_BASE_REF: 'all' },
      encoding: 'utf8',
    });
  } catch (err) {
    failed = true;
    stdout = err.stdout || '';
  }

  assert.strictEqual(failed, true, 'Expected check_list_item_splices.mjs to fail on splice.md');
  assert.match(stdout, /Found 1 list-item merge splice/);
  assert.match(stdout, /splice\.md,line=7/);

  // Positive control 2: single-line paragraph splice
  const singleLineSpliceFile = join(testDir, 'single_line_splice.md');
  const singleLineSpliceContent = `# Single Line Splice

Introductory paragraph line directly preceding a list item.
* Spliced bullet item.
`;
  writeFileSync(singleLineSpliceFile, singleLineSpliceContent);

  failed = false;
  try {
    stdout = execFileSync('node', [scriptPath], {
      env: { ...process.env, MARKDOWNLINT_GLOBS: singleLineSpliceFile, LIST_ITEM_SPLICE_BASE_REF: 'all' },
      encoding: 'utf8',
    });
  } catch (err) {
    failed = true;
    stdout = err.stdout || '';
  }
  assert.strictEqual(failed, true, 'Expected check_list_item_splices.mjs to fail on single_line_splice.md');
  assert.match(stdout, /Found 1 list-item merge splice/);
  assert.match(stdout, /single_line_splice\.md,line=4/);

  // Positive control 3: paragraph following spaced thematic break spliced onto list item
  const spacedHrSpliceFile = join(testDir, 'spaced_hr_splice.md');
  const spacedHrSpliceContent = `# Spaced HR Splice

* * *
Paragraph following spaced thematic break.
* Spliced bullet item.
`;
  writeFileSync(spacedHrSpliceFile, spacedHrSpliceContent);

  failed = false;
  try {
    stdout = execFileSync('node', [scriptPath], {
      env: { ...process.env, MARKDOWNLINT_GLOBS: spacedHrSpliceFile, LIST_ITEM_SPLICE_BASE_REF: 'all' },
      encoding: 'utf8',
    });
  } catch (err) {
    failed = true;
    stdout = err.stdout || '';
  }
  assert.strictEqual(failed, true, 'Expected check_list_item_splices.mjs to fail on spaced_hr_splice.md');
  assert.match(stdout, /Found 1 list-item merge splice/);
  assert.match(stdout, /spaced_hr_splice\.md,line=5/);

  // Test empty base-ref skip
  stdout = execFileSync('node', [scriptPath], {
    env: { ...process.env, MARKDOWNLINT_GLOBS: spliceFile, LIST_ITEM_SPLICE_BASE_REF: '' },
    encoding: 'utf8',
  });
  assert.match(stdout, /Skipping list-item merge splice check/);

  // 2. Negative control: clean fixture (including ordinary wrapped lists per #895)
  const cleanFile = join(testDir, 'clean.md');
  const cleanContent = `# Clean Fixture

## Features
* Item directly after heading
* Tight item 1
* Tight item 2
* Tight item 3

* Item with continuation
  line wrapped cleanly

* Separated item

- **A** -- first item with a
  wrapped continuation line.
- **B** -- second item directly after that continuation.
- **C** -- third.

* An entry whose text wraps onto a continuation line, ending with a
  reference to \`data-raw/precompute-true-effects-chunk.R\` (#429).
* The \`docs\` workflow's "Build site" step no longer times out intermittently.

1. First numbered item with a
   wrapped continuation line.
2. Second numbered item directly after that continuation.

\`\`\`bash
# Code block
* Fake item in code block
\`\`\`

~~~bash
# Tilde code block
* Fake item in tilde code block
~~~

> Blockquote
* Item directly after blockquote

| Table |
| --- |
* Item after table

---
* Item after HR

* * *
* Item after spaced HR

* Item A
  continuation line one

  continuation line two, still part of A per indentation
* Item B
`;
  writeFileSync(cleanFile, cleanContent);

  failed = false;
  try {
    stdout = execFileSync('node', [scriptPath], {
      env: { ...process.env, MARKDOWNLINT_GLOBS: cleanFile, LIST_ITEM_SPLICE_BASE_REF: 'all' },
      encoding: 'utf8',
    });
  } catch (err) {
    failed = true;
    stdout = err.stdout || '';
  }

  assert.strictEqual(failed, false, 'Expected check_list_item_splices.mjs to pass on clean.md');
  assert.match(stdout, /No list-item merge splices found/);

  console.log('✓ All list-item merge splice tests passed!');

} finally {
  rmSync(testDir, { recursive: true, force: true });
}
