- **`cursor-code-review.yml` queues a Cursor Bugbot review** (#510).
  Wraps `POST https://api.cursor.com/bugbot/review` (Enterprise, `admin:*`
  key). Success means the review was queued; Bugbot posts comments itself.
  `ai-code-review.yml` can pick `cursor` when `CURSOR_API_KEY` is set.
