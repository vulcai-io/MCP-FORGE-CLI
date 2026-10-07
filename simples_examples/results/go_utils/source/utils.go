// Small utility module used as a codebase example for mcp-forge.
package utils

// IsPrime returns true if n is a prime number.
func IsPrime(n int) bool {
	if n < 2 {
		return false
	}
	for i := 2; i*i <= n; i++ {
		if n%i == 0 {
			return false
		}
	}
	return true
}

// Factorial returns n! (the factorial of n).
func Factorial(n int) int {
	result := 1
	for i := 2; i <= n; i++ {
		result *= i
	}
	return result
}

// ReverseString returns the reverse of the given string.
func ReverseString(s string) string {
	runes := []rune(s)
	for i, j := 0, len(runes)-1; i < j; i, j = i+1, j-1 {
		runes[i], runes[j] = runes[j], runes[i]
	}
	return string(runes)
}

// SumList returns the sum of a slice of numbers.
func SumList(numbers []float64) float64 {
	total := 0.0
	for _, v := range numbers {
		total += v
	}
	return total
}
