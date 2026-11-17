- `condor-batch` asks every head, before it submits, how many jobs sit idle in its queue
  and how many copies of the job fit in its unclaimed slots,
  and sends the job to the head with the most room to spare, keeping the spread order otherwise (gha#2093).
  Each head's numbers and the choice are logged.
  `CONDOR_PROBE_SECONDS` (default 60) bounds the queries.
