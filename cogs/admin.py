from __future__ import annotations
import asyncio
import copy
import csv
import io
import json
import time
import discord
from discord import app_commands
from discord.ext import commands
import core
import health
import guildutil as gu
from server import role_snapshot,channel_snapshot
from .onboarding import VerificationView
from .community import ClaimsView,GcarsView

SECTIONS={
    "server":("Server setup","Preview and build categories, channels, roles, and access."),
    "onboarding":("Entry & CAPTCHA","Activate entry and adjust CAPTCHA rules."),
    "questions":("Questions","Edit, add, or disable onboarding questions."),
    "texts":("Messages","Edit welcome, rules, FAQ, and public panel text."),
    "branding":("Brand & roles","Brand name, website, color, and role names."),
    "channels":("Channels & access","Channel names, types, access, media, and slowmode."),
    "resources":("Resources & manual changes","Bind IDs and review protected changes."),
    "integrations":("Future bots","Register trusted bots. No companion bot is required."),
    "health":("Health & troubleshooting","Database, backups, permissions, and recent errors."),
    "data":("Member data & history","Export answers and review previous settings."),
    "help":("Guide","Setup, permissions, and daily operation."),
}

class AdminView(gu.SafeView):
    def __init__(self,cog,user,timeout=600):super().__init__(cog.bot,timeout=timeout);self.cog=cog;self.user=user
    async def interaction_check(self,i):
        if i.user.id!=self.user:await gu.reply(i,"Open your own /gate panel.");return False
        return await gu.require(self.bot,i)

class Confirm(AdminView):
    def __init__(self,cog,user,action,label="Apply"):
        super().__init__(cog,user);self.action=action;self.used=False
        self.confirm.label=label
    @discord.ui.button(label="Apply",style=discord.ButtonStyle.success)
    async def confirm(self,i,b):
        if self.used:await gu.reply(i,"This action was already submitted.");return
        self.used=True;self.confirm.disabled=True
        await i.response.defer(ephemeral=True)
        await self.action(i)
    @discord.ui.button(label="Cancel")
    async def cancel(self,i,b):self.used=True;self.stop();await i.response.edit_message(content="Cancelled.",embed=None,view=None)

class Editor(gu.SafeModal):
    def __init__(self,cog,user,cfg,revision,title,fields,save):
        super().__init__(cog.bot,title=title[:45]);self.cog=cog;self.user=user;self.cfg=copy.deepcopy(cfg);self.revision=revision;self.save=save;self.inputs={}
        for key,label,value,maxlen in fields:
            inp=discord.ui.TextInput(label=label[:45],default=str(value)[:maxlen],style=discord.TextStyle.paragraph if maxlen>200 else discord.TextStyle.short,max_length=maxlen,required=True)
            self.inputs[key]=inp;self.add_item(inp)
    async def on_submit(self,i):
        if i.user.id!=self.user or not await gu.require(self.bot,i):return
        values={key:x.value.strip() for key,x in self.inputs.items()}
        self.save(self.cfg,values)
        await self.bot.db.save_config(i.guild_id,self.cfg,self.revision,i.user.id)
        await gu.reply(i,"Saved. Active managed resources update at the next monitoring pass. Preview setup for structural changes. Use Publish panels to refresh public messages.")

class Choice(AdminView):
    def __init__(self,cog,user,options,action,placeholder="Choose an item"):
        super().__init__(cog,user)
        menu=discord.ui.Select(placeholder=placeholder,options=options)
        async def choose(i):await action(i,menu.values[0])
        menu.callback=choose;self.add_item(menu)

class Hub(AdminView):
    def __init__(self,cog,user):
        super().__init__(cog,user)
        menu=discord.ui.Select(placeholder="Choose a section",options=[discord.SelectOption(label=name,value=k,description=desc[:100]) for k,(name,desc) in SECTIONS.items()])
        async def choose(i):await cog.section(i,menu.values[0])
        menu.callback=choose;self.add_item(menu)

