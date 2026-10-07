// Small utility module used as a codebase example for mcp-forge.

bool isPrime(int n) {
  if (n < 2) return false;
  for (int i = 2; i * i <= n; i++) {
    if (n % i == 0) return false;
  }
  return true;
}

int factorial(int n) {
  int result = 1;
  for (int i = 2; i <= n; i++) result *= i;
  return result;
}

String reverseString(String s) {
  return s.split('').reversed.join('');
}

double sumList(List<double> numbers) {
  return numbers.fold(0, (a, b) => a + b);
}
