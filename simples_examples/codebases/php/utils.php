<?php
// Small utility module used as a codebase example for mcp-forge.

function is_prime(int $n): bool {
    if ($n < 2) return false;
    for ($i = 2; $i * $i <= $n; $i++) {
        if ($n % $i === 0) return false;
    }
    return true;
}

function factorial(int $n): int {
    $result = 1;
    for ($i = 2; $i <= $n; $i++) $result *= $i;
    return $result;
}

function reverse_string(string $s): string {
    return strrev($s);
}

function sum_list(array $numbers): float {
    return array_sum($numbers);
}