class SectionView(AdminView):
    def __init__(self,cog,user,key):
        super().__init__(cog,user);self.key=key
        actions={
            "server":[("Preview setup","preview"),("Publish panels","publish")],
            "onboarding":[("Activate / Pause","toggle"),("CAPTCHA settings","captcha")],
            "questions":[("Edit a question","question"),("Add a question","add_question")],
            "texts":[("Edit a message","text"),("Publish panels","publish")],
            "branding":[("Edit branding","brand"),("Role names","roles")],
            "channels":[("Channels","channel"),("Categories","category")],
            "resources":[("Bind an existing ID","bind"),("Review a resource","review")],
            "integrations":[("Register a bot","integration"),("Review / activate","integration_review")],
            "health":[("Refresh","health"),("Backup now","backup"),("Scan permissions","scan")],
            "data":[("Export answers","export"),("Settings history","history")],
            "help":[],
        }[key]
        for label,action in actions:
            button=discord.ui.Button(label=label,style=discord.ButtonStyle.primary)
            async def run(i,a=action):await cog.action(i,a)
            button.callback=run;self.add_item(button)
    @discord.ui.button(label="Home",row=4)
    async def home(self,i,b):await self.cog.panel(i)

class Admin(commands.Cog):
    gate=app_commands.Group(name="gate",description="Ripcars Gate administration and help",guild_only=True)
    def __init__(self,bot):self.bot=bot
    @gate.command(name="panel",description="Open the admin setup center")
    @app_commands.default_permissions(administrator=True)
    async def gate_panel(self,i:discord.Interaction):
        if await gu.require(self.bot,i):await self.panel(i)
    @gate.command(name="health",description="Check health and permission blockers")
    @app_commands.default_permissions(manage_messages=True)
    async def gate_health(self,i:discord.Interaction):
        if await gu.require(self.bot,i,mod=True):await self.show_health(i)
    @gate.command(name="guide",description="Read the entry and server guide")
    async def gate_guide(self,i:discord.Interaction):
        cfg,_=await self.bot.db.config(i.guild_id)
        await gu.reply(i,embed=gu.embed(cfg,"Rip Cars guide","Start in Verification. Pass the CAPTCHA and answer at least one question to get the member role. Choose optional roles in Notifications. OG is assigned by an admin. Holder verification and the support bot will be connected later.\nApp: "+cfg["website"]))
    async def panel(self,i):
        cfg,_=await self.bot.db.config(i.guild_id)
        await gu.reply(i,embed=gu.embed(cfg,"Setup center","Choose a section below. Changes stay separate from companion bots. Member entry is "+("active." if cfg["enabled"] else "paused.")),view=Hub(self,i.user.id))
    async def section(self,i,key):
        cfg,_=await self.bot.db.config(i.guild_id)
        if key=="health":await self.show_health(i);return
        detail=SECTIONS[key][1]
        if key=="help":detail="1. Server setup → Preview → Apply.\n2. Check bot role order and Health.\n3. Publish panels.\n4. Entry & CAPTCHA → Activate.\n5. Test with a regular account.\n\nResources changed outside Gate are protected. Bind existing objects by ID. For a protected resource, Keep current accepts the current managed fields; Restore template explicitly applies the configured template. Unknown channels and bots are not changed."
        if key=="integrations":detail+="\nNo integration is active by default. Register by bot ID, then activate a reviewed access plan."
        await gu.reply(i,embed=gu.embed(cfg,SECTIONS[key][0],detail),view=SectionView(self,i.user.id,key))
    async def action(self,i,action):
        if not await gu.require(self.bot,i):return
        cfg,revision=await self.bot.db.config(i.guild_id)
        async def editor(title,fields,save):await i.response.send_modal(Editor(self,i.user.id,cfg,revision,title,fields,save))
        async def choose(options,fn):await gu.reply(i,"Choose an item.",view=Choice(self,i.user.id,options,fn))
        if action=="preview":
            await i.response.defer(ephemeral=True)
            lines=await self.bot.provisioner.plan(i.guild)
            async def apply(j):
                results=await self.bot.provisioner.apply(j.guild,j.user.id)
                await gu.reply(j,"Setup finished. Review the attached result before activating entry.",file=discord.File(io.BytesIO("\n".join(results).encode()),filename="setup-result.txt"))
            await gu.reply(i,"Preview: roles and per-channel access will be created or updated. Existing manual changes and unknown resources stay protected.",file=discord.File(io.BytesIO("\n".join(lines).encode()),filename="setup-preview.txt"),view=Confirm(self,i.user.id,apply,"Apply setup"))
        elif action=="publish":
            await i.response.defer(ephemeral=True);await self.publish(i.guild)
            await gu.reply(i,"Public messages and persistent buttons have been refreshed.")
        elif action=="toggle":
            if not cfg["enabled"]:
                blockers=await self.blockers(i.guild)
                if blockers:await gu.reply(i,"Activation blockers:\n"+"\n".join(blockers));return
            cfg["enabled"]=not cfg["enabled"];await self.bot.db.save_config(i.guild_id,cfg,revision,i.user.id)
            await gu.reply(i,"Entry is "+("active." if cfg["enabled"] else "paused."))
        elif action=="captcha":
            fields=[("captcha_length","Code length: 4 to 8",cfg["captcha_length"],2),("captcha_ttl","Image expiry in seconds",cfg["captcha_ttl"],4),("max_attempts","Maximum incorrect attempts",cfg["max_attempts"],2),("lock_seconds","Lock duration in seconds",cfg["lock_seconds"],4),("answer_ttl","Time to finish questions in seconds",cfg["answer_ttl"],4)]
            await editor("CAPTCHA settings",fields,lambda c,v:c.update({k:int(x) for k,x in v.items()}))
        elif action=="brand":
            def save(c,v):c.update(brand=v["brand"],website=v["website"],color=int(v["color"].lstrip("#"),16))
            await editor("Brand settings",[("brand","Bot display branding",cfg["brand"],80),("website","Official app URL",cfg["website"],200),("color","Hex color",f"{cfg['color']:06X}",7)],save)
        elif action in ("text","question","roles","channel","category"):
            if action=="text":keys=list(cfg["texts"])
            elif action=="question":keys=[q["id"] for q in cfg["questions"]]
            elif action=="roles":keys=list(cfg["role_names"])
            else:keys=[k for k,s in cfg["blueprint"].items() if (s["kind"]=="category")== (action=="category")]
            async def edit(j,k):await self.edit_item(j,action,k)
            await choose([discord.SelectOption(label=k.replace("_"," ").title(),value=k) for k in keys],edit)
        elif action=="add_question":
            def save(c,v):c["questions"].append(dict(id=v["id"],label=v["label"],prompt=v["prompt"],enabled=True))
            await editor("Add question",[("id","Unique ID: lowercase / underscore","new_question",30),("label","Question label","Your question",45),("prompt","Full question","Your question",100)],save)
        elif action=="bind":
            await i.response.send_modal(BindModal(self,i.user.id))
        elif action=="review":
            res=await self.bot.db.resources(i.guild_id)
            keys=[k for k,r in res.items() if r['owner']==core.OWNER and r["state"]!="active"]
            if not keys:await gu.reply(i,"No protected or missing resources need review.");return
            await choose([discord.SelectOption(label=k[:100],value=k) for k in keys[:25]],self.review)
        elif action=="integration":await i.response.send_modal(IntegrationModal(self,i.user.id))
        elif action=="integration_review":
            rows=await self.bot.db.query("SELECT * FROM integrations WHERE guild=?",(i.guild_id,))
            if not rows:await gu.reply(i,"No companion bots are registered. Gate works independently.");return
            await choose([discord.SelectOption(label=f"{r['bot']} · {r['scope']} · {'active' if r['active'] else 'inactive'}"[:100],value=str(r["bot"])) for r in rows[:25]],self.integration_review)
        elif action=="health":await self.show_health(i)
        elif action=="backup":
            await i.response.defer(ephemeral=True)
            path=await asyncio.to_thread(health.run_backup,self.bot.db.path)
            if self.bot.db.coordination:await asyncio.to_thread(health.run_backup,self.bot.db.coordination.path)
            await gu.reply(i,"Backup created: "+(path.name if path else "database not found"))
        elif action=="scan":
            await i.response.defer(ephemeral=True);changes=await self.bot.provisioner.scan(i.guild)
            await gu.reply(i,"Permission scan:\n"+("\n".join(changes) or "Managed resources match their recorded baseline."))
        elif action=="export":
            rows=await self.bot.db.query("SELECT user,answers,updated FROM profiles WHERE guild=?",(i.guild_id,))
            out=io.StringIO();w=csv.writer(out);w.writerow(["user_id","answers_json","updated_unix"])
            for row in rows:w.writerow([row["user"],row["answers"],row["updated"]])
            await gu.reply(i,file=discord.File(io.BytesIO(out.getvalue().encode("utf-8-sig")),filename="ripcars-member-answers.csv"))
        elif action=="history":
            rows=await self.bot.db.query("SELECT id,actor,at FROM history WHERE guild=? ORDER BY id DESC LIMIT 25",(i.guild_id,))
            if not rows:await gu.reply(i,"No earlier settings yet.");return
            await choose([discord.SelectOption(label=f"Revision snapshot {r['id']} · admin {r['actor']}",value=str(r["id"])) for r in rows],self.restore_history)
    async def edit_item(self,i,kind,key):
        cfg,revision=await self.bot.db.config(i.guild_id)
        if kind=="text":fields=[("value","Message text",cfg["texts"][key],3500)];save=lambda c,v:c["texts"].update({key:v["value"]})
        elif kind=="question":
            q=next(q for q in cfg["questions"] if q["id"]==key)
            fields=[("label","Question label",q["label"],45),("prompt","Full question",q["prompt"],100),("enabled","Enabled: yes / no","yes" if q["enabled"] else "no",3)]
            def save(c,v):next(q for q in c["questions"] if q["id"]==key).update(label=v["label"],prompt=v["prompt"],enabled=yesno(v["enabled"]))
        elif kind=="roles":
            fields=[("name","Role display name",cfg["role_names"][key],80)]
            def save(c,v):
                c["role_names"][key]=v["name"]
                if key.startswith("claim_"):c["claims"][key[6:]]=v["name"]
        else:
            s=cfg["blueprint"][key]
            fields=[("name","Name",s["name"],100),("topic","Topic: use - for empty",s["topic"] or "-",1000),("kind","Type: text / forum / category",s["kind"],8),("access","Access: public / member / og / staff",s["access"],6),("policy","Mode, seconds, links yes/no, images yes/no",f"{s['mode']},{s['slowmode']},{'yes' if s['links'] else 'no'},{'yes' if s['images'] else 'no'}",60)]
            def save(c,v):
                mode,seconds,links,images=[x.strip() for x in v["policy"].split(",")]
                if key=="gcars" and (mode!="submit" or v["kind"]!="text"):raise ValueError("gCARS uses text submissions to enforce its daily cooldown.")
                if (s["kind"]=="category") != (v["kind"]=="category"):raise ValueError("A category cannot be converted to a chat.")
                c["blueprint"][key].update(name=v["name"],topic="" if v["topic"]=="-" else v["topic"],kind=v["kind"],access=v["access"],mode=mode,slowmode=int(seconds),links=yesno(links),images=yesno(images))
        await i.response.send_modal(Editor(self,i.user.id,cfg,revision,"Edit "+key.replace("_"," "),fields,save))
    async def blockers(self,guild):
        rows=await self.bot.db.resources(guild.id);issues=[]
        cfg,_=await self.bot.db.config(guild.id)
        for key in core.ROLE_SPECS:
            r=rows.get("role:"+key)
            if not r or not guild.get_role(r["object_id"]):issues.append(key+": role is missing")
        for key in cfg["blueprint"]:
            r=rows.get("channel:"+key)
            if not r:issues.append(key+": not built yet")
        for key in ("role:rippers","channel:verification","channel:gcars"):
            r=rows.get(key)
            if not r or r["state"] not in ("active","pinned"):issues.append(key+": missing or protected")
        role=await gu.resource(self.bot,guild,"rippers",True)
        if role and (role.permissions.value or role.managed or role>=guild.me.top_role):issues.append("Rippers must have no server-wide permissions and sit below the bot role.")
        for key,r in rows.items():
            if r["owner"]==core.OWNER and r["state"] not in ("active","pinned"):issues.append(key+": "+r["state"])
        if not self.bot.intents.message_content:issues.append("Message Content intent is required for channel link/image filters.")
        for key,r in rows.items():
            if not key.startswith("channel:") or r["kind"]=="category":continue
            ch=guild.get_channel(r["object_id"])
            if not ch:issues.append(key+": deleted");continue
            p=ch.permissions_for(guild.me)
            if not all((p.view_channel,p.read_message_history,p.send_messages,p.embed_links,p.attach_files,p.manage_messages)):
                issues.append(key+": bot needs View Channel, Read History, Send, Embed, Attach, and Manage Messages")
        panels=await self.bot.db.query("SELECT key FROM panels WHERE guild=?",(guild.id,))
        published={r["key"] for r in panels}
        for key in ("verification","notifications","gcars"):
            if key not in published:issues.append(key+": publish its panel first")
        return list(dict.fromkeys(issues))
    async def publish(self,guild):
        cfg,_=await self.bot.db.config(guild.id)
        mapping={"verification":("welcome_title","welcome",VerificationView(self.bot.get_cog("Onboarding"))),"notifications":(None,"notifications",ClaimsView(self.bot,cfg)),"gcars":(None,"gcars",GcarsView(self.bot))}
        keys=["rules","faq","official_links","announcements","twitter_posts","community_news","proposals","ticket",*mapping]
        for key in keys:
            ch=await gu.resource(self.bot,guild,key)
            if not ch or not isinstance(ch,discord.TextChannel):continue
            r=(await self.bot.db.resources(guild.id))["channel:"+key]
            if r["owner"]!=core.OWNER or r["state"]!="active":continue
            titlekey,textkey,view=mapping.get(key,(None,key,None))
            e=gu.embed(cfg,cfg["texts"][titlekey] if titlekey else cfg["blueprint"][key]["name"].replace("-"," ").title(),cfg["texts"][textkey])
            rows=await self.bot.db.query("SELECT * FROM panels WHERE guild=? AND key=?",(guild.id,key))
            msg=None
            if rows and rows[0]["channel"]==ch.id:
                try:msg=await ch.fetch_message(rows[0]["message"])
                except discord.NotFound:pass
            if msg:await msg.edit(embed=e,view=view,allowed_mentions=discord.AllowedMentions.none())
            else:
                msg=await ch.send(embed=e,view=view,allowed_mentions=discord.AllowedMentions.none())
                await self.bot.db.execute("INSERT INTO panels VALUES(?,?,?,?) ON CONFLICT(guild,key) DO UPDATE SET channel=excluded.channel,message=excluded.message",(guild.id,key,ch.id,msg.id))
    async def show_health(self,i):
        await i.response.defer(ephemeral=True)
        cfg,_=await self.bot.db.config(i.guild_id);snap=await health.snapshot(self.bot,i.guild_id)
        issues=await self.blockers(i.guild)
        details=f"Version: {core.VERSION}\nUptime: {health.format_uptime(snap['uptime'])}\nGateway: {snap['latency_ms']} ms\nDatabase: {'OK' if snap['db_ok'] else 'FAILED'}\nBackups: {snap['backups']}\nLatest backup: {snap['last_backup']}\nEntry: {'active' if cfg['enabled'] else 'paused'}\nMembers: {snap['verification']}\nWatchdog: {'on' if snap['watchdog'] else 'off'}\n\nBlockers:\n"+("\n".join(issues) or "None")
        errors=await self.bot.db.query("SELECT details FROM audit WHERE guild=? AND area='error' ORDER BY id DESC LIMIT 5",(i.guild_id,))
        details+="\n\nRecent errors:\n"+("\n".join(r["details"] for r in errors) or "None")
        await gu.reply(i,embed=gu.embed(cfg,"Health & troubleshooting",details),view=SectionView(self,i.user.id,"health") if await gu.authorized(self.bot,i) else None)
    async def review(self,i,key):
        rows=await self.bot.db.resources(i.guild_id);r=rows[key]
        if r['owner']!=core.OWNER:raise ValueError('Use the owning bot to review this resource. Gate did not change it.')
        obj=i.guild.get_role(r["object_id"]) if key.startswith("role:") else i.guild.get_channel(r["object_id"])
        if not obj:await gu.reply(i,"This resource was deleted. Use Bind an existing ID to choose a replacement.");return
        current=role_snapshot(obj) if key.startswith("role:") else channel_snapshot(obj,r["baseline"])
        async def keep(j):
            async with self.bot.db.coordinated(j.guild_id):
                fresh=(await self.bot.db.resources(j.guild_id)).get(key)
                if not fresh or fresh['owner']!=core.OWNER or fresh['object_id']!=r['object_id']:raise ValueError('Resource ownership or binding changed. Reopen review.')
                await self.bot.db.baseline(j.guild_id,key,current)
                await self.bot.db.state(j.guild_id,key,"pinned")
            await gu.reply(j,"Current settings kept. Automatic changes stay disabled for this resource.")
        async def restore(j):
            async with self.bot.db.coordinated(j.guild_id):
                fresh=(await self.bot.db.resources(j.guild_id)).get(key)
                if not fresh or fresh['owner']!=core.OWNER or fresh['object_id']!=r['object_id']:raise ValueError('Resource ownership or binding changed. Reopen review.')
                await self.bot.db.baseline(j.guild_id,key,current)
            result=await self.bot.provisioner.apply(j.guild,j.user.id)
            await gu.reply(j,"Template application result:",file=discord.File(io.BytesIO("\n".join(result).encode()),filename="repair-result.txt"))
        view=AdminView(self,i.user.id)
        for label,fn in [("Keep current",keep),("Restore template",restore)]:
            b=discord.ui.Button(label=label)
            async def click(j,f=fn):await gu.reply(j,"Review the resource change, then apply.",view=Confirm(self,j.user.id,f))
            b.callback=click;view.add_item(b)
        await gu.reply(i,f"{key}\nState: {r['state']}\nCurrent managed fields:",file=discord.File(io.BytesIO(json.dumps(current,indent=2).encode()),filename="resource-current.json"),view=view)
    async def restore_history(self,i,version):
        rows=await self.bot.db.query("SELECT body FROM history WHERE guild=? AND id=?",(i.guild_id,int(version)))
        cfg=json.loads(rows[0]["body"]);cfg["enabled"]=False
        _,rev=await self.bot.db.config(i.guild_id)
        async def restore(j):
            await self.bot.db.save_config(j.guild_id,cfg,rev,j.user.id)
            await gu.reply(j,"Settings restored with entry paused. Preview setup, publish panels, and check Health before activating.")
        await gu.reply(i,"Restore this settings snapshot? This does not delete channels or restore member data.",file=discord.File(io.BytesIO(json.dumps(cfg,indent=2).encode()),filename="settings-preview.json"),view=Confirm(self,i.user.id,restore,"Restore settings"))
    async def integration_review(self,i,botid):
        rows=await self.bot.db.query("SELECT * FROM integrations WHERE guild=? AND bot=?",(i.guild_id,int(botid)));r=rows[0]
        async def apply(j):
            member=j.guild.get_member(int(botid))
            if not member or not member.bot:raise ValueError("The registered bot is not in this server.")
            keys=("ticket","open_tickets","closed_tickets","gate_log") if r["scope"]=="support" else ("holder",)
            async with self.bot.db.coordinated(j.guild_id) as token:
                fresh=await self.bot.db.query('SELECT scope FROM integrations WHERE guild=? AND bot=?',(j.guild_id,int(botid)))
                if not fresh or fresh[0]['scope']!=r['scope']:raise ValueError('Integration scope changed. Reopen review.')
                resources=await self.bot.db.resources(j.guild_id)
                for key in keys:
                    row=resources.get('channel:'+key)
                    if not row or row['owner'] not in (core.OWNER,'bot:'+botid) or row['state'] not in ('active','pinned','external'):raise ValueError('Channel ownership needs review: '+key)
                    ch=await gu.resource(self.bot,j.guild,key)
                    if not ch:raise ValueError(f"Missing channel: {key}")
                    ow=ch.overwrites_for(member)
                    ow.update(view_channel=True,read_message_history=True,send_messages=True,embed_links=True,attach_files=True)
                    await self.bot.db.renew(j.guild_id,'server-setup',token)
                    await ch.set_permissions(member,overwrite=ow,reason="Ripcars Gate: admin-approved companion access")
                await self.bot.db.execute("UPDATE integrations SET active=1 WHERE guild=? AND bot=?",(j.guild_id,int(botid)))
            await self.bot.db.log(j.guild_id,j.user.id,"integration_activated",botid)
            await gu.reply(j,"Companion channel access applied. Its base permissions remain under admin control. Resource ownership has not been transferred.")
        view=AdminView(self,i.user.id)
        button=discord.ui.Button(label="Review channel access")
        async def access(j):await gu.reply(j,"Apply the registered companion's channel access?",view=Confirm(self,j.user.id,apply,"Activate access"))
        button.callback=access;view.add_item(button)
        hand=discord.ui.Button(label="Transfer resource responsibility")
        async def transfer(j):
            fresh=await self.bot.db.query("SELECT active FROM integrations WHERE guild=? AND bot=?",(j.guild_id,int(botid)))
            if not fresh or not fresh[0]["active"]:raise ValueError("Activate channel access before transferring responsibility.")
            keys=("channel:ticket","channel:open_tickets","channel:closed_tickets") if r["scope"]=="support" else ("channel:holder",)
            async def commit(k):
                await self.bot.db.handoff(k.guild_id,keys,int(botid))
                await self.bot.db.log(k.guild_id,k.user.id,"handoff",f"bot={botid}; keys={keys}")
                await gu.reply(k,"Responsibility transferred. Gate no longer updates those resources. Configure the companion bot to use the registered IDs.")
            await gu.reply(j,"Transfer these resources?\n"+"\n".join(keys),view=Confirm(self,j.user.id,commit,"Transfer responsibility"))
        hand.callback=transfer;view.add_item(hand)
        await gu.reply(i,f"Bot ID: {botid}\nScope: {r['scope']}\nActivation grants channel access only. Base permissions and role order stay under admin control.",view=view)

