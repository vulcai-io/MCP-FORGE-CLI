# Small utility module used as a codebase example for mcp-forge.

def is_prime(n)
  return false if n < 2
  (2..Math.sqrt(n)).each do |i|
    return false if n % i == 0
  end
  true
end

def factorial(n)
  (2..n).reduce(1, :*)
end

def reverse_string(s)
  s.reverse
end

def sum_list(numbers)
  numbers.sum
end
