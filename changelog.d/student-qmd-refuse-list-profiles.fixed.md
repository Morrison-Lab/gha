- **Refuse list-valued `when-profile` and `unless-profile` attributes in `student-qmd`**,
  which Quarto matches as a single profile name rather than splitting on commas or whitespace ([gha#924](https://github.com/Morrison-Lab/gha/issues/924)).
  Fails fast in both the generator and checker when an attribute contains commas or whitespace.
