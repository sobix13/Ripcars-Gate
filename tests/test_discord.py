"""Real discord.py objects with mocked HTTP boundaries. No token or live server."""
import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock,MagicMock,patch
from functools import total_ordering
from collections import defaultdict
import asyncio
AVAILABLE=importlib.util.find_spec('discord') is not None
if AVAILABLE:
    import discord
    import core
    from db import Database
    from server import Provisioner
    from cogs.onboarding import Onboarding,VerificationView,Questions,CodeModal,AnswerModal
    from cogs.community import ClaimsView,GcarsView,PostModal,Community
    from cogs.admin import Hub,SectionView,Admin,SECTIONS

@total_ordering
class Role:
    def __init__(self,guild,rid,name,colour=0,permissions=0,position=0):
        self.guild=guild;self.id=rid;self.name=name;self.colour=discord.Colour(colour);self.permissions=discord.Permissions(permissions);self.position=position;self.managed=False
    def __eq__(self,other):return isinstance(other,Role) and self.id==other.id
    def __lt__(self,other):return self.position<other.position
    def __hash__(self):return hash(self.id)
    async def edit(self,**kw):
        for k in ('name','colour','permissions'):
            if k in kw:setattr(self,k,kw[k])
        return self

class Channel:
    def __init__(self,guild,cid,name,kind,**kw):
        self.guild=guild;self.id=cid;self.name=name;self.type=kind;self.category_id=getattr(kw.get('category'),'id',None)
        self.topic=kw.get('topic','');self.slowmode_delay=kw.get('slowmode_delay',0)
        # Deep-copy only overwrite values; target identities must match the guild registry.
        self.ows={target:copy.copy(ow) for target,ow in kw.get('overwrites',{}).items()}
        self.deleted=False
    def overwrites_for(self,target):return copy.copy(self.ows.get(target,discord.PermissionOverwrite()))
    async def edit(self,**kw):
        self.name=kw.get('name',self.name);self.topic=kw.get('topic',self.topic);self.slowmode_delay=kw.get('slowmode_delay',self.slowmode_delay)
        if 'category' in kw:self.category_id=getattr(kw['category'],'id',None)
        return self
    async def set_permissions(self,target,overwrite,**kw):self.ows[target]=copy.copy(overwrite)

class Guild:
    def __init__(self):
        self.id=1;self.owner_id=1;self.features=[];self.roles=[];self.channels=[];self.members=[];self.nextid=100
        self.default_role=Role(self,1,'@everyone');self.roles.append(self.default_role)
        top=Role(self,2,'Ripcars Gate',permissions=discord.Permissions(administrator=True).value,position=100);self.roles.append(top)
        self.me=SimpleNamespace(id=3,top_role=top)
        # Permission overwrite keys need a hashable member.
        self.me=Member(self,3);self.me.top_role=top;self.me.bot=True
        self.members.append(self.me)
    def get_role(self,rid):return next((r for r in self.roles if r.id==rid),None)
    def get_member(self,uid):return next((m for m in self.members if m.id==uid),None)
    def get_channel(self,cid):return next((c for c in self.channels if c.id==cid),None)
    async def create_role(self,**kw):
        self.nextid+=1;r=Role(self,self.nextid,kw['name'],kw['colour'].value,kw['permissions'].value,len(self.roles));self.roles.append(r);return r
    async def edit_role_positions(self,positions,**kw):
        for r,p in positions.items():r.position=p
    async def channel(self,kind,**kw):
        self.nextid+=1;c=Channel(self,self.nextid,kw.pop('name'),kind,**kw);self.channels.append(c);return c
    async def create_category(self,**kw):return await self.channel(discord.ChannelType.category,**kw)
    async def create_text_channel(self,**kw):return await self.channel(discord.ChannelType.text,**kw)
    async def create_forum(self,**kw):return await self.channel(discord.ChannelType.forum,**kw)

class Member:
    def __init__(self,guild,uid=42):
        self.guild=guild;self.id=uid;self.roles=[];self.bot=False;self.display_name='member'
        self.guild_permissions=discord.Permissions.none();self.added=0
    async def add_roles(self,role,**kw):
        self.added+=1
        if role not in self.roles:self.roles.append(role)
    async def remove_roles(self,role,**kw):self.roles.remove(role)

