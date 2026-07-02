// Shared glob-based path-ignore matching for lint-markdown's checks. Kept
// local to this composite (not imported across composite directories) so
// each capability in this repo stays independently taggable and
// self-contained; mirrors lint-yaml/_pathspec.py's matching rules for
// consistency across both linters.

export function splitList(raw) {
  return raw
    .split(/[,\n]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

// Supports `**` (any number of path segments), `*` (within one segment), and
// `?`. A bare directory name (no wildcards) also matches everything beneath
// it, mirroring GitHub's native paths-ignore semantics.
function globToRegExp(pattern) {
  let out = '';
  for (let i = 0; i < pattern.length; ) {
    const c = pattern[i];
    if (c === '*') {
      if (pattern.slice(i, i + 2) === '**') {
        i += 2;
        if (pattern[i] === '/') {
          out += '(?:.*/)?';
          i += 1;
        } else {
          out += '.*';
        }
      } else {
        out += '[^/]*';
        i += 1;
      }
    } else if (c === '?') {
      out += '[^/]';
      i += 1;
    } else {
      out += c.replace(/[.+^${}()|[\]\\]/g, '\\$&');
      i += 1;
    }
  }
  return new RegExp(`^${out}$`);
}

export function compileIgnores(patterns) {
  const compiled = [];
  for (const pat of patterns) {
    compiled.push(globToRegExp(pat));
    if (!pat.includes('*') && !pat.includes('?')) {
      compiled.push(globToRegExp(`${pat.replace(/\/$/, '')}/**`));
    }
  }
  return compiled;
}

export function isIgnored(path, ignores) {
  return ignores.some((re) => re.test(path));
}
