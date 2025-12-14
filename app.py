import pygame
import sys

# pygame ishga tushirish
pygame.init()

# Oyna sozlamalari
WIDTH, HEIGHT = 500, 500
CELL_SIZE = 50
ROWS = COLS = 10

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Hello my game")

clock = pygame.time.Clock()

# Ranglar
WHITE = (255, 255, 255)
GRAY = (200, 200, 200)
BLUE = (0, 100, 255)

# O‘yinchi boshlang‘ich joyi (katak bo‘yicha)
player_x = 0
player_y = 0

def draw_grid():
    for x in range(0, WIDTH, CELL_SIZE):
        pygame.draw.line(screen, GRAY, (x, 0), (x, HEIGHT))
    for y in range(0, HEIGHT, CELL_SIZE):
        pygame.draw.line(screen, GRAY, (0, y), (WIDTH, y))

# Asosiy o‘yin sikli
while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_LEFT and player_x > 0:
                player_x -= 1
            if event.key == pygame.K_RIGHT and player_x < COLS - 1:
                player_x += 1
            if event.key == pygame.K_UP and player_y > 0:
                player_y -= 1
            if event.key == pygame.K_DOWN and player_y < ROWS - 1:
                player_y += 1

    # Chizish
    screen.fill(WHITE)
    draw_grid()

    # O‘yinchi (kvadrat)
    pygame.draw.rect(
        screen,
        BLUE,
        (player_x * CELL_SIZE, player_y * CELL_SIZE, CELL_SIZE, CELL_SIZE)
    )

    pygame.display.update()
    clock.tick(60)