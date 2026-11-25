# =============================================================================
# run_p52_slice.py — Teste E2E (Fase P52 + Validação)
# =============================================================================

import asyncio
import logging

# Importações do Council
from council.mission_contract import Mission, Scope, ActionKind, Contract
from council.mission_state import MissionState
from council.mission_context import MissionContext
from council.reasoning_engine import ReasoningEngine
from council.mission_planner import MissionPlanner
from council.prompt_builder import PromptBuilder
from council.execution_kernel import ExecutionKernel
from council.self_reflection import BrainSelfReflection
from council.knowledge_indexer import KnowledgeIndexer
from council.mission_executor import MissionExecutor

# NOVAS IMPORTAÇÕES DA CAMADA DE ABSTRAÇÃO
from council.provider_registry import ProviderRegistry
from council.provider_selector import ProviderSelector
from council.plan_validator import PlanValidator

# Importações das Fakes
from council.fake_ports import FakeBrowserAdapter, FakeConversationProvider

logging.basicConfig(level=logging.INFO, format="%(message)s")

class MockReasoner:
    def where_to_change(self, objective: str, limit: int = 5) -> list:
        class DummyCandidate:
            file = "motor_intent.py"
        return [DummyCandidate()]

    def get_dependencies(self, module: str) -> list:
        return []

    def which_tests(self, file: str) -> list:
        return []

async def main():
    print("\n" + "="*60)
    print("🚀 INICIANDO TESTE E2E (FASE P52) - PROVIDER REGISTRY")
    print("="*60 + "\n")

    # 1. Configurando o Workspace e o Contrato
    print("1️⃣ Configurando Missão e Contrato...")
    scope = Scope(
        allowed_files=["motor_intent.py"],
        allowed_actions={ActionKind.SEND_PROMPT, ActionKind.RUN_TEST},
        max_model_calls=3
    )
    mission = Mission(
        objective="Pergunte ao ChatGPT: Qual é a capital do Brasil?",
        scope=scope
    )
    active_contract = Contract(mission=mission)
    active_contract.activate()

    # 2. Inicializando a Infraestrutura (Registry)
    print("2️⃣ Inicializando ProviderRegistry...")
    registry = ProviderRegistry()
    
    # Registrando os Fakes no Registry
    registry.register("chatgpt", FakeConversationProvider("ChatGPT"))
    registry.register("deepseek", FakeConversationProvider("DeepSeek"))
    registry.register("browser", FakeBrowserAdapter())
    
    # Seletor de Modelos (Caso o Planner queira usar)
    selector = ProviderSelector()

    # 3. Inicializando os Componentes Cognitivos
    print("3️⃣ Inicializando Componentes do Council...")
    mock_reasoner = MockReasoner()
    reasoning_engine = ReasoningEngine(architecture_reasoner=mock_reasoner) # type: ignore
    planner = MissionPlanner(reasoner=mock_reasoner) # type: ignore
    
    # Agora o Kernel recebe o Registry
    kernel = ExecutionKernel(registry=registry)
    
    # Memória, Reflexão e Validação
    knowledge = KnowledgeIndexer(root=".")
    reflect = BrainSelfReflection(knowledge_indexer=knowledge, reports_dir="./mission_reports")
    prompt_builder = PromptBuilder()
    validator = PlanValidator(registry=registry) # <-- O Validador!
    
    # O Executor recebe o Validador
    executor = MissionExecutor(
        kernel=kernel, 
        prompt_builder=prompt_builder, 
        self_reflection=reflect,
        validator=validator
    )

    # 4. Montando o MissionContext
    print("4️⃣ Montando o MissionContext...")
    state = MissionState(mission_id=mission.mission_id, contract=active_contract)
    context = MissionContext(
        mission=mission,
        contract=active_contract,
        state=state
    )

    # 5. Executando a Inteligência (Reasoning -> Planning)
    print("5️⃣ ReasoningEngine decidindo estratégia...")
    _ = reasoning_engine.plan_mission(mission, state)
    
    print("6️⃣ MissionPlanner gerando plano detalhado...")
    # Usamos "direct_impl" para esta missão simples
    plan = planner.plan(mission, state, strategy="direct_impl")
    context.plan = plan
    
    print(f"\n--- PLANO GERADO ---")
    print(f"Estratégia: {plan.strategy}")
    # O Planner vai usar o deepseek como implementador
    print(f"Modelos: {plan.architect_model or 'Nenhum'} -> {plan.implementer_model}")
    print(f"Arquivos: {plan.ordered_files}")
    print("--------------------\n")

    # 6. Executando a Missão (O Validador entra em ação aqui dentro)
    print("7️⃣ MissionExecutor entrando em ação...")
    result_status = await executor.execute(context)
    
    print("\n" + "="*60)
    print(f"🏁 MISSÃO FINALIZADA COM STATUS: {result_status.upper()}")
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(main())