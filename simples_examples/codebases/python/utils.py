"""Small utility module used as a codebase example for mcp-forge."""


def is_prime(n: int) -> bool:
    """Return True if n is a prime number."""
    if n < 2:
        return False
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0:
            return False
    return True


def factorial(n: int) -> int:
    """Return n! (the factorial of n)."""
    if n < 0:
        raise ValueError("n must be non-negative")
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result


def reverse_string(s: str) -> str:
    """Return the reverse of the given string."""
    return s[::-1]


def sum_list(numbers: list) -> float:
    """Return the sum of a list of numbers."""
    return sum(numbers)
