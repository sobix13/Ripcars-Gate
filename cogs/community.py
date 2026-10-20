from __future__ import annotations
import asyncio
import discord
from discord.ext import commands
import core
import guildutil as gu

class ClaimsView(gu.SafeView):
    def __init__(self,bot,cfg=None):
        super().__init__(bot,timeout=None)
        labels=(cfg or core.DEFAULTS)["claims"]
        for key in core.CLAIM_KEYS:
            button=discord.ui.Button(label=labels[key][:80],custom_id="ripcars:claim:"+key)
            async def toggle(i,k=key):
                await i.response.defer(ephemeral=True)
                cfg,_=await self.bot.db.config(i.guild_id)
                if not cfg.get('claims_enabled',True):return await gu.reply(i,'Optional role claims are turned off.')
                if not await gu.member_gate(self.bot,i):return
                async with self.bot.member_locks[(i.guild_id,i.user.id)]:
                    role=await gu.resource(self.bot,i.guild,"claim_"+k,True)
                    if not role or role.permissions.value or role.managed or role>=i.guild.me.top_role:raise ValueError("This claim role needs an admin check.")
                    present=role.id in {r.id for r in i.user.roles}
                    if present:await i.user.remove_roles(role,reason="Ripcars Gate: optional role removed")
                    else:await i.user.add_roles(role,reason="Ripcars Gate: optional role claimed")
                await gu.reply(i,f"{role.name}: {'removed' if present else 'added'}.")
            button.callback=toggle;self.add_item(button)

class PostModal(gu.SafeModal):
    def __init__(self,bot):
        super().__init__(bot,title="Submit to gCARS")
        self.text=discord.ui.TextInput(label="Your text",style=discord.TextStyle.paragraph,max_length=1800)
        self.add_item(self.text)
    async def on_submit(self,i):
        await i.response.defer(ephemeral=True)
        cfg,_=await self.bot.db.config(i.guild_id)
        if not cfg.get('gcars_enabled',True):return await gu.reply(i,'gCARS submissions are turned off.')
        if not await gu.member_gate(self.bot,i):return
        text=self.text.value.strip()
        if not text or core.has_link(text) or "<@" in text or "@everyone" in text or "@here" in text:
            raise ValueError("Use plain text without links or mentions.")
        row=(await self.bot.db.resources(i.guild_id)).get("channel:gcars")
        if not row or row["owner"]!=core.OWNER or row["state"] not in ("active","pinned"):raise ValueError("gCARS is paused for an admin review.")
        cfg,_=await self.bot.db.config(i.guild_id)
        channel=i.guild.get_channel(row["object_id"])
        if not channel or not channel.permissions_for(i.user).view_channel:raise ValueError("This channel is unavailable.")
        if not channel.permissions_for(i.guild.me).view_channel or not channel.permissions_for(i.guild.me).send_messages or not channel.permissions_for(i.guild.me).embed_links:
            raise ValueError('gCARS is unavailable. Ask staff to check channel access.')
        stamp=await self.bot.db.reserve_post(i.guild_id,i.user.id,"gcars",cfg["blueprint"]["gcars"]["slowmode"])
        try:
            e=gu.embed(cfg,i.user.display_name,text);e.set_footer(text=f"{cfg['brand']} · Member ID {i.user.id}")
            await channel.send(embed=e,allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            await self.bot.db.cancel_post(i.guild_id,i.user.id,"gcars",stamp);raise
        await gu.reply(i,"Your text has been posted.")

class GcarsView(gu.SafeView):
    def __init__(self,bot):super().__init__(bot,timeout=None)
    @discord.ui.button(label="Submit text",style=discord.ButtonStyle.primary,custom_id="ripcars:gcars:submit")
    async def submit(self,i,b):
        cfg,_=await self.bot.db.config(i.guild_id)
        if not cfg.get('gcars_enabled',True):return await gu.reply(i,'gCARS submissions are turned off.')
        if await gu.member_gate(self.bot,i):await i.response.send_modal(PostModal(self.bot))

class Community(commands.Cog):
    def __init__(self,bot):self.bot=bot
    @commands.Cog.listener()
    async def on_message(self,msg):
        if not msg.guild or msg.author.bot or msg.author.guild_permissions.manage_messages:return
        cfg,_=await self.bot.db.config(msg.guild.id)
        if not cfg.get('channel_filters_enabled',True):return
        rows=await self.bot.db.resources(msg.guild.id)
        row=next((r for k,r in rows.items() if k.startswith("channel:") and r["object_id"]==getattr(msg.channel,"parent_id",None)),None) if isinstance(msg.channel,discord.Thread) else next((r for k,r in rows.items() if k.startswith("channel:") and r["object_id"]==msg.channel.id),None)
        if not row or row["owner"]!=core.OWNER or row["state"] not in ("active","pinned"):return
        spec=cfg["blueprint"].get(row["key"][8:])
        if not spec:return
        if not msg.channel.permissions_for(msg.guild.me).view_channel or not msg.channel.permissions_for(msg.guild.me).manage_messages:return
        reason=None
        if not spec["links"] and core.has_link(msg.content):reason="Links are not allowed in this channel."
        if msg.attachments and (not spec["images"] or any(not (a.content_type or "").startswith("image/") for a in msg.attachments)):
            reason="This channel accepts image uploads only." if spec["images"] else "Files are not allowed in this channel."
        if reason:
            try:
                await msg.delete()
            except discord.NotFound:
                # A companion moderator may have deleted the same message already.
                # Do not create a duplicate notice or a false health error.
                return
            try:await msg.author.send(reason,allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:pass
            await self.bot.db.log(msg.guild.id,msg.author.id,"channel_filter",f"channel={msg.channel.id}; {reason}")

async def setup(bot):await bot.add_cog(Community(bot))
