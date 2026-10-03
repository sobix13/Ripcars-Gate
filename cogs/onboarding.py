from __future__ import annotations
import asyncio
import io
import time
from collections import defaultdict
import discord
from discord.ext import commands
import captcha
import core
import guildutil as gu

class CodeModal(gu.SafeModal):
    def __init__(self,cog,user,token):
        super().__init__(cog.bot,title="Enter CAPTCHA code",timeout=300)
        self.cog=cog;self.user=user;self.token=token
        self.code=discord.ui.TextInput(label="Code from the image",min_length=4,max_length=12)
        self.add_item(self.code)
    async def on_submit(self,i):
        if i.user.id!=self.user:await gu.reply(i,"This CAPTCHA belongs to another member.");return
        await i.response.defer(ephemeral=True)
        async with self.cog.locks[(i.guild_id,i.user.id)]:
            cfg,_=await self.bot.db.config(i.guild_id)
            if not cfg["enabled"]:await gu.reply(i,"Verification is paused.");return
            result=await self.bot.db.check_captcha(i.guild_id,i.user.id,self.token,self.code.value,cfg)
        if result=="passed":await self.cog.questions(i)
        else:await gu.reply(i,{"wrong":"That code did not match. Try again with the same image.","locked":"Too many attempts. Wait for the lock to expire, then start again.","expired":"This image expired. Start verification again.","stale":"This image is no longer active. Start verification again."}[result])

class CodeView(gu.SafeView):
    def __init__(self,cog,user,token,ttl):
        super().__init__(cog.bot,timeout=ttl);self.cog=cog;self.user=user;self.token=token
    @discord.ui.button(label="Enter code",style=discord.ButtonStyle.primary)
    async def enter(self,i,b):
        if i.user.id!=self.user:await gu.reply(i,"This CAPTCHA belongs to another member.");return
        await i.response.send_modal(CodeModal(self.cog,self.user,self.token))

class AnswerModal(gu.SafeModal):
    def __init__(self,cog,user,q):
        super().__init__(cog.bot,title=q["label"][:45]);self.cog=cog;self.user=user;self.qid=q["id"]
        self.answer=discord.ui.TextInput(label=q["label"],placeholder=q["prompt"],style=discord.TextStyle.paragraph,required=True,max_length=1000)
        self.add_item(self.answer)
    async def on_submit(self,i):
        if i.user.id!=self.user:await gu.reply(i,"This form belongs to another member.");return
        async with self.cog.locks[(i.guild_id,i.user.id)]:
            cfg,_=await self.bot.db.config(i.guild_id)
            if not cfg["enabled"]:raise ValueError("Verification is paused.")
            await self.bot.db.answer(i.guild_id,i.user.id,self.qid,self.answer.value,cfg)
        await self.cog.questions(i)

class Questions(gu.SafeView):
    def __init__(self,cog,user,cfg):
        super().__init__(cog.bot,timeout=900);self.cog=cog;self.user=user
        menu=discord.ui.Select(placeholder="Choose a question to answer",options=[discord.SelectOption(label=q["label"],value=q["id"],description=q["prompt"][:100]) for q in cfg["questions"] if q["enabled"]])
        async def choose(i):
            fresh,_=await self.bot.db.config(i.guild_id)
            q=next((q for q in fresh["questions"] if q["id"]==menu.values[0] and q["enabled"]),None)
            if not q:raise ValueError("That question changed. Open your status again.")
            await i.response.send_modal(AnswerModal(cog,user,q))
        menu.callback=choose;self.add_item(menu)
    async def interaction_check(self,i):
        if i.user.id!=self.user:await gu.reply(i,"This form belongs to another member.");return False
        return True
    @discord.ui.button(label="Finish and join",style=discord.ButtonStyle.success,row=1)
    async def finish(self,i,b):await self.cog.finish(i)

