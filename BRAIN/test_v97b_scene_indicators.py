from ui_scene_graph import build_scene_graph


def scene(rows):
    return build_scene_graph(app={'hwnd': 1, 'pid': 2}, frame={'coordinate_space': 'screen_physical'}, uia=rows)


def control(name, rect=(10, 10, 50, 50)):
    return {'name': name, 'rect': rect, 'control_type': 'ButtonControl',
            'is_enabled': True, 'is_offscreen': False, 'invoke_supported': True}


def test_missing_and_ambiguous_targets_require_reobservation():
    for graph, reason in [(scene([]), 'target_not_observed'),
                          (scene([control('Pincéis'), control('Pincéis', (60, 10, 90, 50))]), 'target_ambiguous')]:
        result = graph.assess_target('Pincéis')
        assert reason in result['indicators']
        assert result['recommendation'] == 'REOBSERVE_OR_ALTERNATIVE'
        assert result['probability'] is None
        assert result['action_authorized'] is False


def test_native_observation_still_requires_revalidation():
    result = scene([control('Salvar')]).assess_target('Salvar')
    assert result['recommendation'] == 'REVALIDATE_BEFORE_ACTION'
    assert result['action_authorized'] is False