def interaction(guild,user):
    response=SimpleNamespace(is_done=lambda:False,send_message=AsyncMock(),send_modal=AsyncMock(),defer=AsyncMock(),edit_message=AsyncMock())
    async def defer(**kw):response.is_done=lambda:True
    response.defer.side_effect=defer
    return SimpleNamespace(guild=guild,guild_id=guild.id,user=user,response=response,followup=SimpleNamespace(send=AsyncMock()))

@unittest.skipUnless(AVAILABLE,'discord.py dependency unavailable in this execution environment')
class Discord(unittest.IsolatedAsyncioTestCase):
    async def test_companion_already_deleted_message_is_not_an_error(self):
        await self.bot.provisioner.apply(self.guild,1)
        rows=await self.db.resources(1)
        channel=self.guild.get_channel(rows['channel:show_off']['object_id'])
        user=Member(self.guild);user.send=AsyncMock()
        msg=SimpleNamespace(guild=self.guild,author=user,channel=channel,content='https://example.com',attachments=[],delete=AsyncMock(side_effect=discord.NotFound(SimpleNamespace(status=404,reason='Not Found'),'Unknown Message')))
        await Community(self.bot).on_message(msg)
        user.send.assert_not_awaited()

    async def test_companion_patch_does_not_hide_missing_permission_errors(self):
        await self.bot.provisioner.apply(self.guild,1)
        rows=await self.db.resources(1)
        channel=self.guild.get_channel(rows['channel:show_off']['object_id'])
        user=Member(self.guild);user.send=AsyncMock()
        msg=SimpleNamespace(guild=self.guild,author=user,channel=channel,content='https://example.com',attachments=[],delete=AsyncMock(side_effect=discord.Forbidden(SimpleNamespace(status=403,reason='Forbidden'),'Missing Permissions')))
        with self.assertRaises(discord.Forbidden):await Community(self.bot).on_message(msg)

    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Database(Path(self.tmp.name)/'gate.db');await self.db.connect()
        self.bot=SimpleNamespace(db=self.db,intents=SimpleNamespace(message_content=True),member_locks=defaultdict(asyncio.Lock),get_cog=lambda k:None)
        self.guild=Guild();self.bot.provisioner=Provisioner(self.bot)
    async def asyncTearDown(self):await self.db.close();self.tmp.cleanup()
    async def test_setup_is_repeatable_and_preserves_unknown_resources(self):
        unknown=await self.guild.create_text_channel(name='external-chat',overwrites={})
        first=await self.bot.provisioner.apply(self.guild,1);counts=(len(self.guild.roles),len(self.guild.channels))
        await self.bot.provisioner.apply(self.guild,1)
        self.assertEqual(counts,(len(self.guild.roles),len(self.guild.channels)));self.assertEqual(unknown.ows,{})
        self.assertFalse(any(x.startswith(('FAILED','BLOCKED')) for x in first),first)
    async def test_manual_permission_change_is_not_reverted(self):
        await self.bot.provisioner.apply(self.guild,1);rows=await self.db.resources(1)
        ch=self.guild.get_channel(rows['channel:general']['object_id']);role=self.guild.get_role(rows['role:rippers']['object_id'])
        ow=ch.overwrites_for(role);ow.send_messages=False;await ch.set_permissions(role,overwrite=ow)
        await self.bot.provisioner.apply(self.guild,1)
        self.assertFalse(ch.overwrites_for(role).send_messages)
        self.assertEqual((await self.db.resources(1))['channel:general']['state'],'manual')
    async def test_external_bot_overwrite_survives_a_template_update(self):
        await self.bot.provisioner.apply(self.guild,1);rows=await self.db.resources(1)
        ch=self.guild.get_channel(rows['channel:general']['object_id']);external=Member(self.guild,900);self.guild.members.append(external)
        await ch.set_permissions(external,overwrite=discord.PermissionOverwrite(view_channel=True,send_messages=True))
        cfg,rev=await self.db.config(1);cfg['blueprint']['general']['slowmode']=30;await self.db.save_config(1,cfg,rev,1)
        await self.bot.provisioner.apply(self.guild,1)
        self.assertTrue(ch.overwrites_for(external).send_messages);self.assertEqual(ch.slowmode_delay,30)
    async def test_same_name_needs_explicit_id_binding(self):
        existing=await self.guild.create_text_channel(name='general',overwrites={})
        result=await self.bot.provisioner.apply(self.guild,1)
        self.assertTrue(any(x.startswith('CONFLICT general') for x in result));self.assertEqual(existing.ows,{})
        self.assertEqual(sum(c.name=='general' for c in self.guild.channels),1)
    async def test_deleting_a_managed_channel_does_not_recreate_it_automatically(self):
        await self.bot.provisioner.apply(self.guild,1);rows=await self.db.resources(1)
        cid=rows['channel:general']['object_id'];self.guild.channels=[c for c in self.guild.channels if c.id!=cid]
        count=len(self.guild.channels);await self.bot.provisioner.apply(self.guild,1,automatic=True)
        self.assertEqual(len(self.guild.channels),count);self.assertEqual((await self.db.resources(1))['channel:general']['state'],'missing')
    async def test_role_is_granted_only_after_captcha_and_answer(self):
        await self.bot.provisioner.apply(self.guild,1)
        cfg,rev=await self.db.config(1);cfg['enabled']=True;await self.db.save_config(1,cfg,rev,1)
        from captcha import create
        ch=create();token=await self.db.challenge(1,42,ch,300);await self.db.check_captcha(1,42,token,ch.answer,cfg)
        user=Member(self.guild);cog=Onboarding(self.bot)
        with self.assertRaises(ValueError):await cog.finish(interaction(self.guild,user))
        self.assertEqual(user.added,0)
        await self.db.answer(1,42,'dream','F40',cfg)
        await cog.finish(interaction(self.guild,user));self.assertEqual(user.added,1)
        self.assertEqual((await self.db.session(1,42))['verified'],1)
    async def test_every_panel_serializes_within_discord_limits(self):
        cog=Admin(self.bot);cfg=core.defaults();onboarding=Onboarding(self.bot)
        views=[Hub(cog,1),VerificationView(onboarding),ClaimsView(self.bot),GcarsView(self.bot),Questions(onboarding,42,cfg)]
        views.extend(SectionView(cog,1,key) for key in SECTIONS)
        for view in views:
            components=view.to_components();self.assertLessEqual(len(components),5)
            for row in components:
                for comp in row['components']:
                    if 'options' in comp:self.assertLessEqual(len(comp['options']),25)
                    if 'label' in comp:self.assertLessEqual(len(comp['label']),80)
        self.assertTrue(VerificationView(onboarding).is_persistent());self.assertTrue(ClaimsView(self.bot).is_persistent())
    async def ready_server(self):
        await self.bot.provisioner.apply(self.guild,1)
        self.onboarding=Onboarding(self.bot)
        self.bot.get_cog=lambda k:self.onboarding if k=='Onboarding' else None
        for ch in list(self.guild.channels):
            if ch.type!=discord.ChannelType.text:continue
            obj=MagicMock(spec=discord.TextChannel)
            for name in ('id','guild','name','type','category_id','topic','slowmode_delay'):setattr(obj,name,getattr(ch,name))
            obj.overwrites_for=ch.overwrites_for
            obj.set_permissions=ch.set_permissions
            obj.edit=ch.edit
            obj.permissions_for=MagicMock(return_value=discord.Permissions(view_channel=True,read_message_history=True,send_messages=True,embed_links=True,attach_files=True,manage_messages=True))
            obj.send=AsyncMock(return_value=SimpleNamespace(id=ch.id+10000))
            obj.fetch_message=AsyncMock(return_value=SimpleNamespace(edit=AsyncMock()))
            self.guild.channels[self.guild.channels.index(ch)]=obj
        return Admin(self.bot)
    async def test_full_admin_and_member_onboarding_session(self):
        admin=await self.ready_server();owner=Member(self.guild,1)
        await admin.publish(self.guild)
        self.assertEqual(await admin.blockers(self.guild),[])
        await admin.action(interaction(self.guild,owner),'toggle')
        self.assertTrue((await self.db.config(1))[0]['enabled'])
        from captcha import create
        challenge=create();user=Member(self.guild)
        with patch('cogs.onboarding.captcha.create',return_value=challenge):
            start=interaction(self.guild,user);await self.onboarding.start(start)
        panel=start.followup.send.await_args.kwargs
        self.assertTrue(panel['ephemeral']);self.assertIn('file',panel)
        token=(await self.db.session(1,42))['challenge']
        modal=CodeModal(self.onboarding,42,token);modal.code._value=challenge.answer
        await modal.on_submit(interaction(self.guild,user))
        self.assertEqual(user.roles,[])
        cfg,_=await self.db.config(1)
        answer=AnswerModal(self.onboarding,42,cfg['questions'][0]);answer.answer._value='Yes'
        await answer.on_submit(interaction(self.guild,user))
        await self.onboarding.finish(interaction(self.guild,user))
        self.assertEqual(len(user.roles),1);self.assertEqual(user.roles[0].permissions.value,0)
        self.assertEqual(len((await self.db.session(1,42))['answers']),1)
    async def test_all_claim_buttons_add_then_remove_and_reject_unverified_user(self):
        await self.ready_server();rows=await self.db.resources(1);user=Member(self.guild)
        view=ClaimsView(self.bot)
        await view.children[0].callback(interaction(self.guild,user));self.assertEqual(user.roles,[])
        member_role=self.guild.get_role(rows['role:rippers']['object_id']);user.roles.append(member_role)
        for button in view.children:
            await button.callback(interaction(self.guild,user));self.assertEqual(len(user.roles),2)
            self.assertEqual(user.roles[-1].permissions.value,0)
            await button.callback(interaction(self.guild,user));self.assertEqual(user.roles,[member_role])
    async def test_gcars_modal_enforces_daily_limit_and_rejects_link(self):
        await self.ready_server();rows=await self.db.resources(1);user=Member(self.guild)
        user.roles.append(self.guild.get_role(rows['role:rippers']['object_id']))
        invalid=PostModal(self.bot);invalid.text._value='https://test.io'
        with self.assertRaises(ValueError):await invalid.on_submit(interaction(self.guild,user))
        modal=PostModal(self.bot);modal.text._value='My dream car is an F40'
        await modal.on_submit(interaction(self.guild,user))
        with self.assertRaises(ValueError):await modal.on_submit(interaction(self.guild,user))
        ch=self.guild.get_channel(rows['channel:gcars']['object_id']);self.assertEqual(ch.send.await_count,1)
    async def test_failed_gcars_publish_does_not_consume_the_day(self):
        await self.ready_server();rows=await self.db.resources(1);user=Member(self.guild)
        user.roles.append(self.guild.get_role(rows['role:rippers']['object_id']))
        ch=self.guild.get_channel(rows['channel:gcars']['object_id']);ch.send.side_effect=RuntimeError('simulated transport failure')
        modal=PostModal(self.bot);modal.text._value='F40'
        with self.assertRaises(RuntimeError):await modal.on_submit(interaction(self.guild,user))
        ch.send.side_effect=None
        await modal.on_submit(interaction(self.guild,user));self.assertEqual(ch.send.await_count,2)
    async def test_public_panel_republish_edits_recorded_messages(self):
        admin=await self.ready_server();await admin.publish(self.guild)
        sends=sum(ch.send.await_count for ch in self.guild.channels if hasattr(ch,'send'))
        await admin.publish(self.guild)
        self.assertEqual(sum(ch.send.await_count for ch in self.guild.channels if hasattr(ch,'send')),sends)
        self.assertTrue(any(ch.fetch_message.await_count for ch in self.guild.channels if hasattr(ch,'fetch_message')))
    async def test_regular_member_cannot_activate_entry(self):
        admin=await self.ready_server();i=interaction(self.guild,Member(self.guild))
        await admin.action(i,'toggle')
        self.assertFalse((await self.db.config(1))[0]['enabled']);i.response.send_message.assert_awaited_once()

if __name__=='__main__':unittest.main()
