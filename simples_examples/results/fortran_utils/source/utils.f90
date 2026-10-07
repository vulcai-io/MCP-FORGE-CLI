! Small utility module used as a codebase example for mcp-forge.
module utils
    implicit none
contains

    logical function is_prime(n)
        integer, intent(in) :: n
        integer :: i
        is_prime = .true.
        if (n < 2) then
            is_prime = .false.
            return
        end if
        do i = 2, int(sqrt(real(n)))
            if (mod(n, i) == 0) then
                is_prime = .false.
                return
            end if
        end do
    end function is_prime

    integer function factorial(n)
        integer, intent(in) :: n
        integer :: i
        factorial = 1
        do i = 2, n
            factorial = factorial * i
        end do
    end function factorial

    function reverse_string(s) result(r)
        character(len=*), intent(in) :: s
        character(len=len(s)) :: r
        integer :: i, n
        n = len(s)
        do i = 1, n
            r(i:i) = s(n - i + 1:n - i + 1)
        end do
    end function reverse_string

    real function sum_list(numbers, count)
        real, intent(in) :: numbers(:)
        integer, intent(in) :: count
        sum_list = sum(numbers(1:count))
    end function sum_list

end module utils
