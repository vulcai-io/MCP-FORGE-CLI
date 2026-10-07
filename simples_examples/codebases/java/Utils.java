// Small utility module used as a codebase example for mcp-forge.

public class Utils {

    public static boolean isPrime(int n) {
        if (n < 2) return false;
        for (int i = 2; i * i <= n; i++) {
            if (n % i == 0) return false;
        }
        return true;
    }

    public static long factorial(int n) {
        long result = 1;
        for (int i = 2; i <= n; i++) result *= i;
        return result;
    }

    public static String reverseString(String s) {
        return new StringBuilder(s).reverse().toString();
    }

    public static double sumList(double[] numbers) {
        double total = 0;
        for (double v : numbers) total += v;
        return total;
    }
}
