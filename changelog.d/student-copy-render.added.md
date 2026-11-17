- **One composite runs a grading repository's student-copy check on the cluster**
  ([#2064](https://github.com/Morrison-Lab/gha/issues/2064)).
  `.github/actions/student-copy-render` sends the whole check to the WWU CS clusters as one HTCondor job through `condor-batch`:
  both Quarto profiles, each question rendered on its own, then the repository's check command.
  It takes lists of documents and questions, so mcsg (only what a PR changed) and mlg (everything) both use it.
