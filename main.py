"""Independent Ripcars Gate process. No support, guard, or holder bot is required."""
from __future__ import annotations
import asyncio
import logging
import os
import sys
from pathlib import Path
from collections import defaultdict
import discord
from discord.ext import commands
import core
import db
import health
import alerts
import guildutil as gu
from server import Provisioner

ROOT=Path(__file__).resolve().parent
def load_env(path):
    if not path.exists():return
    for line in path.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith("#") or "=" not in line:continue
        key,value=line.split("=",1);value=value.strip()
        if len(value)>1 and value[0]==value[-1] and value[0] in ("'",'"'):value=value[1:-1]
        os.environ.setdefault(key.strip(),value)
load_env(ROOT/".env")
logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)-7s %(name)s %(message)s")
log=logging.getLogger("ripcarsgate")

class GateBot(commands.Bot):
    def __init__(self,db_path=None,coordination_path=None):
        intents=discord.Intents.default();intents.members=True;intents.message_content=True
        super().__init__(command_prefix=commands.when_mentioned,intents=intents,
                         allowed_mentions=discord.AllowedMentions.none())
        self.db_path=str(db_path or os.environ.get("DB_PATH",ROOT/"data/gate.sqlite3"))
        self.coordination_path=str(coordination_path or os.environ.get("COORDINATION_PATH",ROOT/"data/coordination.sqlite3"))
        self.db=db.Database(self.db_path,self.coordination_path)
        self.version=core.VERSION;self.watchdog=health.Watchdog();self.errors=health.ErrorLog()
        self.alerts=alerts.AlertReporter(self);self.provisioner=Provisioner(self)
        self.member_locks=defaultdict(asyncio.Lock);self.tasks=[]
    async def setup_hook(self):
        await self.db.connect();self.tree.on_error=self.on_tree_error
        for name in ("onboarding","community","admin"):
            await self.load_extension("cogs."+name);log.info("loaded %s",name)
        from cogs.onboarding import VerificationView
        from cogs.community import ClaimsView,GcarsView
        for view in (VerificationView(self.get_cog("Onboarding")),ClaimsView(self),GcarsView(self)):self.add_view(view)
        guild_id=os.environ.get("GUILD_ID","").strip()
        if guild_id:
            obj=discord.Object(id=int(guild_id));self.tree.copy_global_to(guild=obj);await self.tree.sync(guild=obj)
        else:await self.tree.sync()
        for coro in (health.heartbeat_loop(self),health.backup_loop(self),self.monitor()):self.tasks.append(asyncio.create_task(coro))
    async def on_ready(self):log.info("online as %s version %s in %d guilds",self.user,self.version,len(self.guilds))
    async def monitor(self):
        await self.wait_until_ready()
        while not self.is_closed():
            for guild in self.guilds:
                try:
                    if guild.id in self.provisioner.busy:continue
                    changes=await self.provisioner.scan(guild)
                    cfg,_=await self.db.config(guild.id)
                    if cfg["auto_repair"] and await self.db.resources(guild.id):
                        results=await self.provisioner.apply(guild,None,automatic=True)
                        failed=[r for r in results if r.startswith("FAILED")]
                        if failed:await gu.report(self,guild,"managed permissions",RuntimeError("\n".join(failed)[:1500]))
                    if changes:
                        await self.db.log(guild.id,None,"protected_changes","\n".join(changes))
                        ch=guild.get_channel(cfg["ops_channel_id"] or 0)
                        if ch:await ch.send(embed=gu.embed(cfg,"Changes preserved","\n".join(changes)),allowed_mentions=discord.AllowedMentions.none())
                except asyncio.CancelledError:raise
                except db.Conflict:continue
                except Exception as exc:await gu.report(self,guild,"resource monitoring",exc)
            await asyncio.sleep(60)
    async def on_tree_error(self,i,error):
        original=getattr(error,"original",error)
        if isinstance(original,ValueError):await gu.reply(i,str(original));return
        if isinstance(error,discord.app_commands.CheckFailure):await gu.reply(i,"This command is not available to your role.");return
        eid=await gu.report(self,i.guild,"command",original)
        log.error("command failed %s",eid,exc_info=(type(original),original,original.__traceback__))
        await gu.reply(i,f"Something went wrong. Error ID: {eid}. Ask an admin to check /gate health.")
    async def on_error(self,event,*args,**kwargs):
        exc=sys.exc_info()[1]
        if exc:
            guild=next((getattr(x,"guild",None) for x in args if getattr(x,"guild",None)),None)
            await gu.report(self,guild,event,exc)
        log.exception("event failed: %s",event)
    async def close(self):
        self.watchdog.stopping()
        for task in self.tasks:task.cancel()
        if self.tasks:await asyncio.gather(*self.tasks,return_exceptions=True)
        await self.db.close();await super().close()

async def amain():
    token=os.environ.get("DISCORD_TOKEN","").strip()
    if not token:raise SystemExit("DISCORD_TOKEN is missing. Create .env from .env.example.")
    async with GateBot() as bot:await bot.start(token)
if __name__=="__main__":
    try:asyncio.run(amain())
    except KeyboardInterrupt:pass
