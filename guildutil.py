from __future__ import annotations
import discord
import logging
import core

def embed(cfg, title, description=""):
    e=discord.Embed(title=title[:256],description=description[:4000] or None,color=cfg["color"])
    e.set_footer(text=cfg["brand"]);return e

async def reply(interaction, content=None, **kwargs):
    kwargs.setdefault("ephemeral",True)
    kwargs.setdefault("allowed_mentions",discord.AllowedMentions.none())
    if interaction.response.is_done(): return await interaction.followup.send(content,**kwargs)
    return await interaction.response.send_message(content,**kwargs)

async def authorized(bot, interaction, mod=False):
    if not interaction.guild or interaction.user.bot:return False
    perms=interaction.user.guild_permissions
    if interaction.user.id==interaction.guild.owner_id or perms.administrator:return True
    if mod:
        res=await bot.db.resources(interaction.guild.id)
        role=res.get("role:moderator",{}).get("object_id")
        return role in {r.id for r in interaction.user.roles}
    return False

async def require(bot, interaction, mod=False):
    ok=await authorized(bot,interaction,mod)
    if not ok:await reply(interaction,"This section is available to server admins." if not mod else "This section is available to server staff.")
    return ok

async def resource(bot,guild,key,role=False):
    r=(await bot.db.resources(guild.id)).get(("role:" if role else "channel:")+key)
    if not r:return None
    return guild.get_role(r["object_id"]) if role else guild.get_channel(r["object_id"])

async def member_gate(bot,interaction):
    if not interaction.guild or interaction.user.bot:return False
    role=await resource(bot,interaction.guild,"rippers",True)
    if not role or role.id not in {r.id for r in interaction.user.roles}:
        await reply(interaction,"Complete verification and at least one question first.");return False
    return True

async def report(bot,guild,area,exc):
    entry=bot.errors.record(area,exc)
    logging.getLogger("ripcarsgate.errors").error("%s: %s",entry["id"],area,exc_info=(type(exc),exc,exc.__traceback__))
    try:
        await bot.db.log(guild.id if guild else 0,None,"error",f"{entry['id']} {area}: {type(exc).__name__}: {str(exc)[:300]}")
    except Exception:pass
    await bot.alerts.notify(guild,area,entry)
    return entry["id"]

class SafeView(discord.ui.View):
    def __init__(self,bot,*args,**kwargs):super().__init__(*args,**kwargs);self.bot=bot
    async def on_error(self,interaction,error,item):
        if isinstance(error,ValueError):await reply(interaction,str(error));return
        eid=await report(self.bot,interaction.guild,"panel",error)
        await reply(interaction,f"Something went wrong. Error ID: {eid}. Ask a server admin to check Health.")

class SafeModal(discord.ui.Modal):
    def __init__(self,bot,*args,**kwargs):super().__init__(*args,**kwargs);self.bot=bot
    async def on_error(self,interaction,error):
        if isinstance(error,ValueError):await reply(interaction,str(error));return
        eid=await report(self.bot,interaction.guild,"form",error)
        await reply(interaction,f"Something went wrong. Error ID: {eid}.")
