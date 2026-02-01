n = int(input())

for i in range(n):
    stars = n - i
    spaces = 2 * i
    print('*' * stars + ' ' * spaces + '*' * stars)
