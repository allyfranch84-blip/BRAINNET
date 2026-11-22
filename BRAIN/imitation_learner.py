import logging
import sqlite3
from typing import Tuple, Optional
import numpy as np

logger = logging.getLogger("BRAINNET_Imitation")

class ImitationLearner:
    """
    Analisa a telemetria do usuário e cria mapas de probabilidade de clique.
    Usado pelo PPO e pelo Physarum para imitar o comportamento humano.
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path

    def get_click_heatmap(self, process_name: str, screen_width: int = 1920, screen_height: int = 1080, grid_size: int = 10) -> np.ndarray:
        """
        Retorna uma matriz (grid_size x grid_size) com a frequência de cliques
        do usuário para um determinado aplicativo.
        """
        heatmap = np.zeros((grid_size, grid_size), dtype=np.float32)
        
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                # Puxa os cliques do app específico
                rows = conn.execute(
                    "SELECT x, y FROM user_telemetry WHERE process_name LIKE ? AND x IS NOT NULL AND y IS NOT NULL",
                    (f"%{process_name.lower()}%",)
                ).fetchall()
                
            if not rows:
                return heatmap

            for x, y in rows:
                # Mapeia o pixel para a célula do grid (0 a 9)
                gx = min(grid_size - 1, max(0, int((x / screen_width) * grid_size)))
                gy = min(grid_size - 1, max(0, int((y / screen_height) * grid_size)))
                heatmap[gy, gx] += 1.0

            # Normaliza o heatmap para valores entre 0.0 e 1.0
            total = np.sum(heatmap)
            if total > 0:
                heatmap /= total

        except Exception as e:
            logger.error(f"[IMITATION]: Falha ao ler telemetria: {e}")

        return heatmap

    def predict_next_click(self, process_name: str, screen_width: int = 1920, screen_height: int = 1080) -> Optional[Tuple[int, int]]:
        """
        Retorna as coordenadas do centro da célula mais clicada do app.
        """
        heatmap = self.get_click_heatmap(process_name, screen_width, screen_height)
        if np.max(heatmap) == 0:
            return None

        # Encontra o índice da célula com maior valor
        best_y, best_x = np.unravel_index(np.argmax(heatmap), heatmap.shape)
        
        # Converte de volta para coordenadas absolutas (centro da célula)
        cell_w, cell_h = screen_width / 10, screen_height / 10
        target_x = int((best_x * cell_w) + (cell_w / 2))
        target_y = int((best_y * cell_h) + (cell_h / 2))
        
        logger.info(f"[IMITATION]: Imitando usuário em '{process_name}'. Alvo provável: ({target_x}, {target_y}) com {np.max(heatmap)*100:.1f}% de frequência.")
        return target_x, target_y
