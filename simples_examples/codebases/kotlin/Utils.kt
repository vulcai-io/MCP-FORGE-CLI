// Small utility module used as a codebase example for mcp-forge.

fun isPrime(n: Int): Boolean {
    if (n < 2) return false
    var i = 2
    while (i * i <= n) {
        if (n % i == 0) return false
        i++
    }
    return true
}

fun factorial(n: Int): Long {
    var result = 1L
    for (i in 2..n) result *= i
    return result
}

fun reverseString(s: String): String {
    return s.reversed()
}

fun sumList(numbers: List<Double>): Double {
    return numbers.sum()
}
