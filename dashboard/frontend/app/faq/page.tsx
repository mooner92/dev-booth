import { PageShell } from "@/components/PageShell";
import { FaqAccordion, type FaqItem } from "@/components/FaqAccordion";
import { siteConfig } from "@/lib/siteConfig";

export const metadata = { title: `자주 묻는 질문 | ${siteConfig.name}` };

const faqs: FaqItem[] = [
  {
    q: "코드나 데이터가 외부로 전송되나요?",
    a: (
      <>
        아니요. 모든 추론은 서버 내부의 <strong>로컬 모델(vLLM)</strong>에서 수행되며, 코드·데이터가
        외부 API나 클라우드로 전송되지 않습니다.
      </>
    ),
  },
  {
    q: "어떤 모델을 사용하나요?",
    a: (
      <>
        로컬에 서빙된 코드 특화 모델(Qwen2.5-Coder 계열)을 vLLM으로 구동합니다. 상단의{" "}
        <strong>vLLM</strong> 표시로 모델이 온라인인지 확인할 수 있습니다.
      </>
    ),
  },
  {
    q: "작업이 멈췄어요(blocked).",
    a: (
      <>
        대부분 테스트 실패나 더 진행할 수 없는 상황입니다. 세션 상세의 <strong>unblock</strong> 배너로
        다시 진행시키거나, 채팅 스트림의 마지막 로그에서 원인을 확인하세요. 사용법은{" "}
        <a href="/guide">사용 안내</a>의 “막힌 작업 풀기”를 참고하세요.
      </>
    ),
  },
  {
    q: "한 세션은 얼마나 걸리나요?",
    a: <>저장소 크기와 작업 난이도에 따라 다릅니다. 세션 카드의 단계 바로 실시간 진행률을 확인하세요.</>,
  },
  {
    q: "PR은 어디로 올라가나요?",
    a: (
      <>
        연결된 <strong>GitHub 봇 계정</strong>으로 대상 저장소에 PR을 만듭니다. 홈 화면의 “GitHub 봇
        계정” 카드에서 현재 계정과 대상을 확인할 수 있습니다.
      </>
    ),
  },
  {
    q: "광고나 외부 추적이 있나요?",
    a: (
      <>
        없습니다. 이 대시보드는 내부 운영 도구이며 광고·외부 분석 도구(애드센스·트래킹 등)를 사용하지
        않습니다.
      </>
    ),
  },
  {
    q: "로그인이나 회원가입이 필요한가요?",
    a: <>아니요. 대시보드는 로컬 환경에서 바로 사용합니다.</>,
  },
  {
    q: "소스 코드는 어디서 보나요?",
    a: (
      <>
        <a href={siteConfig.githubUrl} target="_blank" rel="noreferrer">
          GitHub 저장소({siteConfig.repoLabel})
        </a>
        에서 확인할 수 있습니다.
      </>
    ),
  },
];

export default function FaqPage() {
  return (
    <PageShell
      title="자주 묻는 질문"
      intro="대시보드를 쓰면서 자주 나오는 질문을 모았습니다. 항목을 눌러 펼쳐 보세요."
    >
      <FaqAccordion items={faqs} />
      <p className="mt-6">
        여기서 해결되지 않으면 <a href={`mailto:${siteConfig.email}`}>{siteConfig.email}</a>로 문의해
        주세요.
      </p>
    </PageShell>
  );
}
