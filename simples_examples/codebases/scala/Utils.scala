// Small utility module used as a codebase example for mcp-forge.

object Utils {

  def isPrime(n: Int): Boolean = {
    if (n < 2) false
    else !(2 to math.sqrt(n).toInt).exists(i => n % i == 0)
  }

  def factorial(n: Int): Long = {
    (2 to n).foldLeft(1L)(_ * _)
  }

  def reverseString(s: String): String = s.reverse

  def sumList(numbers: List[Double]): Double = numbers.sum
}
