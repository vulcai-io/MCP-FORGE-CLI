#!/usr/bin/env bash
# Small utility module used as a codebase example for mcp-forge.

is_prime() {
    local n=$1
    if (( n < 2 )); then echo "false"; return; fi
    local i=2
    while (( i * i <= n )); do
        if (( n % i == 0 )); then echo "false"; return; fi
        ((i++))
    done
    echo "true"
}

factorial() {
    local n=$1
    local result=1
    for ((i = 2; i <= n; i++)); do
        result=$((result * i))
    done
    echo "$result"
}

reverse_string() {
    echo "$1" | rev
}

sum_list() {
    local total=0
    for n in "$@"; do
        total=$((total + n))
    done
    echo "$total"
}
