# Small utility module used as a codebase example for mcp-forge.
defmodule Utils do
  def is_prime(n) when n < 2, do: false

  def is_prime(n) do
    2..trunc(:math.sqrt(n))
    |> Enum.all?(fn i -> rem(n, i) != 0 end)
  end

  def factorial(n) do
    Enum.reduce(2..n, 1, fn i, acc -> acc * i end)
  end

  def reverse_string(s) do
    String.reverse(s)
  end

  def sum_list(numbers) do
    Enum.sum(numbers)
  end
end
