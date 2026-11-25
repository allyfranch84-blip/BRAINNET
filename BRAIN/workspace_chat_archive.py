
"""Conversation archive, separate from motor authorization and user notes."""
import sqlite3
import json
import os
import re
from pathlib import Path
from time import time

def _db():
    root = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "BRAINNET"
    root.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(root / "workspace_chats.sqlite3", timeout=5)
    con.execute("CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, title TEXT NOT NULL, messages TEXT NOT NULL, updated REAL NOT NULL)")
    return con

def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", value):
        raise ValueError("ID de conversa inválido")
    return value

def save(chat_id, messages):
    _id(chat_id)
    if not isinstance(messages, list) or len(messages) > 10000:
        raise ValueError("Histórico excede o limite de 10.000 mensagens")
    rows = []
    for m in messages:
        if not isinstance(m, dict) or m.get("role") not in ("user", "ai") or not isinstance(m.get("text"), str):
            raise ValueError("Mensagem inválida")
        if len(m["text"]) > 500000:
            raise ValueError("Mensagem excede o limite do arquivo")
        rows.append({k:m[k] for k in ("id","role","text","durationMs","timestamp","taskId","resultStatus") if k in m})
    raw = json.dumps(rows, ensure_ascii=False)
    if len(raw.encode("utf-8")) > 16*1024*1024:
        raise ValueError("Conversa excede 16 MiB; crie outra")
    title = next((m["text"].strip().replace("\n"," ")[:70] for m in rows if m["role"]=="user" and m["text"].strip()), "Nova conversa")
    with _db() as con:
        con.execute("INSERT INTO chats VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,messages=excluded.messages,updated=excluded.updated", (chat_id,title,raw,time()))
    return {"ok":True,"title":title}

def listing():
    with _db() as con:
        rows=con.execute("SELECT id,title,updated FROM chats ORDER BY updated DESC").fetchall()
    return [{"id":r[0],"title":r[1],"updated":r[2]} for r in rows]

def load(chat_id):
    with _db() as con:
        row=con.execute("SELECT messages FROM chats WHERE id=?", (_id(chat_id),)).fetchone()
    return json.loads(row[0]) if row else []

def recall(term, limit=8):
    term=term.strip().casefold()
    if not 2<=len(term)<=120:raise ValueError("Informe um termo de 2 a 120 caracteres.")
    hits=[]
    with _db() as con:
        rows=con.execute("SELECT id,title,messages FROM chats ORDER BY updated DESC LIMIT 25").fetchall()
    for chat_id,title,raw in rows:
        for item in reversed(json.loads(raw)):
            pos=item["text"].casefold().find(term)
            if pos<0:continue
            excerpt=item["text"][max(0,pos-80):pos+220]
            hits.append({"chat":title,"id":chat_id,"role":item["role"],"excerpt":excerpt})
            if len(hits)>=limit:return hits
    return hits

def history(rows):
    # Bounded context only. Archived messages are data, not current instructions.
    return [{"role":m["role"],"text":m["text"][:3000],"id":str(m.get("id","")),"timestamp":(m.get("timestamp",0)/1000 if isinstance(m.get("timestamp"),(int,float)) and m["timestamp"]>10**11 else 0)} for m in rows[-120:]]
