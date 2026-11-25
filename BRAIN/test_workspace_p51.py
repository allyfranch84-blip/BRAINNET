
import pytest
import workspace_chat_archive as archive

@pytest.fixture(autouse=True)
def isolated_db(monkeypatch,tmp_path):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path))

def test_roundtrip_and_isolation():
    a=[{"id":"a","role":"user","text":"Olá","timestamp":1},{"id":"b","role":"ai","text":"Olá 1","durationMs":123}]
    assert archive.save("chat_a",a)["ok"]
    assert archive.save("chat_b",[{"role":"user","text":"Outro"}])["ok"]
    assert archive.load("chat_a")==a
    assert archive.load("chat_b")[0]["text"]=="Outro"
    assert len(archive.listing())==2
    assert archive.load("new_chat")==[]

def test_update_without_duplicate_chat():
    archive.save("chat",[{"role":"user","text":"primeiro"}])
    archive.save("chat",[{"role":"user","text":"primeiro"},{"role":"ai","text":"segundo"}])
    assert len(archive.listing())==1
    assert len(archive.load("chat"))==2

def test_validation_preserves_saved_chat():
    archive.save("valid",[{"role":"user","text":"original"}])
    with pytest.raises(ValueError):
        archive.save("valid",[{"role":"system","text":"invalid"}])
    assert archive.load("valid")[0]["text"]=="original"
    with pytest.raises(ValueError):
        archive.load("../invalid")

def test_recall_from_distinct_conversations():
    archive.save("a",[{"role":"user","text":"memória episódica"}])
    archive.save("b",[{"role":"ai","text":"memória semântica"}])
    hits=archive.recall("MEMÓRIA")
    assert {x["id"] for x in hits}=={"a","b"}

def test_context_is_bounded():
    rows=[{"role":"user","text":"x"*4000} for _ in range(130)]
    assert len(archive.history(rows))==120
    assert len(archive.history(rows)[0]["text"])==3000