class VerificationView(gu.SafeView):
    def __init__(self,cog):super().__init__(cog.bot,timeout=None);self.cog=cog
    @discord.ui.button(label="Start verification",style=discord.ButtonStyle.primary,custom_id="ripcars:gate:start")
    async def start(self,i,b):await self.cog.start(i)
    @discord.ui.button(label="My status / Continue",custom_id="ripcars:gate:status")
    async def status(self,i,b):
        if not i.guild or i.user.bot:return
        cfg,_=await self.bot.db.config(i.guild_id);s=await self.bot.db.session(i.guild_id,i.user.id)
        role=await gu.resource(self.bot,i.guild,"rippers",True)
        if role and role.id in {r.id for r in i.user.roles}:await gu.reply(i,"Your member role is active.");return
        if s and s["captcha_until"]>time.time():await self.cog.questions(i);return
        await gu.reply(i,"Start verification to complete a fresh CAPTCHA.")

class Onboarding(commands.Cog):
    def __init__(self,bot):self.bot=bot;self.locks=defaultdict(asyncio.Lock)
    async def start(self,i):
        if not i.guild or i.user.bot:return
        await i.response.defer(ephemeral=True)
        async with self.locks[(i.guild_id,i.user.id)]:
            cfg,_=await self.bot.db.config(i.guild_id)
            if not cfg["enabled"]:await gu.reply(i,"Verification is being set up. Please try again later.");return
            role=await gu.resource(self.bot,i.guild,"rippers",True)
            if not role:raise ValueError("Member role is missing. Ask an admin to check Health.")
            if role.id in {r.id for r in i.user.roles}:await gu.reply(i,"Your member role is already active.");return
            s=await self.bot.db.session(i.guild_id,i.user.id)
            if s and s["captcha_until"]>time.time():await self.questions(i);return
            ch=await asyncio.to_thread(captcha.create,cfg["captcha_length"])
            token=await self.bot.db.challenge(i.guild_id,i.user.id,ch,cfg["captcha_ttl"])
        e=gu.embed(cfg,"Verify you're human",f"Enter the code below. It expires in {cfg['captcha_ttl']//60} minutes. Letters are not case-sensitive.")
        e.set_image(url="attachment://ripcars-captcha.png")
        await gu.reply(i,embed=e,file=discord.File(io.BytesIO(ch.png),filename="ripcars-captcha.png"),view=CodeView(self,i.user.id,token,cfg["captcha_ttl"]))
    async def questions(self,i):
        cfg,_=await self.bot.db.config(i.guild_id);s=await self.bot.db.session(i.guild_id,i.user.id)
        count=sum(q["id"] in (s or {}).get("answers",{}) for q in cfg["questions"] if q["enabled"])
        await gu.reply(i,embed=gu.embed(cfg,"A quick introduction",cfg["texts"]["questions_intro"]+f"\nAnswers saved: {count}"),view=Questions(self,i.user.id,cfg))
    async def finish(self,i):
        await i.response.defer(ephemeral=True)
        async with self.locks[(i.guild_id,i.user.id)]:
            cfg,_=await self.bot.db.config(i.guild_id);s=await self.bot.db.session(i.guild_id,i.user.id)
            if not cfg["enabled"]:raise ValueError("Verification is paused.")
            if not core.eligible(s,time.time()):raise ValueError("Complete the CAPTCHA and answer at least one question before joining.")
            if not any(q["enabled"] and q["id"] in s["answers"] for q in cfg["questions"]):raise ValueError("Answer at least one currently enabled question.")
            role=await gu.resource(self.bot,i.guild,"rippers",True)
            if not role or role.permissions.value!=0 or role.managed or role>=i.guild.me.top_role:
                raise ValueError("The member role needs an admin check. Your answers are saved. Check My status after it is fixed.")
            try:
                await i.user.add_roles(role,reason="Ripcars Gate: CAPTCHA and at least one answer completed")
            except discord.HTTPException as exc:
                await self.bot.db.verified(i.guild_id,i.user.id,str(exc));raise
            await self.bot.db.verified(i.guild_id,i.user.id)
            await self.bot.db.log(i.guild_id,i.user.id,"onboarding_complete",f"answered={len(s['answers'])}")
        await gu.reply(i,embed=gu.embed(cfg,"Welcome to the garage",cfg["texts"]["success"]))
    @commands.Cog.listener()
    async def on_member_join(self,member):
        if not member.bot:await self.bot.db.begin(member.guild.id,member.id,reset=True)

async def setup(bot):await bot.add_cog(Onboarding(bot))
