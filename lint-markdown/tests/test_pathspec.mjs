import assert from 'node:assert';
import { compileIgnores, isIgnored, splitList } from '../_pathspec.mjs';

// 1. splitList
assert.deepStrictEqual(splitList('a, b\nc , d'), ['a', 'b', 'c', 'd']);
assert.deepStrictEqual(splitList(''), []);

// 2. compileIgnores and isIgnored on POSIX paths
const ignores = compileIgnores(['vendor/**', 'docs', '*.tmp', 'src/test_?.md']);
assert.strictEqual(isIgnored('vendor/bundle/a.md', ignores), true);
assert.strictEqual(isIgnored('docs/index.md', ignores), true);
assert.strictEqual(isIgnored('docs/sub/page.md', ignores), true);
assert.strictEqual(isIgnored('foo.tmp', ignores), true);
assert.strictEqual(isIgnored('src/test_1.md', ignores), true);
assert.strictEqual(isIgnored('src/test_12.md', ignores), false);
assert.strictEqual(isIgnored('src/other.md', ignores), false);

// 3. isIgnored with Windows backslash path separators
assert.strictEqual(isIgnored('vendor\\bundle\\a.md', ignores), true);
assert.strictEqual(isIgnored('docs\\index.md', ignores), true);
assert.strictEqual(isIgnored('docs\\sub\\page.md', ignores), true);
assert.strictEqual(isIgnored('src\\test_1.md', ignores), true);
assert.strictEqual(isIgnored('src\\other.md', ignores), false);

console.log('✓ All _pathspec tests passed!');
