// 사이트 정보 한 곳에서 관리. 이름/문구/링크는 여기서만 바꾸면 됩니다.
export const siteConfig = {
  name: "Dev-Booth",
  tagline: "완전 로컬 자율 개발 시스템",
  description:
    "Git 저장소 URL 하나로 분석부터 PR까지 사람 개입 없이 진행하는 로컬 AI 개발 파이프라인",
  githubUrl: "https://github.com/mooner92/dev-booth",
  issuesUrl: "https://github.com/mooner92/dev-booth/issues",
  repoLabel: "mooner92/dev-booth",
  email: "support.aidt@kei.re.kr",
} as const;

// 정보 페이지 공통 네비게이션 항목 (푸터·헤더에서 재사용)
export const infoNav = [
  { href: "/about", label: "사이트 소개" },
  { href: "/guide", label: "사용 안내" },
  { href: "/faq", label: "자주 묻는 질문" },
] as const;
