# Small utility module used as a codebase example for mcp-forge.

is_prime <- function(n) {
  if (n < 2) return(FALSE)
  for (i in 2:floor(sqrt(n))) {
    if (n %% i == 0) return(FALSE)
  }
  return(TRUE)
}

factorial_fn <- function(n) {
  if (n <= 1) return(1)
  return(prod(2:n))
}

reverse_string <- function(s) {
  paste(rev(strsplit(s, "")[[1]]), collapse = "")
}

sum_list <- function(numbers) {
  sum(numbers)
}
