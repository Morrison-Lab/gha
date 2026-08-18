test_that("bump_dev_version_string increments dev and initializes release", {
  expect_equal(bump_dev_version_string("0.1.0"), "0.1.0.9000")
  expect_equal(bump_dev_version_string("0.1.0.9000"), "0.1.0.9001")
  expect_equal(bump_dev_version_string("1.2.3.9050"), "1.2.3.9051")
  expect_error(bump_dev_version_string("1.2"))
  expect_error(bump_dev_version_string("1.2.3.4.5"))
})

test_that("versions_equal checks semantic version equality", {
  expect_true(versions_equal("0.1.0", "0.1.0.0"))
  expect_true(versions_equal("1.0.0", "1.0"))
  expect_false(versions_equal("0.1.0", "0.1.1"))
})

test_that("read_version and bump_dev_version manipulate files correctly", {
  tmp <- tempfile(fileext = ".txt")
  writeLines(c("Package: testpkg", "Version: 0.1.0", "Title: Test"), tmp)
  
  expect_equal(read_version(tmp), "0.1.0")
  res <- bump_dev_version(tmp)
  expect_equal(res$old, "0.1.0")
  expect_equal(res$new, "0.1.0.9000")
  expect_equal(read_version(tmp), "0.1.0.9000")
  
  unlink(tmp)
})