def yesno(value):
    if value.lower() not in ("yes","no"):raise ValueError("Use yes or no.")
    return value.lower()=="yes"

class BindModal(gu.SafeModal):
    def __init__(self,cog,user):
        super().__init__(cog.bot,title="Bind an existing resource");self.cog=cog;self.user=user
        self.key=discord.ui.TextInput(label="Resource key: channel:general or role:rippers",max_length=60)
        self.oid=discord.ui.TextInput(label="Existing channel or role ID",max_length=25)
        self.add_item(self.key);self.add_item(self.oid)
    async def on_submit(self,i):
        if i.user.id!=self.user or not await gu.require(self.bot,i):return
        key=self.key.value.strip();oid=int(self.oid.value)
        cfg,_=await self.bot.db.config(i.guild_id)
        if key.startswith("role:") and key[5:] in core.ROLE_SPECS:
            obj=i.guild.get_role(oid)
            if not obj or obj.managed or obj==i.guild.default_role or obj>=i.guild.me.top_role:raise ValueError("Choose an ordinary role below the bot role.")
            snap=role_snapshot(obj);kind="role"
        elif key.startswith("channel:") and key[8:] in cfg["blueprint"]:
            obj=i.guild.get_channel(oid)
            if not obj:raise ValueError("This channel is not in this server.")
            kind=cfg["blueprint"][key[8:]]["kind"]
            if str(obj.type)!={"text":"text","forum":"forum","category":"category"}[kind]:raise ValueError("Existing channel type does not match the template.")
            snap=channel_snapshot(obj,{"name":"","kind":"","parent":None,"topic":"","slowmode":0,"overwrites":{}}) if kind!="category" else channel_snapshot(obj,{"name":"","kind":"","overwrites":{}})
        else:raise ValueError("Unknown resource key. See the blueprint in the package.")
        async def apply(j):
            async with self.bot.db.coordinated(j.guild_id):
                await self.bot.db.register(j.guild_id,key,oid,kind,snap)
            await self.bot.db.log(j.guild_id,j.user.id,"bind_resource",f"{key}={oid}")
            await gu.reply(j,"ID bound. Preview setup before applying template permissions.")
        await gu.reply(i,f"Bind {key} to {obj.name} ({oid})? A later Apply setup will apply the template's managed permissions.",view=Confirm(self.cog,i.user.id,apply,"Bind ID"))

class IntegrationModal(gu.SafeModal):
    def __init__(self,cog,user):
        super().__init__(cog.bot,title="Register a future bot");self.cog=cog;self.user=user
        self.oid=discord.ui.TextInput(label="Bot user ID",max_length=25)
        self.scope=discord.ui.TextInput(label="Scope: support or holder",max_length=10)
        self.add_item(self.oid);self.add_item(self.scope)
    async def on_submit(self,i):
        if i.user.id!=self.user or not await gu.require(self.bot,i):return
        scope=self.scope.value.strip().lower();oid=int(self.oid.value)
        if scope not in ("support","holder"):raise ValueError("Use support or holder.")
        if oid==self.bot.user.id:raise ValueError("Use a companion bot ID.")
        if await self.bot.db.query("SELECT bot FROM integrations WHERE guild=? AND bot=?",(i.guild_id,oid)):
            raise ValueError("This bot is already registered. Open Review / activate to inspect it.")
        await self.bot.db.execute("INSERT INTO integrations(guild,bot,scope) VALUES(?,?,?)",(i.guild_id,oid,scope))
        await gu.reply(i,"Registered as inactive. No permissions were changed.")

async def setup(bot):await bot.add_cog(Admin(bot))
