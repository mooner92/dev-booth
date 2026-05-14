import discord
from discord.ext import commands
import asyncio
import os
from dotenv import load_dotenv
import sys
sys.path.insert(0, '/dev-booth')
from core.llm import chat

load_dotenv('/dev-booth/config/.env')

def create_hermes_bot(token_env: str, name: str, role: str, system_prompt: str):
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix='!', intents=intents)

    @bot.event
    async def on_ready():
        print(f'{name} ready: {bot.user}')

    @bot.event
    async def on_message(message):
        if message.author.bot:
            await bot.process_commands(message)
            return

        if bot.user in message.mentions:
            async with message.channel.typing():
                response = await chat(
                    [{"role": "user", "content": message.content}],
                    system_prompt=system_prompt
                )
                emoji = '🔵' if name == 'Hermes-A' else '🟢'
                await message.channel.send(f'{emoji} **{name}**: {response}')

        await bot.process_commands(message)

    return bot, os.getenv(token_env)

# Hermes-A: 분석/설계
hermes_a_prompt = """You are Hermes-A, an AI software architect and analyst.
Your role:
1. Analyze codebases and project requirements
2. Design software architecture and API structure
3. Create technical specifications
4. Delegate implementation tasks to Hermes-B

Always respond in the same language as the user.
Be precise and technical."""

# Hermes-B: 구현/코딩
hermes_b_prompt = """You are Hermes-B, an AI software developer.
Your role:
1. Implement code based on Hermes-A's designs
2. Fix bugs and write tests
3. Commit code to the repository
4. Request code review from OpenClaw

Always respond in the same language as the user.
Focus on clean, working code."""

import threading

def run_bot(bot, token):
    bot.run(token)

if __name__ == '__main__':
    import sys
    which = sys.argv[1] if len(sys.argv) > 1 else 'a'
    
    if which == 'a':
        bot, token = create_hermes_bot('HERMES_A_TOKEN', 'Hermes-A', 'architect', hermes_a_prompt)
    else:
        bot, token = create_hermes_bot('HERMES_B_TOKEN', 'Hermes-B', 'developer', hermes_b_prompt)
    
    bot.run(token)
