- `check-merge-drops` no longer reports the lines one parent added to a file that the other parent deleted, when the merge keeps the deletion (a modify/delete conflict resolved as delete).
  A file the merge alone deletes, or a new file it drops, is still reported (gha#2089).
