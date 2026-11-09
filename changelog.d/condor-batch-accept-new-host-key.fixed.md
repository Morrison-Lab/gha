- `condor-batch` passes `-o StrictHostKeyChecking=accept-new` to ssh,
  so a head missing from the runner's `known_hosts`, such as `csci-lab-head:922`, is usable instead of failing with `Host key verification failed` (gha#1634).
  A head whose recorded key changed is still refused.
