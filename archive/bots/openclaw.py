import discord
from discord.ext import commands
import asyncio
import json
import os
from pathlib import Path
from dotenv import load_dotenv
import sys
sys.path.insert(0, '/dev-booth')
from core.llm import chat

load_dotenv('/dev-booth/config/.env')

GUILD_ID = int(os.getenv('DISCORD_GUILD_ID'))
DEV_BOOTH_PATH = os.getenv('DEV_BOOTH_PATH', '/dev-booth/sessions')

SYSTEM_PROMPT = """You are OpenClaw, an AI orchestrator and code reviewer.
Your role:
1. Manage development sessions and assign tasks
2. Review code produced by Hermes agents
3. Create Pull Requests to the upstream repository
4. Report progress to the user

Always respond in the same language as the user.
Be concise and action-oriented."""

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

sessions = {}

@bot.event
async def on_ready():
    print(f'OpenClaw ready: {bot.user}')

@bot.command(name='new-session')
async def new_session(ctx, name: str, *, args: str = ''):
    guild = bot.get_guild(GUILD_ID)
    
    # 세션 채널 생성
    category = discord.utils.get(guild.categories, name='sessions')
    if not category:
        category = await guild.create_category('sessions')
    
    channel = await guild.create_text_channel(f'session-{name}', category=category)
    
    # 세션 디렉터리 생성
    session_path = Path(DEV_BOOTH_PATH) / name
    session_path.mkdir(parents=True, exist_ok=True)
    
    # 세션 정보 저장
    sessions[name] = {
        'channel_id': channel.id,
        'status': 'active',
        'messages': []
    }
    
    with open(session_path / 'status.json', 'w') as f:
        json.dump(sessions[name], f, indent=2)
    
    await ctx.send(f'✅ 세션 생성됨: **{name}**\n📢 채널: {channel.mention}')
    await channel.send(f'🚀 **세션 시작: {name}**\nHermes-A, 분석을 시작해주세요.')
    
    # OpenClaw가 세션 시작 알림
    response = await chat(
        [{"role": "user", "content": f"New session started: {name}. Brief intro in 2 sentences."}],
        system_prompt=SYSTEM_PROMPT,
        max_tokens=100
    )
    await channel.send(f'🔴 **OpenClaw**: {response}')

@bot.command(name='status')
async def status(ctx, name: str = None):
    if not sessions:
        await ctx.send('활성 세션 없음')
        return
    
    if name and name in sessions:
        s = sessions[name]
        await ctx.send(f'**{name}**: {s["status"]}')
    else:
        msg = '**활성 세션 목록:**\n'
        for n, s in sessions.items():
            msg += f'- {n}: {s["status"]}\n'
        await ctx.send(msg)

@bot.event
async def on_message(message):
    if message.author.bot:
        await bot.process_commands(message)
        return
    
    # OpenClaw 멘션 처리
    if bot.user in message.mentions:
        async with message.channel.typing():
            response = await chat(
                [{"role": "user", "content": message.content}],
                system_prompt=SYSTEM_PROMPT
            )
            await message.channel.send(f'🔴 **OpenClaw**: {response}')
    
    await bot.process_commands(message)

bot.run(os.getenv('OPENCLAW_TOKEN'))
