"""Local explicit notes. No model access or execution authority."""
from pathlib import Path
import sqlite3
import time
import uuid
import re
import os
from contextlib import contextmanager


def default_path():
    return Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'BRAINNET' / 'workspace_notes.sqlite3'


class Notes:
    def __init__(self, path=None):
        self.path = Path(path or default_path())

    @contextmanager
    def db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.path, timeout=5)
        c.row_factory = sqlite3.Row
        try:
            with c:
                c.execute('CREATE TABLE IF NOT EXISTS notes (id TEXT PRIMARY KEY, title TEXT NOT NULL, title_key TEXT UNIQUE NOT NULL, body TEXT NOT NULL, revision INTEGER NOT NULL, updated REAL NOT NULL)')
                yield c
        finally:
            c.close()

    def list(self, query=''):
        if not isinstance(query, str) or len(query) > 200:
            raise ValueError('Busca inválida')
        q = query.casefold().strip()
        with self.db() as c:
            rows = c.execute('SELECT id,title,body,revision,updated FROM notes ORDER BY updated DESC').fetchall()
            return [{k: r[k] for k in ('id','title','revision','updated')} for r in rows if q in (r['title']+' '+r['body']).casefold()][:500]

    def get(self, note_id):
        with self.db() as c:
            r = c.execute('SELECT id,title,body,revision,updated FROM notes WHERE id=?', (note_id,)).fetchone()
            if r is None:
                raise ValueError('Nota não encontrada')
            links = []
            rows = c.execute('SELECT id,title,title_key,body FROM notes').fetchall()
            index = {n['title_key']: n for n in rows}
            for name in dict.fromkeys(re.findall(r'\[\[([^\[\]\n]{1,160})\]\]', r['body'])):
                dest = index.get(name.strip().casefold())
                links.append({'title':name, 'id':dest['id'] if dest else None})
            backlinks = [{'id':n['id'],'title':n['title']} for n in rows if n['id'] != note_id and r['title'].casefold() in [v.strip().casefold() for v in re.findall(r'\[\[([^\[\]\n]{1,160})\]\]',n['body'])]]
            return {**dict(r), 'links':links, 'backlinks':backlinks}

    def save(self, note_id, title, body, revision):
        if not isinstance(title,str) or not isinstance(body,str):
            raise ValueError('Texto inválido')
        title = title.strip()
        if not title or len(title)>160 or '\n' in title or '\r' in title or len(body)>200000:
            raise ValueError('Título ou conteúdo fora do limite')
        if type(revision) is not int or revision < 0:
            raise ValueError('Revisão inválida')
        try:
            with self.db() as c:
                if note_id is None:
                    if revision != 0: raise ValueError('Revisão inválida')
                    note_id = uuid.uuid4().hex
                    c.execute('INSERT INTO notes VALUES (?,?,?,?,?,?)',(note_id,title,title.casefold(),body,1,time.time()))
                else:
                    result = c.execute('UPDATE notes SET title=?, title_key=?, body=?, revision=revision+1, updated=? WHERE id=? AND revision=?',(title,title.casefold(),body,time.time(),note_id,revision))
                    if result.rowcount != 1: raise ValueError('Nota alterada ou inexistente. Reabra antes de salvar.')
        except sqlite3.IntegrityError as exc:
            raise ValueError('Já existe nota com esse título') from exc
        return self.get(note_id)

    def by_title(self, title):
        if not isinstance(title,str) or not title.strip() or len(title)>160:
            raise ValueError('Título inválido')
        with self.db() as c:
            r=c.execute('SELECT id FROM notes WHERE title_key=?',(title.strip().casefold(),)).fetchone()
        if r is None: raise ValueError('Nota não encontrada: '+title)
        return self.get(r['id'])

    def link(self, source, target):
        a=self.by_title(source);b=self.by_title(target)
        if a['id']==b['id']:raise ValueError('Escolha duas notas distintas')
        if any(x['id']==b['id'] for x in a['links']):return a
        return self.save(a['id'],a['title'],a['body'].rstrip()+'\n\n[['+b['title']+']]\n',a['revision'])
