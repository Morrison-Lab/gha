- **`condor-batch` can submit to the csci-lab desktop pool**
  ([#1518](https://github.com/Morrison-Lab/gha/issues/1518)).
  A `head` entry may carry a port, as in `csci-lab-head.cs.wwu.edu:922`.
  A head in the desktop pool keeps its run directory under the login home, asks for `+CSCI_GrpDesktop`, and receives the Apptainer image from the new `image-file` input with each job through HTCondor file transfer, so nothing is read from its home.
  Heads outside the pool behave as before.
