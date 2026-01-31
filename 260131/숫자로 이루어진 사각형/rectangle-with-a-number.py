n = int(input())

# Please write your code here.
def print_square(n):
    num = 1
    for _ in range(n):
        for _ in range(n):
            print((num - 1) % 9 + 1,end =' ')
            num += 1
        print()
print_square(n)