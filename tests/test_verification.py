import asyncio
import tempfile
import time
import unittest
from pathlib import Path
import captcha
import core
from db import Database

class Verification(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'gate.db'
        self.db=Database(self.path);await self.db.connect();self.cfg=core.defaults()
        self.ch=captcha.create();self.token=await self.db.challenge(1,10,self.ch,300)
    async def asyncTearDown(self):await self.db.close();self.tmp.cleanup()
    async def pass_code(self):return await self.db.check_captcha(1,10,self.token,self.ch.answer.lower(),self.cfg)
    async def test_captcha_without_an_answer_never_qualifies(self):
        self.assertEqual(await self.pass_code(),'passed')
        self.assertFalse(core.eligible(await self.db.session(1,10),time.time()))
    async def test_question_before_captcha_is_rejected(self):
        with self.assertRaises(ValueError):await self.db.answer(1,10,'dream','Porsche 911',self.cfg)
    async def test_one_answer_qualifies_and_others_remain_optional(self):
        await self.pass_code();await self.db.answer(1,10,'dream','Porsche 911',self.cfg)
        s=await self.db.session(1,10);self.assertTrue(core.eligible(s,time.time()));self.assertEqual(len(s['answers']),1)
    async def test_whitespace_or_unknown_question_is_rejected(self):
        await self.pass_code()
        for q,v in [('dream','   '),('fake','yes')]:
            with self.assertRaises(ValueError):await self.db.answer(1,10,q,v,self.cfg)
    async def test_captcha_is_single_use_and_bound_to_user(self):
        self.assertEqual(await self.db.check_captcha(1,11,self.token,self.ch.answer,self.cfg),'stale')
        await self.pass_code();self.assertEqual(await self.pass_code(),'stale')
    async def test_failed_attempts_lock_and_survive_restart(self):
        for _ in range(2):self.assertEqual(await self.db.check_captcha(1,10,self.token,'WRONG',self.cfg),'wrong')
        self.assertEqual(await self.db.check_captcha(1,10,self.token,'WRONG',self.cfg),'locked')
        await self.db.close();self.db=Database(self.path);await self.db.connect()
        self.assertEqual(await self.pass_code(),'locked')
        with self.assertRaises(ValueError):await self.db.challenge(1,10,self.ch,300)
    async def test_expiry_blocks_a_valid_code(self):
        self.assertEqual(await self.db.check_captcha(1,10,self.token,self.ch.answer,self.cfg,now=time.time()+301),'expired')
    async def test_question_progress_survives_restart(self):
        await self.pass_code();await self.db.answer(1,10,'collector','Yes',self.cfg)
        await self.db.close();self.db=Database(self.path);await self.db.connect()
        self.assertTrue(core.eligible(await self.db.session(1,10),time.time()))
    async def test_rejoin_requires_fresh_entry_but_preserves_research_data(self):
        await self.pass_code();await self.db.answer(1,10,'dream','F40',self.cfg)
        await self.db.verified(1,10);await self.db.begin(1,10,reset=True)
        self.assertFalse(core.eligible(await self.db.session(1,10),time.time()))
        self.assertEqual(len(await self.db.query('SELECT * FROM profiles WHERE guild=?',(1,))),1)
    async def test_parallel_correct_submits_consume_only_once(self):
        results=await asyncio.gather(self.pass_code(),self.pass_code())
        self.assertEqual(sorted(results),['passed','stale'])
    async def test_grant_failure_is_not_recorded_as_success(self):
        await self.db.verified(1,10,'Missing permissions');s=await self.db.session(1,10)
        self.assertEqual(s['verified'],0);self.assertTrue(s['role_error'])
    def test_png_and_hash(self):
        self.assertTrue(self.ch.png.startswith(b'\x89PNG'))
        self.assertNotEqual(self.ch.answer,self.ch.digest)
        self.assertFalse(captcha.verify(self.ch.answer+'Z',self.ch.salt,self.ch.digest))

if __name__=='__main__':unittest.main()
