import os
import tempfile
from ghrr_core import GHRRHyperdimensionalEngine
from pdag_ghrr_extension import SyntacticPDAG

def test_syntactic_pdag():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    try:
        engine = GHRRHyperdimensionalEngine(dim=10_000, matrix_size=2)
        pdag = SyntacticPDAG(db_path, engine)
        
        steps = [
            {"acao": "OPEN_APP", "app": "brave"},
            {"acao": "HOTKEY", "keys": ["ctrl", "l"]},
            {"acao": "TYPE", "text": "python"},
            {"acao": "HOTKEY", "keys": ["enter"]}
        ]
        
        # Armazena
        pdag.store_route("test_route_1", "pesquisar python", steps)
        
        # Recupera
        route = pdag.retrieve_route("test_route_1")
        assert route is not None
        assert len(route["steps"]) == 4
        assert route["steps"][0]["acao"] == "OPEN_APP"
        
        # Verifica integridade da sequência
        sim = pdag.verify_sequence("test_route_1", steps)
        assert sim > 0.99, f"Similaridade muito baixa: {sim}"
        
        print(f"✅ Syntactic P-DAG funcionou. Similaridade: {sim:.4f}")
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

if __name__ == "__main__":
    test_syntactic_pdag()