import { execFileSync } from 'node:child_process';
import { writeFileSync, unlinkSync, mkdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import assert from 'node:assert';

const testDir = join(process.cwd(), 'lint-markdown', 'tests', 'temp_fixture');

try {
  mkdirSync(testDir, { recursive: true });

  // 1. Positive control: splice fixture
  const spliceFile = join(testDir, 'splice.md');
  const spliceContent = `# Fixture

## Bug fixes

* An entry whose text wraps onto a continuation line, ending with a
  reference to \`data-raw/precompute-true-effects-chunk.R\` (#429).
* The \`docs\` workflow's "Build site" step no longer times out intermittently.

* A normally separated item, for contrast.
`;
  writeFileSync(spliceFile, spliceContent);

  // Run check_list_item_splices.mjs
  const scriptPath = join(process.cwd(), 'lint-markdown', 'check_list_item_splices.mjs');

  let failed = false;
  let stdout = '';
  try {
    stdout = execFileSync('node', [scriptPath], {
      env: { ...process.env, MARKDOWNLINT_GLOBS: spliceFile },
      encoding: 'utf8',
    });
  } catch (err) {
    failed = true;
    stdout = err.stdout || '';
  }

  assert.strictEqual(failed, true, 'Expected check_list_item_splices.mjs to fail on splice.md');
  assert.match(stdout, /Found 1 list-item merge splice/);
  assert.match(stdout, /splice\.md,line=7/);

  // 2. Negative control: clean fixture
  const cleanFile = join(testDir, 'clean.md');
  const cleanContent = `# Clean Fixture

## Features

* Tight item 1
* Tight item 2
* Tight item 3

* Item with continuation
  line wrapped cleanly

* Separated item

\`\`\`bash
# Code block
* Fake item in code block
\`\`\`

| Table |
| --- |
* Item after table

---
* Item after HR
`;
  writeFileSync(cleanFile, cleanContent);

  failed = false;
  try {
    stdout = execFileSync('node', [scriptPath], {
      env: { ...process.env, MARKDOWNLINT_GLOBS: cleanFile },
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
