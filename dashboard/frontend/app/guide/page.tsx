import { PageShell } from "@/components/PageShell";
import { siteConfig } from "@/lib/siteConfig";

export const metadata = { title: `사용 안내 | ${siteConfig.name}` };

export default function GuidePage() {
  return (
    <PageShell
      title="사용 안내"
      intro={`${siteConfig.name} 대시보드를 처음 쓰는 분을 위한 사용 설명서입니다. 작업 시작부터 모니터링까지 순서대로 정리했습니다.`}
    >
      <p className="rounded-md border border-brand/30 bg-brand-50/60 px-4 py-3 text-sm text-foreground dark:bg-brand/10">
        원칙 — 이 대시보드는 <strong>읽기 중심 관제 화면</strong>입니다. 실제 작업은 에이전트가
        자동으로 수행하고, 사람은 작업을 시작하고 지켜보다가 필요할 때만 막힌 작업을 풀어 줍니다.
      </p>

      <h2>1. 새 작업 시작</h2>
      <ol>
        <li>우측 상단 <strong>새 작업 시작</strong> 버튼을 누릅니다.</li>
        <li>작업할 <strong>Git 저장소 URL</strong>을 입력하고 세션을 생성합니다.</li>
        <li>잠시 후 세션 목록에 카드로 나타나며 자동으로 파이프라인이 돌기 시작합니다.</li>
      </ol>

      <h2>2. 진행 상황 보기</h2>
      <p>
        세션 카드의 단계 바(예: <strong>5/12</strong>)와 현재 단계 라벨로 어디까지 왔는지 확인합니다.
        12단계는 다음 순서입니다.
      </p>
      <ol>
        <li>저장소 클론 → 초기 분석 → 계획 초안 → 계획 승인</li>
        <li>구현 → 자체 리뷰 → 테스트 실행 → 테스트 통과</li>
        <li>PR 초안 → PR 리뷰 → PR 승인 → 머지 완료</li>
      </ol>

      <h2>3. 세션 상세 들여다보기</h2>
      <p>세션 카드를 누르면 해당 작업의 내부를 볼 수 있습니다.</p>
      <ul>
        <li><strong>채팅 스트림</strong> — 에이전트들이 주고받는 대화와 도구 호출</li>
        <li><strong>파일 트리</strong> — 변경된 파일과 내용(에디터로 열람)</li>
        <li><strong>칸반 보드</strong> — 작업 카드의 상태(대기/진행/완료/막힘)</li>
        <li><strong>모니터링</strong> — vLLM 상태와 큐 적체 추이</li>
      </ul>

      <h2>4. 막힌 작업 풀기</h2>
      <p>
        작업이 <strong>blocked</strong>로 멈추면(보통 테스트 실패나 진행 불가) 상단의 unblock 배너나
        칸반 카드에서 다시 진행시킬 수 있습니다. 원인이 궁금하면 채팅 스트림의 마지막 로그를
        확인하세요.
      </p>

      <h2>5. Village 보기</h2>
      <p>
        상단 <strong>🏢 Village</strong>에서 에이전트들의 활동을 가상 오피스 화면으로 볼 수 있습니다.
      </p>

      <h2>6. 검색·필터</h2>
      <p>
        세션 목록 위의 검색창으로 세션명·에이전트를 찾고, <strong>전체 / 실행 중 / 완료 / 미상</strong>{" "}
        필터로 좁혀 볼 수 있습니다.
      </p>

      <h2>도움이 더 필요하면</h2>
      <p>
        못 찾은 내용은 <a href="/faq">자주 묻는 질문</a>을 보거나{" "}
        <a href={`mailto:${siteConfig.email}`}>{siteConfig.email}</a> ·{" "}
        <a href={siteConfig.issuesUrl} target="_blank" rel="noreferrer">
          GitHub Issues
        </a>
        로 알려 주세요.
      </p>
    </PageShell>
  );
}
