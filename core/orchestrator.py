import asyncio
import subprocess
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from core.llm import chat
from core.notion_logger import log, log_document

load_dotenv('/dev-booth/config/.env')

SESSIONS_ROOT = '/dev-booth/sessions'
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
UPSTREAM_OWNER = os.getenv('GITHUB_UPSTREAM_OWNER', 'mooner92')
BOT_OWNER = os.getenv('GITHUB_BOT_OWNER', 'CrownClownCrowd')

SYSTEM_PROMPTS = {
    "OpenClaw": """You are OpenClaw, lead AI agent and orchestrator.
Responsibilities: manage sessions, assign tasks, review code, approve commits, create PRs.
Always respond in Korean. Be concise and decisive.""",

    "Hermes-A": """You are Hermes-A, AI software architect.
Responsibilities: analyze codebases, design architecture, write technical specs, delegate to Hermes-B.
Always respond in Korean. Be technical and precise.""",

    "Hermes-B": """You are Hermes-B, AI software developer.
Responsibilities: implement code, fix bugs, write tests, report completion.
Always respond in Korean. Focus on working code."""
}

class DevBoothSession:
    def __init__(self, session_name: str, repo_url: str):
        self.name = session_name
        self.repo_url = repo_url
        self.repo_name = repo_url.rstrip('/').split('/')[-1]
        self.path = Path(f'{SESSIONS_ROOT}/{session_name}')
        self.path.mkdir(parents=True, exist_ok=True)
        self.awg_root = str(self.path / 'awg')
        self.project_path = self.path / 'project'
        self.messages = {agent: [] for agent in SYSTEM_PROMPTS}
        os.environ['AWG_ROOT'] = self.awg_root

    def awg(self, *args) -> str:
        result = subprocess.run(
            ['awg'] + list(args),
            capture_output=True, text=True,
            env={**os.environ, 'AWG_ROOT': self.awg_root}
        )
        return result.stdout.strip()

    def awg_init(self):
        self.awg('init', '--agent', 'openclaw', '--agent', 'hermes-a', '--agent', 'hermes-b')

    def send(self, from_agent: str, to_agent: str, kind: str, body: str):
        return self.awg('send', f'--from={from_agent}', f'--to={to_agent}',
                        f'--kind={kind}', f'--body={body}')

    def recv(self, agent: str) -> dict | None:
        result = self.awg('recv', f'--as={agent}', '--require-ack', '--timeout=10')
        if not result:
            return None
        try:
            return json.loads(result)
        except:
            return None

    def ack(self, agent: str, msg_id: str):
        self.awg('ack', f'--as={agent}', f'--id={msg_id}')

    async def think(self, agent: str, content: str, max_tokens: int = 1024) -> str:
        self.messages[agent].append({"role": "user", "content": content})
        response = await chat(self.messages[agent], SYSTEM_PROMPTS[agent], max_tokens)
        self.messages[agent].append({"role": "assistant", "content": response})
        print(f"\n[{agent}]\n{response}\n")
        log(self.name, agent, response, repository=self.repo_name)
        return response

    def git(self, *args, cwd=None) -> str:
        result = subprocess.run(
            ['git'] + list(args),
            capture_output=True, text=True,
            cwd=cwd or str(self.project_path)
        )
        return result.stdout.strip()

    def gh(self, *args) -> str:
        result = subprocess.run(
            ['gh'] + list(args),
            capture_output=True, text=True,
            env={**os.environ, 'GH_TOKEN': GITHUB_TOKEN}
        )
        return result.stdout.strip()

    # ─── 1단계: 준비 ───────────────────────────────────────────
    async def step1_setup(self):
        print(f"\n{'='*60}")
        print(f"🚀 Dev-Booth 세션 시작: {self.name}")
        print(f"레포: {self.repo_url}")
        print(f"{'='*60}\n")

        log(self.name, "OpenClaw", f"세션 시작: {self.repo_url}", "active", self.repo_name)
        self.awg_init()

        # fork
        repo_path = self.repo_url.replace('https://github.com/', '')
        fork_result = self.gh('repo', 'fork', repo_path, '--clone=false')
        log(self.name, "OpenClaw", f"Fork 완료: {BOT_OWNER}/{self.repo_name}", repository=self.repo_name)

        # clone
        self.project_path.parent.mkdir(parents=True, exist_ok=True)
        clone_url = f"https://{GITHUB_TOKEN}@github.com/{BOT_OWNER}/{self.repo_name}.git"
        subprocess.run(['git', 'clone', clone_url, str(self.project_path)], check=True)

        # develop 브랜치
        self.git('checkout', '-b', 'develop')
        self.git('push', '-u', 'origin', 'develop')
        log(self.name, "OpenClaw", "Clone 완료, develop 브랜치 생성", repository=self.repo_name)

    # ─── 2단계: 분석 ───────────────────────────────────────────
    async def step2_analyze(self):
        print("\n📊 분석 단계 시작\n")

        # 프로젝트 파일 목록
        files = subprocess.run(
            ['find', str(self.project_path), '-type', 'f',
             '-not', '-path', '*/.git/*', '-not', '-path', '*/node_modules/*'],
            capture_output=True, text=True
        ).stdout.strip()

        # Hermes-A: 구조 분석
        self.send('openclaw', 'hermes-a', 'instruction', f'프로젝트 구조를 분석해주세요.\n파일 목록:\n{files[:3000]}')
        msg = self.recv('hermes-a')
        if msg:
            ha_analysis = await self.think('Hermes-A', msg['body'])
            self.ack('hermes-a', msg['id'])
            (self.path / 'analysis_hermes_a.md').write_text(ha_analysis)
            self.send('hermes-a', 'openclaw', 'answer', ha_analysis[:500])

        # Hermes-B: 기술스택 분석
        self.send('openclaw', 'hermes-b', 'instruction', f'기술스택과 의존성을 분석해주세요.\n파일 목록:\n{files[:3000]}')
        msg = self.recv('hermes-b')
        if msg:
            hb_analysis = await self.think('Hermes-B', msg['body'])
            self.ack('hermes-b', msg['id'])
            (self.path / 'analysis_hermes_b.md').write_text(hb_analysis)
            self.send('hermes-b', 'openclaw', 'answer', hb_analysis[:500])

        # OpenClaw: 최종 요약
        ha_text = (self.path / 'analysis_hermes_a.md').read_text()
        hb_text = (self.path / 'analysis_hermes_b.md').read_text()
        summary = await self.think('OpenClaw',
            f'두 분석을 취합해서 summary_v1.0.0.md를 작성해주세요.\n\nHermes-A:\n{ha_text}\n\nHermes-B:\n{hb_text}',
            max_tokens=2048)
        (self.path / 'summary_v1.0.0.md').write_text(summary)
        log_document(self.name, "OpenClaw", "summary_v1.0.0", summary, repository=self.repo_name)
        log_document(self.name, "OpenClaw", "summary_v1.0.0", summary, repository=self.repo_name)
        log(self.name, "OpenClaw", "최종 요약본 v1.0.0 작성 완료", repository=self.repo_name)

    # ─── 3단계: 개선방안 설계 ──────────────────────────────────
    async def step3_plan(self):
        print("\n📋 개선방안 설계 단계\n")

        summary = (self.path / 'summary_v1.0.0.md').read_text()

        # 토의
        ha_plan = await self.think('Hermes-A', f'요약본 기반으로 개선방안을 제안해주세요:\n{summary}')
        hb_plan = await self.think('Hermes-B', f'요약본 기반으로 개선방안을 제안해주세요:\n{summary}')
        log(self.name, "3자토의", "개선방안 토의 시작", repository=self.repo_name)

        improvements = await self.think('OpenClaw',
            f'두 제안을 취합해서 improvements_v0.0.1.md를 작성해주세요. 각 TASK에 담당자(Hermes-A/Hermes-B)를 명시해주세요.\n\nHermes-A 제안:\n{ha_plan}\n\nHermes-B 제안:\n{hb_plan}',
            max_tokens=2048)
        (self.path / 'improvements_v0.0.1.md').write_text(improvements)
        log_document(self.name, "OpenClaw", "improvements_v0.0.1", improvements, repository=self.repo_name)
        log(self.name, "OpenClaw", "개선방안 v0.0.1 확정", repository=self.repo_name)
        return improvements

    # ─── 4단계: 개발 루프 ──────────────────────────────────────
    async def step4_develop(self, task: str, assignee: str):
        print(f"\n⚙️  개발: {task} [{assignee}]\n")

        feature_branch = f"feature/{task.lower().replace(' ', '-')[:30]}"
        self.git('checkout', '-b', feature_branch)
        log(self.name, "OpenClaw", f"브랜치 생성: {feature_branch}", repository=self.repo_name)

        # 개발 지시
        response = await self.think(assignee,
            f'다음 태스크를 구현해주세요: {task}\n구현할 코드와 파일명을 알려주세요.',
            max_tokens=2048)
        log(self.name, assignee, f"작업중: {task}", repository=self.repo_name)
        return response, feature_branch

    # ─── 5단계: 커밋 검토 ──────────────────────────────────────
    async def step5_commit_review(self, task: str, feature_branch: str):
        print("\n🔍 커밋 검토\n")
        log(self.name, "3자토의", f"커밋 검토 시작: {task}", repository=self.repo_name)

        diff = self.git('diff', '--stat')
        review = await self.think('OpenClaw',
            f'다음 변경사항을 검토해주세요:\n{diff}\n\n커밋해도 될지 판단하고, 커밋 메시지를 작성해주세요.',
            max_tokens=512)

        if '승인' in review or 'approve' in review.lower():
            commit_msg = review.split('\n')[0]
            self.git('add', '.')
            self.git('commit', '-m', commit_msg)
            self.git('push', 'origin', feature_branch)
            log(self.name, "OpenClaw", f"커밋 승인: {commit_msg}", "done", self.repo_name)
            return True
        else:
            log(self.name, "OpenClaw", f"커밋 반려: {review}", "error", self.repo_name)
            return False

    # ─── 6단계: PR 생성 ────────────────────────────────────────
    async def step6_create_pr(self, feature_branch: str):
        print("\n📬 PR 생성\n")
        log(self.name, "3자토의", "PR 적합도 토의 시작", repository=self.repo_name)

        improvements = (self.path / 'improvements_v0.0.1.md').read_text()
        pr_body = await self.think('OpenClaw',
            f'PR 설명을 작성해주세요. 변경사항과 테스트 결과를 포함해주세요.\n개선방안:\n{improvements}',
            max_tokens=1024)

        pr_result = self.gh('pr', 'create',
            '--title', f'[Dev-Booth] {self.name} improvements v0.0.1',
            '--body', pr_body,
            '--base', 'main',
            '--head', f'{BOT_OWNER}:{feature_branch}',
            '--repo', f'{UPSTREAM_OWNER}/{self.repo_name}')

        log(self.name, "OpenClaw", f"PR 제출 완료: {pr_result}", "done", self.repo_name)
        return pr_result

    # ─── 전체 실행 ─────────────────────────────────────────────
    async def run(self):
        await self.step1_setup()
        await self.step2_analyze()
        improvements = await self.step3_plan()
        print("\n개선방안이 작성됐습니다. 개발을 시작합니다...\n")
        print(improvements)

async def main():
    if len(sys.argv) < 3:
        print("Usage: python3 -m core.orchestrator <session-name> <repo-url>")
        sys.exit(1)

    session = DevBoothSession(sys.argv[1], sys.argv[2])
    await session.run()

if __name__ == '__main__':
    asyncio.run(main())
