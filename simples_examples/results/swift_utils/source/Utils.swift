// Small utility module used as a codebase example for mcp-forge.

func isPrime(_ n: Int) -> Bool {
    if n < 2 { return false }
    var i = 2
    while i * i <= n {
        if n % i == 0 { return false }
        i += 1
    }
    return true
}

func factorial(_ n: Int) -> Int {
    var result = 1
    for i in 2...max(n, 1) where i <= n { result *= i }
    return result
}

func reverseString(_ s: String) -> String {
    return String(s.reversed())
}

func sumList(_ numbers: [Double]) -> Double {
    return numbers.reduce(0, +)
}
