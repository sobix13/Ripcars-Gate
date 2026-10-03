import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
AVAILABLE=importlib.util.find_spec('discord') is not None
if AVAILABLE:from main import GateBot

@unittest.skipUnless(AVAILABLE,'discord.py dependency unavailable in this execution environment')
class Boot(unittest.IsolatedAsyncioTestCase):
    async def test_real_startup_registers_only_gate_modules_and_persistent_views(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot=GateBot(Path(tmp)/'gate.db',Path(tmp)/'coord.db')
            bot.tree.sync=AsyncMock(return_value=[])
            async with bot:
                await bot.setup_hook()
                self.assertEqual(set(bot.cogs),{'Onboarding','Community','Admin'})
                self.assertEqual({c.name for c in bot.tree.get_commands()},{'gate'})
                self.assertEqual(len(bot.persistent_views),3)
                for view in bot.persistent_views:self.assertTrue(view.is_persistent())
                self.assertTrue(bot.intents.members);self.assertTrue(bot.intents.message_content)
                cfg,_=await bot.db.config(1);self.assertFalse(cfg['enabled'])

if __name__=='__main__':unittest.main()
