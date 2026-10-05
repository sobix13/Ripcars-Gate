import asyncio
import tempfile
import unittest
from pathlib import Path
import core
from db import Database,Conflict

class Hostile(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();base=Path(self.tmp.name)
        self.db=Database(base/'gate.db',base/'coordination.db');self.other=Database(base/'other.db',base/'coordination.db')
        await self.db.connect();await self.other.connect()
    async def asyncTearDown(self):await self.db.close();await self.other.close();self.tmp.cleanup()
    async def test_companion_setup_lock_is_shared_but_answers_are_not(self):
        token=await self.db.lease(1,'server-setup')
        with self.assertRaises(Conflict):await self.other.lease(1,'server-setup')
        await self.db.begin(1,42)
        self.assertIsNone(await self.other.session(1,42))
        await self.db.release(1,'server-setup','incorrect-token')
        with self.assertRaises(Conflict):await self.other.lease(1,'server-setup')
        await self.db.release(1,'server-setup',token)
        token2=await self.other.lease(1,'server-setup');self.assertTrue(token2)
    async def test_different_servers_do_not_block_each_other(self):
        self.assertTrue(await self.db.lease(1,'server-setup'));self.assertTrue(await self.other.lease(2,'server-setup'))
    async def test_stale_admin_form_does_not_overwrite_a_new_setting(self):
        cfg,rev=await self.db.config(1);other,rev2=await self.db.config(1)
        cfg['brand']='Updated';await self.db.save_config(1,cfg,rev,1)
        other['brand']='Stale'
        with self.assertRaises(Conflict):await self.db.save_config(1,other,rev2,2)
        self.assertEqual((await self.db.config(1))[0]['brand'],'Updated')
    async def test_parallel_daily_posts_only_reserve_once(self):
        out=await asyncio.gather(self.db.reserve_post(1,42,'gcars',86400),self.other.reserve_post(1,42,'gcars',86400),return_exceptions=True)
        # Member cooldowns belong to Gate, so two Gate instances share its operational DB.
        # A companion uses its own DB and never enforces Gate's member cooldown.
        self.assertTrue(all(isinstance(x,float) for x in out))
        out=await asyncio.gather(self.db.reserve_post(1,43,'gcars',86400),self.db.reserve_post(1,43,'gcars',86400),return_exceptions=True)
        self.assertEqual(sum(isinstance(x,float) for x in out),1)
    async def test_post_failure_rolls_back_only_its_own_reservation(self):
        stamp=await self.db.reserve_post(1,42,'gcars',86400)
        await self.db.cancel_post(1,42,'gcars',stamp+1)
        with self.assertRaises(ValueError):await self.db.reserve_post(1,42,'gcars',86400)
        await self.db.cancel_post(1,42,'gcars',stamp)
        self.assertTrue(await self.db.reserve_post(1,42,'gcars',86400))
    async def test_registered_id_cannot_be_silently_claimed_twice(self):
        await self.db.register(1,'channel:general',123,'text',{'name':'general'})
        with self.assertRaises(Conflict):await self.other.register(1,'channel:ticket',123,'text',{'name':'ticket'})
        self.assertEqual((await self.db.resources(1))['channel:general']['object_id'],123)
    async def test_manual_flag_and_owner_are_visible_to_the_next_bot(self):
        await self.db.register(1,'channel:general',123,'text',{'name':'general'})
        await self.db.state(1,'channel:general','manual')
        self.assertEqual((await self.other.resources(1))['channel:general']['state'],'manual')
    async def test_foreign_controller_cannot_be_rebound_by_gate(self):
        await self.db.register(1,'channel:ticket',123,'text',{},owner='bot:900')
        with self.assertRaises(Conflict):await self.db.register(1,'channel:ticket',456,'text',{})
        self.assertEqual((await self.db.resources(1))['channel:ticket']['object_id'],123)
    def test_private_and_shared_paths_cannot_be_same(self):
        with self.assertRaises(ValueError):Database(self.db.path,self.db.path)
    async def test_handoff_is_atomic_and_preserves_other_resources(self):
        await self.db.register(1,'channel:ticket',123,'text',{})
        await self.db.register(1,'channel:open_tickets',124,'category',{})
        await self.db.register(1,'channel:general',125,'text',{})
        await self.db.handoff(1,('channel:ticket','channel:open_tickets'),900)
        rows=await self.db.resources(1)
        self.assertEqual((rows['channel:ticket']['owner'],rows['channel:ticket']['state']),('bot:900','external'))
        self.assertEqual(rows['channel:general']['owner'],'ripcars-gate')
    async def test_failed_handoff_does_not_partially_transfer(self):
        await self.db.register(1,'channel:ticket',123,'text',{})
        await self.db.register(1,'channel:open_tickets',124,'category',{},owner='bot:901')
        with self.assertRaises(Conflict):await self.db.handoff(1,('channel:ticket','channel:open_tickets'),900)
        self.assertEqual((await self.db.resources(1))['channel:ticket']['owner'],'ripcars-gate')
    async def test_handoff_cannot_bypass_a_peer_lease(self):
        token=await self.other.lease(1,'server-setup')
        with self.assertRaises(Conflict):await self.db.handoff(1,(),900)
        await self.other.release(1,'server-setup',token)
    async def test_manual_resource_requires_review_before_handoff(self):
        await self.db.register(1,'channel:ticket',123,'text',{})
        await self.db.state(1,'channel:ticket','manual')
        with self.assertRaises(Conflict):await self.db.handoff(1,('channel:ticket',),900)
        self.assertEqual((await self.db.resources(1))['channel:ticket']['state'],'manual')
    def test_link_filter_and_normal_text(self):
        for text in ['https://example.com','www.test.io','discord.gg/test','example.io','https：//test.com','discord\u200b.gg/test']:
            self.assertTrue(core.has_link(text),text)
        for text in ['Porsche 911','gCARS today','my dream car is an F40']:
            self.assertFalse(core.has_link(text),text)
    def test_bad_configuration_cannot_open_holder_or_duplicate_questions(self):
        cfg=core.defaults();cfg['questions'].append(dict(cfg['questions'][0]))
        with self.assertRaises(ValueError):core.validate(cfg)

if __name__=='__main__':unittest.main()
