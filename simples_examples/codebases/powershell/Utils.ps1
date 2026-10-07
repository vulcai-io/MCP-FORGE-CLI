# Small utility module used as a codebase example for mcp-forge.

function Test-IsPrime {
    param([int]$N)
    if ($N -lt 2) { return $false }
    for ($i = 2; $i * $i -le $N; $i++) {
        if ($N % $i -eq 0) { return $false }
    }
    return $true
}

function Get-Factorial {
    param([int]$N)
    $result = 1
    for ($i = 2; $i -le $N; $i++) { $result *= $i }
    return $result
}

function Get-ReverseString {
    param([string]$S)
    $chars = $S.ToCharArray()
    [Array]::Reverse($chars)
    return -join $chars
}

function Get-SumList {
    param([double[]]$Numbers)
    return ($Numbers | Measure-Object -Sum).Sum
}
