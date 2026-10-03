#!/usr/bin/env python3
"""No network and no secret output. Missing runtime dependencies fail closed."""
import argparse
import asyncio
import importlib.metadata
import os
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

async def check():
    parser=argparse.ArgumentParser();parser.add_argument('--code-only',action='store_true');args=parser.parse_args()
    if sys.version_info<(3,10):raise SystemExit('Python 3.10 or newer is required.')
    try:
        version=importlib.metadata.version('discord.py')
        if version!='2.6.4':raise SystemExit('Install the pinned discord.py version in requirements.txt.')
        import discord
        from PIL import Image
    except ImportError:raise SystemExit('Install requirements.txt in the bot virtual environment first.')
    import core
    from db import Database
    core.validate(core.defaults())
    # Every configured permission must be recognized by the installed runtime.
    for spec in core.BLUEPRINT.values():
        for flags in core.access_policy(spec).values():discord.PermissionOverwrite(**flags)
    from cogs.admin import Admin,SECTIONS,SectionView
    from main import GateBot
    if not args.code_only:
        token=os.environ.get('DISCORD_TOKEN','').strip()
        if not token:raise SystemExit('DISCORD_TOKEN is empty. Edit /etc/ripcars-gate.env.')
        guild=os.environ.get('GUILD_ID','').strip()
        if guild and not guild.isdigit():raise SystemExit('GUILD_ID must be a numeric server ID.')
        for key in ('DB_PATH','COORDINATION_PATH'):
            path=Path(os.environ[key]);path.parent.mkdir(parents=True,exist_ok=True)
            if not os.access(path.parent,os.W_OK):raise SystemExit(f'{key} directory is not writable.')
    print('Preflight passed: configuration, runtime imports, and permission flags.')

if __name__=='__main__':asyncio.run(check())
