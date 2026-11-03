- **`cancel-superseded` no longer warns about a run that already finished**.
  A run that ended between the listing and the cancel call returns HTTP 409,
  which is the outcome the job wants, so it is logged without an annotation
  that would fail a consumer's annotation gate.
  Other failures still warn, now with the API's message.
