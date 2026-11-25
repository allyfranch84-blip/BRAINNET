import pytest
from workspace_notes import Notes
from workspace_runtime import shape_clarification


def test_notes_survive_reopen_and_backlinks(tmp_path):
    path=tmp_path/'notes.sqlite3'; db=Notes(path)
    a=db.save(None,'Arquitetura','[[Motor]]',0)
    b=db.save(None,'Motor','trajetória',0)
    db=Notes(path)
    assert db.get(a['id'])['links']==[{'title':'Motor','id':b['id']}]
    assert db.get(b['id'])['backlinks']==[{'title':'Arquitetura','id':a['id']}]
    assert db.list('TRAJETÓRIA')[0]['id']==b['id']


def test_conflicting_revision_and_title(tmp_path):
    db=Notes(tmp_path/'notes.sqlite3'); a=db.save(None,'Nota','a',0)
    b=db.save(a['id'],'Nota','b',1)
    assert b['revision']==2
    with pytest.raises(ValueError):db.save(a['id'],'Nota','stale',1)
    with pytest.raises(ValueError):db.save(None,'nota','duplicate',0)
    assert db.get(a['id'])['body']=='b'

@pytest.mark.parametrize('text',['Faça um quadrado com o mouse','mova o mouse em um círculo com diâmetro de 300 pixels','mova o mouse para cima e'])
def test_clarification_no_dispatch(text):
    r=shape_clarification(text);assert r['status']=='CLARIFICATION_REQUIRED' and r['dispatched'] is False

@pytest.mark.parametrize('text',['Abra o Paint','Mova o mouse para cima 300 pixels','Como faço um quadrado com o mouse?','Não faça um quadrado com o mouse'])
def test_other_requests_not_intercepted(text):assert shape_clarification(text) is None


def test_telemetry_is_real_and_reports_missing_gpu():
    from workspace_runtime import on_demand_telemetry
    from types import SimpleNamespace
    data=on_demand_telemetry(SimpleNamespace(is_running=True))
    assert data['available'] and data['kernel']['running']
    assert data['hardware']['ram_total_bytes']>0
    assert 0<=data['hardware']['cpu_total_pct']<=100
    assert 'gpu_pct' not in data['hardware']


def test_audio_missing_device_resets_active(monkeypatch):
    import sys
    from types import SimpleNamespace
    from audio_ear import AudioEar
    def bad_microphone():raise OSError('mock device missing')
    monkeypatch.setitem(sys.modules,'speech_recognition',SimpleNamespace(Recognizer=type('R',(),{}),Microphone=bad_microphone))
    ear=AudioEar()
    assert ear.start_listening()
    ear._thread.join(2)
    assert ear.status()['state']=='ERROR' and not ear.is_listening
    ear.stop_listening()
    assert ear.status()['state']=='STOPPED'


def test_audio_stop_discards_inflight_recognition(monkeypatch):
    import sys,threading
    from types import SimpleNamespace
    from audio_ear import AudioEar
    entered=threading.Event(); release=threading.Event(); received=[]
    class R:
        def listen(self,*a,**kw):return b'mock'
        def recognize_google(self,*a,**kw):entered.set();release.wait(2);return 'mova o mouse'
    class M:
        def __enter__(self):return self
        def __exit__(self,*a):pass
    monkeypatch.setitem(sys.modules,'speech_recognition',SimpleNamespace(Recognizer=R,Microphone=M))
    ear=AudioEar(on_speech_detected=received.append)
    assert ear.start_listening() and entered.wait(1)
    ear.stop_listening();assert ear.status()['state']=='STOPPING' and not ear.is_listening
    release.set();ear._thread.join(2)
    assert ear.status()['state']=='STOPPED' and received==[]
