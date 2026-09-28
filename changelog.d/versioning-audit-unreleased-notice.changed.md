- **The versioning-docs audit reports a brand-new capability as a notice**
  (#960, #962).
  A capability that exists at no tag yet, and whose stub pins the newest
  existing major tag, is reported as a notice rather than as `ABSENT`, since
  that pin becomes right at the next slide and no other pin could.
  A stub pinning a major tag that has not been cut yet is still `ABSENT`.
  A stub pinning an older major, or a capability missing from the newest tag
  while present at an older one, is still an error.
