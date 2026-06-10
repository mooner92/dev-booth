import { PageShell } from "@/components/PageShell";
import { siteConfig } from "@/lib/siteConfig";

export const metadata = { title: `사이트 소개 | ${siteConfig.name}` };

export default function AboutPage() {
  return (
    <PageShell
      title="사이트 소개"
      intro={siteConfig.tagline}
    >
      <h2>무엇을 하나요</h2>
      <p>
        <strong>{siteConfig.name}</strong>은 Git 저장소 URL 하나만 입력하면 저장소 분석 → 구현 →
        테스트 → 커밋 → PR까지 사람 개입 없이 진행하는 자율 개발 시스템입니다. 이 화면은 그 진행
        상황을 실시간으로 지켜보는 <strong>관제 대시보드</strong>입니다.
      </p>

      <h2>어떻게 동작하나요</h2>
      <p>
        세 개의 AI 에이전트가 칸반 보드를 통해서만 협업합니다. 각 작업은 12단계 파이프라인을 따라
        진행됩니다.
      </p>
      <ul>
        <li><strong>Conductor</strong> — 작업을 쪼개고 흐름을 조율</li>
        <li><strong>Architect</strong> — 코드 분석과 설계</li>
        <li><strong>Executor</strong> — 실제 구현과 테스트</li>
      </ul>

      <h2>핵심 원칙</h2>
      <p>
        모든 추론은 서버 내부의 <strong>로컬 모델(vLLM)</strong>에서 수행되며, 코드와 데이터가 외부
        API·클라우드로 전송되지 않습니다. 자동화는 초안을 만들고, 커밋·PR의 최종 확인은 사람이
        합니다.
      </p>

      <h2>대상 사용자</h2>
      <p>자율 개발 파이프라인을 시작·모니터링하고, 필요할 때 막힌 작업을 풀어 주는 운영자입니다.</p>

      <h2>더 알아보기</h2>
      <p>
        사용 순서는 <a href="/guide">사용 안내</a>, 자주 묻는 질문은 <a href="/faq">FAQ</a>를
        참고하세요. 소스 코드는{" "}
        <a href={siteConfig.githubUrl} target="_blank" rel="noreferrer">
          GitHub 저장소
        </a>
        에서 볼 수 있습니다.
      </p>
    </PageShell>
  );
}
