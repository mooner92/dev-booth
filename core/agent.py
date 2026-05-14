import asyncio
import json
from pathlib import Path
from datetime import datetime
from core.llm import chat
from core.notion_logger import log

SYSTEM_PROMPTS = {
    "OpenClaw": """You are OpenClaw, an AI orchestrator and code reviewer.
Your role:
1. Manage development sessions and assign tasks to Hermes-A and Hermes-B
2. Review code and make decisions
3. Create Pull Requests
Always be concise and action-oriented. Respond in Korean.""",

    "Hermes-A": """You are Hermes-A, an AI software architect.
Your role:
1. Analyze codebases and requirements
2. Design architecture and APIs
3. Give clear implementation instructions to Hermes-B
Always be precise and technical. Respond in Korean.""",

    "Hermes-B": """You are Hermes-B, an AI software developer.
Your role:
1. Implement code based on Hermes-A's designs
2. Fix bugs and write tests
3. Report completion to OpenClaw
Always focus on clean working code. Respond in Korean."""
}

class AgentSession:
    def __init__(self, name: str):
        self.name = name
        self.path = Path(f'/dev-booth/sessions/{name}')
        self.path.mkdir(parents=True, exist_ok=True)
        self.messages = {agent: [] for agent in SYSTEM_PROMPTS}
        self.conversation_log = []

    async def agent_say(self, agent: str, content: str) -> str:
        self.messages[agent].append({"role": "user", "content": content})
        
        response = await chat(
            self.messages[agent],
            system_prompt=SYSTEM_PROMPTS[agent],
            max_tokens=1024
        )
        
        self.messages[agent].append({"role": "assistant", "content": response})
        
        # 로그 저장
        entry = {
            "time": datetime.now().isoformat(),
            "agent": agent,
            "input": content,
            "output": response
        }
        self.conversation_log.append(entry)
        
        with open(self.path / 'messages.jsonl', 'a') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        
        # Notion 로그
        log(self.name, agent, response)
        
        print(f"\n{'='*50}")
        print(f"[{agent}]")
        print(response)
        
        return response

    async def run(self, goal: str):
        print(f"\n🚀 세션 시작: {self.name}")
        print(f"목표: {goal}\n")
        
        log(self.name, "OpenClaw", f"세션 시작: {goal}", "active")
        
        # 1. OpenClaw가 목표 분석 후 Hermes-A에게 지시
        oc_response = await self.agent_say(
            "OpenClaw",
            f"새 개발 세션 시작. 목표: {goal}\nHermes-A에게 분석 및 설계 지시를 내려주세요."
        )
        
        # 2. Hermes-A가 분석 후 설계
        ha_response = await self.agent_say(
            "Hermes-A",
            f"OpenClaw 지시사항:\n{oc_response}\n\n분석하고 Hermes-B에게 구현 지시를 내려주세요."
        )
        
        # 3. Hermes-B가 구현
        hb_response = await self.agent_say(
            "Hermes-B",
            f"Hermes-A 설계:\n{ha_response}\n\n구현 계획을 작성해주세요."
        )
        
        # 4. OpenClaw가 검토
        review = await self.agent_say(
            "OpenClaw",
            f"Hermes-B 구현 계획:\n{hb_response}\n\n검토 결과와 다음 단계를 알려주세요."
        )
        
        log(self.name, "OpenClaw", "1차 사이클 완료", "active")
        return review

async def main():
    import sys
    session_name = sys.argv[1] if len(sys.argv) > 1 else "test-session"
    goal = sys.argv[2] if len(sys.argv) > 2 else "Hello World 웹앱 만들기"
    
    session = AgentSession(session_name)
    await session.run(goal)

if __name__ == '__main__':
    asyncio.run(main())
