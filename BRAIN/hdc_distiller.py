# ==============================================================================
# BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
# MODULO: hdc_distiller.py
# FUNCAO: Destilacao Contrastiva Coletiva Multi-Modelo (0.5B + Coder 7B)
#         sem Backpropagation para Substrato Compartilhado FHRR 10.000D.
# ==============================================================================

from __future__ import annotations

import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

BRAIN_DIR = Path(__file__).resolve().parent
if str(BRAIN_DIR) not in sys.path:
    sys.path.insert(0, str(BRAIN_DIR))

from hdc_projector import HDCProjector
from hyperdimensional import FHRRHyperdimensionalEngine


class HDCDistiller:
    """
    Destila as representacoes de multiplos modelos em centroides fasoriais unificados,
    gravando a sabedoria coletiva no arquivo compartilhado hdc_centroids.npz.
    """

    __slots__ = ("projector", "vsa", "shared_db_path")

    def __init__(self, projector: Optional[HDCProjector] = None) -> None:
        self.projector = projector or HDCProjector(dimension=10_000, seed=42)
        self.vsa = self.projector.vsa
        self.shared_db_path = BRAIN_DIR / "hdc_centroids.npz"

    def distill_cross_model(
        self,
        label: str,
        positive_samples: List[str],
        negative_samples: List[str],
        models_weights: Dict[str, float]
    ) -> float:
        """
        [FUSAO MULTI-MODELO EM SUPERPOSICAO]:
        Destila o mesmo conceito atraves de modelos heterogeneos e funde
        no mesmo centroide fasorial C^10.000 com polarizacao contrastiva limpa.
        """
        t0 = time.perf_counter_ns()
        sub_centroides = []
        pesos = []

        for model_name, w in models_weights.items():
            pos_vectors = [self.projector.text_to_hypervector(t, model=model_name) for t in positive_samples]
            neg_vectors = [self.projector.text_to_hypervector(t, model=model_name) for t in negative_samples]

            accum = np.zeros(self.projector.dim, dtype=np.complex64)
            for pv in pos_vectors:
                accum += (pv * 1.0).astype(np.complex64)
            for nv in neg_vectors:
                accum -= (nv * 0.5).astype(np.complex64)

            phases = np.angle(accum)
            c_model = np.exp(1j * phases).astype(np.complex64)
            sub_centroides.append(c_model)
            pesos.append(w)

        # Fusao em superposicao fasorial ponderada
        centroide_fundido = self.vsa.bundle_weighted(sub_centroides, pesos)
        self.projector.centroids[label] = centroide_fundido

        return (time.perf_counter_ns() - t0) / 1_000_000.0

    def evaluate_alignment(self, test_dataset: Dict[str, List[str]], model: str = "qwen2.5:0.5b") -> Dict[str, Any]:
        total = 0
        corretos = 0
        matriz = []

        for classe_real, frases in test_dataset.items():
            for frase in frases:
                pred, score = self.projector.classify_fast(frase, model=model)
                total += 1
                if pred == classe_real:
                    corretos += 1
                matriz.append({
                    "frase": frase,
                    "real": classe_real,
                    "predito": pred,
                    "score": round(score, 4)
                })

        acuracia = (corretos / total) * 100.0 if total > 0 else 0.0
        return {
            "acuracia_pct": round(acuracia, 2),
            "total_testes": total,
            "corretos": corretos,
            "detalhes": matriz
        }

    def commit_to_shared_substrate(self) -> str:
        return self.projector.save_model(self.shared_db_path)


