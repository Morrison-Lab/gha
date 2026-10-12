- **A confirming Claude review links the prior verdict's real comment URL**
  (Morrison-Lab/bcs#1122).
  The prompt asks a confirming review to link the prior round's verdict
  comment, but the prior-review context it was handed carried only each
  comment's date, so the reviewer wrote a made-up
  `#issuecomment-placeholder` link.
  Each summary header in that context now carries the comment's `html_url`,
  and the prompt says to take the link from there and never write a
  placeholder.
  Both prior-review reads also paginate now: without it the API returned
  the first 30 comments, so on a busy PR the "last three" summaries came
  from the oldest page.
