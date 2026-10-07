// Small utility module used as a codebase example for mcp-forge.

function isPrime(n) {
  if (n < 2) return false;
  for (let i = 2; i <= Math.sqrt(n); i++) {
    if (n % i === 0) return false;
  }
  return true;
}

function factorial(n) {
  let result = 1;
  for (let i = 2; i <= n; i++) result *= i;
  return result;
}

function reverseString(s) {
  return s.split("").reverse().join("");
}

function sumList(numbers) {
  return numbers.reduce((a, b) => a + b, 0);
}

module.exports = { isPrime, factorial, reverseString, sumList };
