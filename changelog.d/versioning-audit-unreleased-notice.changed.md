- **The versioning-docs audit reports a brand-new capability as a notice**
  (#960).
  A capability that exists at no tag yet, and whose stub pins the newest major
  tag, is reported as `UNRELEASED` rather than `ABSENT`, since that pin becomes
  right at the next slide and no other pin could.
  A stub pinning an older major, or a capability missing from the newest tag
  while present at an older one, is still an error.
