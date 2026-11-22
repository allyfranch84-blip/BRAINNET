"""Verificacao conservadora de circulo vermelho em canvas explicitamente identificado."""
from __future__ import annotations

from collections import deque
import numpy as np


def verify_new_red_circle(before, after, canvas_rect):
    """Compara imagens PIL alinhadas; canvas_rect usa coordenadas locais da imagem.

    Retorna False quando a regiao nao e comprovada ou a geometria e ambigua.
    Nao identifica o canvas por heuristica nem usa resultado produzido pelo VLM.
    """
    if canvas_rect is None or before is None or after is None or before.size != after.size:
        return False
    if not isinstance(canvas_rect, (tuple, list)) or len(canvas_rect) != 4:
        return False
    if any(type(v) is not int for v in canvas_rect):
        return False
    left, top, right, bottom = canvas_rect
    width, height = before.size
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        return False
    if (right-left) * (bottom-top) > 4_000_000:
        return False
    previous = np.asarray(before.crop(canvas_rect).convert("RGB"), dtype=np.int16)
    current = np.asarray(after.crop(canvas_rect).convert("RGB"), dtype=np.int16)

    def red(rgb):
        return (rgb[:, :, 0] >= 150) & (rgb[:, :, 0] >= rgb[:, :, 1] + 55) & (rgb[:, :, 0] >= rgb[:, :, 2] + 55)

    mask = red(current) & ~red(previous)
    visited = np.zeros(mask.shape, dtype=bool)
    ys, xs = np.nonzero(mask)
    for sy, sx in zip(ys, xs):
        if visited[sy, sx]:
            continue
        visited[sy, sx] = True
        queue = deque([(int(sy), int(sx))])
        points = []
        while queue:
            y, x = queue.popleft()
            points.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if (dy or dx) and 0 <= ny < mask.shape[0] and 0 <= nx < mask.shape[1] and mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        queue.append((ny, nx))
        if len(points) < 32:
            continue
        pts = np.asarray(points, dtype=float)
        min_y, min_x = pts.min(axis=0)
        max_y, max_x = pts.max(axis=0)
        h, w = max_y-min_y+1, max_x-min_x+1
        if min(h, w) < 12 or not 0.8 <= w / h <= 1.25:
            continue
        xnorm = (pts[:, 1] - (min_x+max_x)/2) / (w/2)
        ynorm = (pts[:, 0] - (min_y+max_y)/2) / (h/2)
        radius = np.hypot(xnorm, ynorm)
        if np.mean(radius > 1.08) > 0.04:
            continue
        rim = radius >= 0.72
        if not rim.any():
            continue
        angles = np.arctan2(ynorm[rim], xnorm[rim])
        sectors = np.unique(((angles + np.pi) * (24 / (2*np.pi))).astype(int) % 24)
        if len(sectors) >= 20:
            return True
    return False
