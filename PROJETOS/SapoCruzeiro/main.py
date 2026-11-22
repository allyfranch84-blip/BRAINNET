#!/usr/bin/env python3

import pygame
import modulo

pygame.init()

# Configurações iniciais
largura_tela = 800
altura_tela = 600
janela = pygame.display.set_mode((largura_tela, altura_tela))
título = pygame.display.set_caption('Sapo Cruzeiro')
clock = pygame.time.Clock()

# Carrega imagens
sapo_img = pygame.image.load('sapo.png')

# Posição inicial do sapo
sapo_x = 50
sapo_y = altura_tela - sapo_img.get_height() - 50

# Velocidade do sapo
sapo_velocidade = 5

# Função principal
def main():
    global sapo_x, sapo_y
    rodando = True
    while rodando:
        for evento in pygame.event.get():
            if evento.type == pygame.QUIT:
                rodando = False
            if evento.type == pygame.KEYDOWN:
                if evento.key == pygame.K_LEFT:
                    sapo_x -= sapo_velocidade
                if evento.key == pygame.K_RIGHT:
                    sapo_x += sapo_velocidade

        # Limpa a tela
        janela.fill((255, 255, 255))

        # Desenha o sapo
        janela.blit(sapo_img, (sapo_x, sapo_y))

        # Atualiza a tela
        pygame.display.update()

        # Limita a taxa de quadros
        clock.tick(60)

    pygame.quit()

if __name__ == '__main__':
    main()