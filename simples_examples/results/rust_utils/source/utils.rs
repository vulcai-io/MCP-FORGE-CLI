// Small utility module used as a codebase example for mcp-forge.

pub fn is_prime(n: u64) -> bool {
    if n < 2 {
        return false;
    }
    let mut i = 2;
    while i * i <= n {
        if n % i == 0 {
            return false;
        }
        i += 1;
    }
    true
}

pub fn factorial(n: u64) -> u64 {
    (2..=n).product::<u64>().max(1)
}

pub fn reverse_string(s: &str) -> String {
    s.chars().rev().collect()
}

pub fn sum_list(numbers: &[f64]) -> f64 {
    numbers.iter().sum()
}
