`slide-major-tag.yml` now refuses to move the tag unless every check run on the commit is green or skipped.
Dependabot updater runs and the slide job itself are exempt, since they are not tests of the commit.
The `force` input and `ALLOW_BREAKING_SLIDE` bypass it, as they bypass the permissions audit.
