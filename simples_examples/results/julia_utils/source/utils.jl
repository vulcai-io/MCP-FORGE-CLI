# Small utility module used as a codebase example for mcp-forge.

function is_prime(n::Int)::Bool
    if n < 2
        return false
    end
    for i in 2:floor(Int, sqrt(n))
        if n % i == 0
            return false
        end
    end
    return true
end

function factorial_fn(n::Int)::Int
    result = 1
    for i in 2:n
        result *= i
    end
    return result
end

function reverse_string(s::String)::String
    return reverse(s)
end

function sum_list(numbers::Vector{Float64})::Float64
    return sum(numbers)
end