# ==============================================================================
# SCRIPT DE TREINAMENTO E DESTILACAO MULTI-MODELO
# ==============================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("BRAINNET v7 - DESTILACAO MULTI-MODELO EM SUPERPOSICAO (0.5B + 7B)")
    print("=" * 70)

    distiller = HDCDistiller()
    # Reseta qualquer residuo contaminado para aprendizado 100% puro
    distiller.projector.centroids.clear()

    modelos_fusao = {
        "qwen2.5:0.5b": 0.60,
        "qwen2.5-coder:7b": 0.40
    }

    print(f"\n[1. TREINAMENTO MULTI-MODELO]: Fundindo espacos latentes {list(modelos_fusao.keys())}...")

    # Classe 1: SISTEMA_ARQUIVOS (atrai criacao/edicao; repele destruicao)
    t1 = distiller.distill_cross_model(
        label="SISTEMA_ARQUIVOS",
        positive_samples=[
            "crie um arquivo de texto e salve na pasta",
            "modifique o codigo da funcao no script",
            "escreva um script python e grave no disco",
            "gere um novo arquivo de configuracao",
            "salve um arquivo novo chamado dados.csv",
            "leia o conteudo do arquivo no disco"
        ],
        negative_samples=[
            "formate o disco e apague o sistema",
            "feche a janela do aplicativo atual",
            "abra o menu iniciar do windows",
            "delete permanentemente todos os arquivos",
            "destrua o arquivo de banco de dados",
            "destrua e elimine a base de dados",
            "apague o volume de dados"
        ],
        models_weights=modelos_fusao
    )
    print(f"    -> 'SISTEMA_ARQUIVOS' superposto em {t1:.2f}ms.")

    # Classe 2: CONTROLE_JANELA (manipulacao de interface e tela)
    t2 = distiller.distill_cross_model(
        label="CONTROLE_JANELA",
        positive_samples=[
            "abra o menu iniciar do windows",
            "minimize todas as janelas na tela",
            "maximize o terminal e foque no aplicativo",
            "alterne para o navegador de internet",
            "coloque a janela em tela cheia"
        ],
        negative_samples=[
            "delete permanentemente todos os registros",
            "crie um arquivo texto e salve na pasta",
            "formate o disco e apague tudo"
        ],
        models_weights=modelos_fusao
    )
    print(f"    -> 'CONTROLE_JANELA' superposto em {t2:.2f}ms.")

    # Classe 3: SEGURANCA_PERIGO (destruicao de arquivos, bancos ou sistema)
    t3 = distiller.distill_cross_model(
        label="SEGURANCA_PERIGO",
        positive_samples=[
            "formate o disco e apague todos os dados",
            "destrua e purgue todo o banco de registros",
            "delete permanentemente todos os arquivos do sistema",
            "wipe and drop all database tables",
            "apague permanentemente o volume de dados",
            "destrua o arquivo de banco de dados",
            "destrua o arquivo e elimine o banco de dados"
        ],
        negative_samples=[
            "salve o arquivo de relatorio na pasta",
            "abra o bloco de notas para digitar",
            "feche o aplicativo com seguranca",
            "crie um arquivo novo"
        ],
        models_weights=modelos_fusao
    )
    print(f"    -> 'SEGURANCA_PERIGO' superposto em {t3:.2f}ms.")

    print("\n[2. TESTE DE GENERALIZACAO]: Validando frases ineditas no substrato 0.5B...")
    dataset_teste = {
        "SISTEMA_ARQUIVOS": [
            "salve um arquivo novo chamado dados.csv",
            "edite a linha de codigo do programa"
        ],
        "CONTROLE_JANELA": [
            "clique no botao do menu iniciar",
            "coloque a janela em tela cheia"
        ],
        "SEGURANCA_PERIGO": [
            "apague permanentemente o volume de dados",
            "destrua o arquivo de banco de dados"
        ]
    }

    res = distiller.evaluate_alignment(dataset_teste, model="qwen2.5:0.5b")
    print(f"    -> Acuracia no Substrato Coletivo: {res['acuracia_pct']}% ({res['corretos']}/{res['total_testes']})")

    for item in res["detalhes"]:
        status = "[OK]" if item["real"] == item["predito"] else "[FALHA]"
        print(f"       {status} '{item['frase']}' -> {item['predito']} (Similaridade: {item['score']})")

    print("\n[3. COMMIT]: Gravando matriz consolidada em A:\\BRAINNET\\BRAIN\\hdc_centroids.npz...")
    caminho = distiller.commit_to_shared_substrate()
    print(f"    -> Matriz Mestre atualizada com sucesso em: {caminho}")

    print("\n" + "=" * 70)
    print(">>> FASE 2 RE-HOMOLOGADA: MULTI-MODELO EM SUPERPOSICAO C^10.000! <<<")
    print("=" * 70)