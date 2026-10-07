// Small utility module used as a codebase example for mcp-forge.

export function isPrime(n: number): boolean {
  if (n < 2) return false;
  for (let i = 2; i <= Math.sqrt(n); i++) {
    if (n % i === 0) return false;
  }
  return true;
}

export function factorial(n: number): number {
  let result = 1;
  for (let i = 2; i <= n; i++) result *= i;
  return result;
}

export function reverseString(s: string): string {
  return s.split("").reverse().join("");
}

export function sumList(numbers: number[]): number {
  return numbers.reduce((a, b) => a + b, 0);
}
