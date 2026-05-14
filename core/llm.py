import aiohttp
from dotenv import load_dotenv
import os

load_dotenv('/dev-booth/config/.env')

VLLM_BASE_URL = os.getenv('VLLM_BASE_URL', 'http://localhost:8000/v1')
AGENT_MODEL = os.getenv('AGENT_MODEL', 'Qwen/Qwen3-Coder-Next-FP8')

async def chat(messages: list, system_prompt: str = None, max_tokens: int = 2048) -> str:
    if system_prompt:
        messages = [{"role": "system", "content": system_prompt}] + messages

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{VLLM_BASE_URL}/chat/completions",
            json={
                "model": AGENT_MODEL,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.7,
            }
        ) as resp:
            data = await resp.json()
            if 'choices' not in data:
                print(f"[LLM ERROR] 응답에 choices 없음: {data}")
                return f"[ERROR] {data.get('message', str(data))}"
            return data['choices'][0]['message']['content']
