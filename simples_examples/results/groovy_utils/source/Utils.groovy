// Small utility module used as a codebase example for mcp-forge.

boolean isPrime(int n) {
    if (n < 2) return false
    for (int i = 2; i * i <= n; i++) {
        if (n % i == 0) return false
    }
    return true
}

long factorial(int n) {
    long result = 1
    for (int i = 2; i <= n; i++) result *= i
    return result
}

String reverseString(String s) {
    return s.reverse()
}

double sumList(List<Double> numbers) {
    return numbers.sum()
}
