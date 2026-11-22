"""Mock-only continuity, visual retries, and monitor geometry."""
import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
import pytest
from BRAINNET import BrainnetBridge
from execution_authority import authorization_scope
from vision_eye import RealVisionEngine
from test_ui_tars_protocol import make_controller

def test_conversation_does_not_replace_failed_task():
    bridge=object.__new__(BrainnetBridge)
    bridge._kernel=SimpleNamespace(esta_dormindo=False,ultimo_toque_ai=0,blackbox=SimpleNamespace(buffer_circular=[]))
    bridge._window=None;bridge._chat_history=[];bridge._last_executed_task=''
    bridge._executar_comando_interno=Mock(return_value={'reply':'falhou','logs':[],
        'visual_result':{'status':'INVALID_PROPOSAL','sucesso_real':False,
                         'failure_reason':'formato inválido','trace':[{'action_type':'invalid_proposal'}]}})
    bridge.send_command('desenhe um triângulo')
    assert bridge._last_executed_task=='desenhe um triângulo'
    result=bridge.send_command('O que deu errado?')
    assert 'formato inválido' in result['reply'] and 'triângulo' in result['reply']
    assert bridge._executar_comando_interno.call_count==1

def test_missing_failure_is_uncertain():
    bridge=object.__new__(BrainnetBridge)
    bridge._kernel=SimpleNamespace(blackbox=SimpleNamespace(buffer_circular=[]))
    result=bridge.send_command('Por que a ação falhou?')
    assert 'Não encontrei evidência' in result['reply'] and 'Faltam' in result['reply']

def test_monitor_rectangles_use_individual_mss_geometry():
    monitors=[{'left':-1920,'top':-900,'width':4480,'height':2340},
              {'left':0,'top':0,'width':2560,'height':1440},
              {'left':-1920,'top':-900,'width':1920,'height':1080}]
    fake=MagicMock();fake.__enter__.return_value.monitors=monitors
    with patch('vision_eye.mss.mss',return_value=fake):
        rects=RealVisionEngine().obter_geometria_monitores()
        assert rects['m1']==(0,0,2560,1440) and rects['m2']==(-1920,-900,0,180)
        assert rects['total']==(-1920,-900,2560,1440)
        with pytest.raises(ValueError):RealVisionEngine().capturar_monitor(3)

def test_two_monitor_descriptions_are_independent_and_numbering_is_uncertain():
    bridge=object.__new__(BrainnetBridge)
    vision=SimpleNamespace(obter_geometria_monitores=Mock(return_value={'m1':(0,0,100,100),'m2':(-100,0,0,100)}),
                           descrever_tela=Mock(side_effect=['primeira imagem','segunda imagem']))
    bridge._kernel=SimpleNamespace(vision=vision)
    result=bridge._executar_comando_interno('Descreva as duas telas','descreva as duas telas','descreva as duas telas')
    assert vision.descrever_tela.call_count==2
    assert 'Índice MSS 1' in result['reply'] and 'Índice MSS 2' in result['reply']
    assert 'não foi confirmada' in result['reply']
    result=bridge._executar_comando_interno('E a tela 2?','e a tela 2?','e a tela 2?')
    assert 'não consigo confirmar' in result['reply'].lower()
    assert vision.descrever_tela.call_count==2

@pytest.mark.parametrize('error,expected_calls',[
    ('JSON visual invalido: syntax',2),
    ('Somente chamada de funcao simples e permitida',1),
    ('Coordenadas devem conter apenas numeros literais',1),
])
def test_visual_retry_only_for_format_errors(error,expected_calls):
    controller,trajectory=make_controller([ValueError(error)]*3)
    with authorization_scope(threading.Event()):
        result=asyncio.run(controller.run_task('pinte um triangulo'))
    assert result['status']=='INVALID_PROPOSAL'
    assert controller.vision.describe_ui_with_protocol.call_count==expected_calls
    trajectory.bridge.dispatch.assert_not_awaited()
