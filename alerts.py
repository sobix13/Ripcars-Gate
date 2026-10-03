"""Rate-limited Discord operational reporting, with no secret values in alerts."""
import hashlib
import time
import discord
import guildutil as gu

class AlertReporter:
    def __init__(self,bot):self.bot=bot;self.sent={}
    async def notify(self,guild,where,entry,context=None):
        if not guild:return False
        try:
            cfg,_=await self.bot.db.config(guild.id)
            ch=guild.get_channel(cfg["ops_channel_id"] or 0)
            if not ch:return False
            fingerprint=hashlib.sha256(f"{guild.id}:{where}:{entry['type']}:{entry['message']}".encode()).hexdigest()
            if time.monotonic()-self.sent.get(fingerprint,-1000)<60:return False
            self.sent[fingerprint]=time.monotonic()
            e=gu.embed(cfg,"Ripcars Gate error",f"Error ID: {entry['id']}\nArea: {where}\nType: {entry['type']}\nMessage: {entry['message']}\n{context or ''}")
            e.set_footer(text="Full trace: journalctl -u ripcars-gate")
            await ch.send(embed=e,allowed_mentions=discord.AllowedMentions.none());return True
        except Exception:return False
    async def notify_all(self,where,entry,context=None):
        for guild in self.bot.guilds:await self.notify(guild,where,entry,context)
