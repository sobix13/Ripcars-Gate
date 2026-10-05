"""SQLite transactions. Operational data and future-bot coordination are separate."""
from __future__ import annotations
import asyncio
import copy
import json
import re
import sqlite3
import time
import uuid
import ripcars_coordination as protocol
from pathlib import Path
from contextlib import asynccontextmanager
import captcha
import core

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(guild INTEGER PRIMARY KEY,revision INTEGER NOT NULL,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY AUTOINCREMENT,guild INTEGER,actor INTEGER,at REAL,body TEXT);
CREATE TABLE IF NOT EXISTS sessions(guild INTEGER,user INTEGER,challenge TEXT DEFAULT '',salt TEXT DEFAULT '',digest TEXT DEFAULT '',expires REAL DEFAULT 0,captcha_until REAL DEFAULT 0,attempts INTEGER DEFAULT 0,locked_until REAL DEFAULT 0,answers TEXT DEFAULT '{}',verified INTEGER DEFAULT 0,role_error TEXT DEFAULT '',PRIMARY KEY(guild,user));
CREATE TABLE IF NOT EXISTS profiles(guild INTEGER,user INTEGER,answers TEXT,updated REAL,PRIMARY KEY(guild,user));
CREATE TABLE IF NOT EXISTS resources(guild INTEGER,key TEXT,object_id INTEGER,kind TEXT,owner TEXT,baseline TEXT,desired TEXT,state TEXT DEFAULT 'active',PRIMARY KEY(guild,key),UNIQUE(guild,object_id));
CREATE TABLE IF NOT EXISTS panels(guild INTEGER,key TEXT,channel INTEGER,message INTEGER,PRIMARY KEY(guild,key));
CREATE TABLE IF NOT EXISTS integrations(guild INTEGER,bot INTEGER,scope TEXT,grants TEXT DEFAULT '{}',active INTEGER DEFAULT 0,PRIMARY KEY(guild,bot));
CREATE TABLE IF NOT EXISTS leases(guild INTEGER,key TEXT,token TEXT,expires REAL,PRIMARY KEY(guild,key));
CREATE TABLE IF NOT EXISTS cooldowns(guild INTEGER,user INTEGER,key TEXT,at REAL,PRIMARY KEY(guild,user,key));
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,guild INTEGER,actor INTEGER,at REAL,area TEXT,details TEXT);
"""

class Conflict(ValueError): pass

class Database:
    def __init__(self, path, coordination_path=None, shared=False):
        if coordination_path and Path(path).resolve()==Path(coordination_path).resolve():raise ValueError('Operational and coordination databases must be separate.')
        self.path = str(path); self._conn = None; self._lock = asyncio.Lock()
        self.shared=shared
        self.coordination=Database(coordination_path,shared=True) if coordination_path else None
    async def connect(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        def init():
            self._conn = sqlite3.connect(self.path, timeout=15, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=15000")
            self._conn.executescript(SCHEMA)
            protocol.initialize(self._conn,Conflict); self._conn.commit()
            if self.shared:protocol.shared_permissions(self.path)
        await asyncio.to_thread(init)
        if self.coordination:await self.coordination.connect()
    async def run(self, fn):
        async with self._lock:
            def transaction():
                try:
                    self._conn.execute("BEGIN IMMEDIATE")
                    value = fn(self._conn); self._conn.commit(); return value
                except BaseException:
                    self._conn.rollback(); raise
            task=asyncio.create_task(asyncio.to_thread(transaction))
            try:return await asyncio.shield(task)
            except asyncio.CancelledError:
                try:await task
                finally:raise
    async def close(self):
        if self.coordination:await self.coordination.close()
        async with self._lock:
            if self._conn:
                await asyncio.to_thread(self._conn.close); self._conn = None
    async def query(self, sql, args=()):
        store=self.coordination if self.coordination and re.search(r"\b(resources|integrations|leases|locks|suite_meta)\b",sql,re.I) else self
        return await store.run(lambda c: [dict(r) for r in c.execute(sql,args).fetchall()])
    async def execute(self, sql, args=()):
        store=self.coordination if self.coordination and re.search(r"\b(resources|integrations|leases|locks|suite_meta)\b",sql,re.I) else self
        return await store.run(lambda c: c.execute(sql,args).rowcount)
    async def config(self, guild):
        def get(c):
            row = c.execute("SELECT * FROM settings WHERE guild=?",(guild,)).fetchone()
            if not row:
                cfg = core.defaults(); c.execute("INSERT INTO settings VALUES(?,?,?)",(guild,1,json.dumps(cfg))); return cfg,1
            return json.loads(row["body"]),row["revision"]
        return await self.run(get)
    async def save_config(self, guild, cfg, revision, actor):
        core.validate(cfg)
        def save(c):
            row = c.execute("SELECT body,revision FROM settings WHERE guild=?",(guild,)).fetchone()
            if not row or row["revision"] != revision: raise Conflict("Settings changed. Reopen this section before saving.")
            c.execute("INSERT INTO history(guild,actor,at,body) VALUES(?,?,?,?)",(guild,actor,time.time(),row["body"]))
            c.execute("UPDATE settings SET body=?,revision=revision+1 WHERE guild=?",(json.dumps(cfg),guild))
            c.execute("DELETE FROM history WHERE guild=? AND id NOT IN (SELECT id FROM history WHERE guild=? ORDER BY id DESC LIMIT 30)",(guild,guild))
        await self.run(save)
    async def begin(self, guild, user, reset=False):
        await self.execute("INSERT OR IGNORE INTO sessions(guild,user) VALUES(?,?)",(guild,user))
        if reset:
            await self.execute("UPDATE sessions SET challenge='',captcha_until=0,answers='{}',verified=0,role_error='' WHERE guild=? AND user=?",(guild,user))
    async def session(self, guild,user):
        rows = await self.query("SELECT * FROM sessions WHERE guild=? AND user=?",(guild,user))
        if not rows: return None
        row=rows[0]; row["answers"]=json.loads(row["answers"]); return row
    async def challenge(self,guild,user,ch,ttl):
        now=time.time(); token=uuid.uuid4().hex
        def write(c):
            row=c.execute("SELECT * FROM sessions WHERE guild=? AND user=?",(guild,user)).fetchone()
            if row and row["locked_until"] > now: raise ValueError("Too many attempts. Try again after the lock expires.")
            if row and row["expires"] > now + ttl-10: raise ValueError("A CAPTCHA was just created. Use that image or wait 10 seconds.")
            c.execute("INSERT OR IGNORE INTO sessions(guild,user) VALUES(?,?)",(guild,user))
            c.execute("UPDATE sessions SET challenge=?,salt=?,digest=?,expires=?,captcha_until=0,attempts=CASE WHEN locked_until>0 THEN 0 ELSE attempts END,locked_until=0 WHERE guild=? AND user=?",(token,ch.salt,ch.digest,now+ttl,guild,user))
        await self.run(write); return token
    async def check_captcha(self,guild,user,token,answer,cfg,now=None):
        now=time.time() if now is None else now
        def check(c):
            row=c.execute("SELECT * FROM sessions WHERE guild=? AND user=?",(guild,user)).fetchone()
            if not row or row["challenge"] != token or not token: return "stale"
            if row["locked_until"]>now:return "locked"
            if row["expires"]<now:return "expired"
            if not captcha.verify(answer,row["salt"],row["digest"]):
                attempts=row["attempts"]+1; lock=now+cfg["lock_seconds"] if attempts>=cfg["max_attempts"] else 0
                c.execute("UPDATE sessions SET attempts=?,locked_until=? WHERE guild=? AND user=?",(attempts,lock,guild,user));return "locked" if lock else "wrong"
            c.execute("UPDATE sessions SET challenge='',salt='',digest='',expires=0,captcha_until=?,attempts=0,locked_until=0 WHERE guild=? AND user=?",(now+cfg["answer_ttl"],guild,user)); return "passed"
        return await self.run(check)
    async def answer(self,guild,user,qid,value,cfg):
        value=core.normalize_answer(value)
        if not value: raise ValueError("Enter a response. At least one question is required.")
        if not any(q["id"]==qid and q["enabled"] for q in cfg["questions"]): raise ValueError("This question is no longer enabled.")
        now=time.time()
        def write(c):
            row=c.execute("SELECT * FROM sessions WHERE guild=? AND user=?",(guild,user)).fetchone()
            if not row or row["captcha_until"]<now:raise ValueError("Complete a fresh CAPTCHA before answering.")
            answers=json.loads(row["answers"]); answers[qid]=value
            c.execute("UPDATE sessions SET answers=? WHERE guild=? AND user=?",(json.dumps(answers),guild,user))
            c.execute("INSERT INTO profiles VALUES(?,?,?,?) ON CONFLICT(guild,user) DO UPDATE SET answers=excluded.answers,updated=excluded.updated",(guild,user,json.dumps(answers),now))
        await self.run(write)
    async def verified(self,guild,user,error=""):
        await self.execute("UPDATE sessions SET verified=?,role_error=? WHERE guild=? AND user=?",(0 if error else 1,error[:300],guild,user))
    async def verification_stats(self,guild):
        rows=await self.query("SELECT COUNT(*) AS members,SUM(verified=0) AS waiting,SUM(verified=1) AS verified,SUM(locked_until>?) AS locked,SUM(role_error!='') AS role_errors FROM sessions WHERE guild=?",(time.time(),guild)); return rows[0]
    async def resources(self,guild):
        rows=await self.query("SELECT * FROM resources WHERE guild=?",(guild,))
        return {r["key"]:{**r,"baseline":json.loads(r["baseline"]),"desired":json.loads(r["desired"])} for r in rows}
    async def register(self,guild,key,oid,kind,baseline,desired=None,owner=core.OWNER):
        def put(c):
            old=c.execute('SELECT owner FROM resources WHERE guild=? AND key=?',(guild,key)).fetchone()
            if old and old['owner']!=owner:raise Conflict('This resource belongs to another controller. Explicit handoff is required; its binding was preserved.')
            duplicate=c.execute('SELECT key FROM resources WHERE guild=? AND object_id=? AND key!=?',(guild,oid,key)).fetchone()
            if duplicate:raise Conflict('This object ID is already registered under another resource key.')
            c.execute("INSERT INTO resources VALUES(?,?,?,?,?,?,?,'active') ON CONFLICT(guild,key) DO UPDATE SET object_id=excluded.object_id,kind=excluded.kind,owner=excluded.owner,baseline=excluded.baseline,desired=excluded.desired,state='active'",(guild,key,oid,kind,owner,json.dumps(baseline),json.dumps(desired if desired is not None else baseline)))
        await (self.coordination or self).run(put)
    async def state(self,guild,key,state):
        await self.execute("UPDATE resources SET state=? WHERE guild=? AND key=?",(state,guild,key))
    async def baseline(self,guild,key,value):
        await self.execute("UPDATE resources SET baseline=?,state='active' WHERE guild=? AND key=?",(json.dumps(value),guild,key))
    async def lease(self,guild,key,ttl=180):
        return await (self.coordination or self).run(lambda c:protocol.claim(c,guild,key,ttl,error=Conflict))
    async def renew(self,guild,key,token,ttl=180):
        await (self.coordination or self).run(lambda c:protocol.renew(c,guild,key,token,ttl,error=Conflict))
    async def release(self,guild,key,token):
        await (self.coordination or self).run(lambda c:protocol.release(c,guild,key,token))
    @asynccontextmanager
    async def coordinated(self,guild):
        token=await self.lease(guild,'server-setup')
        try:yield token
        finally:await self.release(guild,'server-setup',token)
    async def handoff(self,guild,keys,bot_id):
        if type(bot_id) is not int or bot_id<=0:raise Conflict('A numeric companion bot ID is required.')
        new_owner=f'bot:{bot_id}'
        async with self.coordinated(guild) as token:
            def transfer(c):
                protocol.ensure(c,guild,'server-setup',token,error=Conflict)
                for key in keys:
                    row=c.execute('SELECT owner,state FROM resources WHERE guild=? AND key=?',(guild,key)).fetchone()
                    if not row or (row['owner']==core.OWNER and row['state'] not in ('active','pinned')) or row['owner'] not in (core.OWNER,new_owner):
                        raise Conflict('Handoff requires reviewed Gate-owned resources. No ownership was changed.')
                    if row['owner']==new_owner and row['state']!='external':raise Conflict('Companion resource is protected; handoff was stopped.')
                for key in keys:c.execute("UPDATE resources SET owner=?,state='external' WHERE guild=? AND key=?",(new_owner,guild,key))
            await (self.coordination or self).run(transfer)
    async def reserve_post(self,guild,user,key,delay):
        now=time.time()
        def take(c):
            row=c.execute("SELECT at FROM cooldowns WHERE guild=? AND user=? AND key=?",(guild,user,key)).fetchone()
            if row and row[0]+delay>now:raise ValueError(f"Your next post is available in {int((row[0]+delay-now+59)//60)} minute(s).")
            c.execute("INSERT INTO cooldowns VALUES(?,?,?,?) ON CONFLICT(guild,user,key) DO UPDATE SET at=excluded.at",(guild,user,key,now));return now
        return await self.run(take)
    async def cancel_post(self,guild,user,key,stamp):
        await self.execute("DELETE FROM cooldowns WHERE guild=? AND user=? AND key=? AND at=?",(guild,user,key,stamp))
    async def log(self,guild,actor,area,details):
        await self.execute("INSERT INTO audit(guild,actor,at,area,details) VALUES(?,?,?,?,?)",(guild,actor,time.time(),area,str(details)[:2000]))
        await self.execute("DELETE FROM audit WHERE guild=? AND id NOT IN (SELECT id FROM audit WHERE guild=? ORDER BY id DESC LIMIT 5000)",(guild,guild))
