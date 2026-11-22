from hyperdimensional import FHRRHyperdimensionalEngine
from natural_comprehension import CONCEPT_SEEDS, retrieve_concept_candidates
from parser_contract import analyze_literal_intent, parse_supervised_mouse_move


def test_curated_concepts_have_stable_ids_and_never_authorize():
    engine=FHRRHyperdimensionalEngine(dimension=1000,seed=42)
    results=retrieve_concept_candidates(engine,'cursor ponteiro movimento',limit=5)
    assert len(CONCEPT_SEEDS)==11 and len(results)==5
    assert all(item['concept_id'].startswith('brainnet:concept:v1:') for item in results)
    assert all(not item['verified'] and not item['execution_authorized'] for item in results)
    assert [x['similarity'] for x in results]==sorted([x['similarity'] for x in results],reverse=True)


def test_literal_negation_and_question_never_authorize():
    for text in ('não abra o paint','o Paint abriu?'):
        assert analyze_literal_intent(text)['execution_authorized'] is False
    assert parse_supervised_mouse_move('não mova o mouse lentamente 30 pixels para a direita, sem clicar') is None
