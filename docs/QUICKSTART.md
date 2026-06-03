# Dev-Booth 빠른 시작 가이드

5분 안에 첫 자율 개발 세션을 돌립니다.

---

## 1. 서비스 상태 확인 (1분)

세션을 시작하기 전에 핵심 서비스가 모두 동작 중인지 확인합니다.

```bash
curl http://localhost:8003/health           # vLLM (Qwen2.5-Coder-32B)
hermes gateway status                       # Hermes 게이트웨이
curl http://localhost:7000/api/health       # 대시보드 API
nvidia-smi | grep MiB                       # GPU 메모리 사용량
```

서비스가 내려가 있으면 한 번에 올립니다.

```bash
sudo systemctl start vllm-qwen25-coder-32b hermes-gateway dev-booth-dashboard
```

---

## 2. 첫 세션 시작 (1분)

```bash
cd /dev-booth
./run.sh start demo https://github.com/mooner92/firebase-chat-exp "버그 수정 및 코드 품질 개선"
```

- **dryrun이 기본 모드**입니다. 실제 `git push` / PR 생성은 일어나지 않습니다.
- 명령이 완료되면 Kanban 보드(`demo`)에 12단계 태스크가 자동으로 seed됩니다.
- Hermes 게이트웨이 dispatcher가 태스크를 감지하고, conductor / architect / executor 에이전트를 자동으로 spawn합니다.

실제 push와 PR이 필요한 경우에만 `live` 모드를 사용합니다.

```bash
./run.sh start demo https://github.com/mooner92/firebase-chat-exp "버그 수정 및 코드 품질 개선" live
# 확인 프롬프트에 'yes' 입력 필요
```

---

## 3. 대시보드 접속 (1분)

브라우저에서 아래 URL을 엽니다.

```
https://dashboard.excusa.uk
```

1. 세션 카드(`demo`)를 클릭합니다.
2. Kanban 보드에서 단계별 태스크 진행 상황을 실시간으로 확인합니다.
3. 에이전트 대화 로그도 같은 화면에서 볼 수 있습니다.

---

## 4. 진행 상황 확인 (2분)

터미널에서 다음 명령어로 세션 상태를 모니터링합니다.

```bash
./run.sh watch demo     # Kanban 이벤트 실시간 스트리밍
./run.sh board demo     # 현재 태스크 목록 일괄 출력
./run.sh status demo    # sessions/demo/status.json 내용 확인
./run.sh logs demo      # 세션 메시지 로그 (tail -f)
```

---

## 5. 자주 쓰는 명령어

| 명령어 | 설명 |
|---|---|
| `./run.sh gateway start` | 게이트웨이 시작 (dryrun 모드) |
| `./run.sh gateway stop` | 게이트웨이 중단 |
| `./run.sh gateway status` | 게이트웨이 상태 확인 |
| `./run.sh list` | 보드 목록 + 세션 목록 |
| `./run.sh stop <세션명>` | 세션 종료 (보드 태스크 archive) |
| `hermes kanban --board <slug> stats` | 보드 태스크 통계 |
| `hermes kanban --board <slug> unblock <task_id>` | `protocol_violation` 상태 태스크 복구 |
| `hermes profile list` | 등록된 에이전트 프로필 목록 |

> 전체 명령어 레퍼런스는 `docs/MANUAL.md` 를 참고하세요.
