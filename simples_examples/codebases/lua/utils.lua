-- Small utility module used as a codebase example for mcp-forge.

local M = {}

function M.is_prime(n)
    if n < 2 then return false end
    for i = 2, math.floor(math.sqrt(n)) do
        if n % i == 0 then return false end
    end
    return true
end

function M.factorial(n)
    local result = 1
    for i = 2, n do
        result = result * i
    end
    return result
end

function M.reverse_string(s)
    return s:reverse()
end

function M.sum_list(numbers)
    local total = 0
    for _, v in ipairs(numbers) do
        total = total + v
    end
    return total
end

return M
