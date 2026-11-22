# Este arquivo pode ser usado para modularizar funções ou classes adicionais
# Por exemplo, funções de movimento, colisões, etc.

# Exemplo de função para mover o sapo

def mover_sapo(sapo_x, sapo_y, velocidade):
    sapo_x += velocidade
    return sapo_x, sapo_y

# Exemplo de função para verificar colisões

def verificar_colisão(sapo_x, sapo_y, obstáculo_x, obstáculo_y):
    if sapo_x < obstáculo_x + obstáculo_img.get_width() and sapo_x + sapo_img.get_width() > obstáculo_x:
        if sapo_y < obstáculo_y + obstáculo_img.get_height() and sapo_y + sapo_img.get_height() > obstáculo_y:
            return True
    return False