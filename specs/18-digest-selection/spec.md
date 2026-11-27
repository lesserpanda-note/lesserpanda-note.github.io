# Spec: 다이제스트 선별 결정론화와 하루 상한            (specs/18-digest-selection/spec.md)

이슈 #18. 2026-11-27 master와 합의(Q1~Q6 추천안 수용).

## 1. 의도 (무엇을·왜·누구를 위해)
- 무엇을: 하루 다이제스트 분량을 줄이고, 기계로 판정할 수 있는 선별 규칙을 LLM 지시문 밖에서 강제·테스트한다.
- 왜:
  - 2026-11-26부터 후보 기준이 `collected_at > updated`로 바뀌어 하루 후보가 30~76건으로 늘었고, 11-26은 18건이 실려 master가 확인하기 어려웠다(최근 4주 평균 8.8건).
  - 선별 규칙이 두 LLM 지시문과 `CLAUDE.md`에만 있어 위반이 그대로 실린다. 11-26의 Latent Space `[AINews]`(X·Reddit 일일 모음)는 링크 모음 규칙 위반인데 실렸고, `[AINews]`는 최근 4주에 7번 실렸다.
- 이걸로 master가 할 수 있게 되는 것: 하루 10건 이내의 다이제스트를 훑어보고, 퀴즈·모음글·패치 범프가 섞이지 않는다고 믿을 수 있다.

## 2. 인수조건 (AC)
- [ ] AC1 (하루 상한): Given 어느 날 후보가 몇 건이든, When 다이제스트가 만들어지면, Then `highlights`는 전체 10건 이하이고 어느 카테고리도 3건을 넘지 않는다. 여러 날을 밀려서 만들 때는 날마다 따로 적용한다.
- [ ] AC2 (우선순위): Given 한 카테고리에 보안 공지·메이저 릴리스·일반 글이 섞여 상한을 넘으면, When 고를 때, Then 보안 공지 → 메이저 릴리스 → 나머지 순으로 채운다. 보안 공지와 메이저 릴리스도 상한에 포함된다. 상한에 밀린 보안 공지 중 보안 패널 출처(Spring Security·Node.js Security 등 `data/security.json`이 수집하는 것)는 패널에 남고, 다른 출처의 CVE 글(예: Cloudflare·Foojay)은 남지 않는다. 루틴이 같은 소식의 중복(`duplicate`)이나 본문을 읽지 못함(`unreadable`)을 사유로 건너뛴 상위 tier 후보는 순서 검사에서 빠지고, 건너뛴 항목과 사유는 `digest-status.json`에 남는다(2026-11-27 M1 게이트 결정).
- [ ] AC3 (후보 제외 — 퀴즈): Given 제목이 `Quiz:`로 시작하는 Real Python 글, Then 후보에 오르지 않는다.
- [ ] AC4 (후보 제외 — 모음글): Given 제목이 `[AINews]`로 시작하는 Latent Space 글 또는 `This Week in …` 형태의 링크 모음, Then 후보에 오르지 않는다. Given InfoQ `… News Roundup`처럼 내용을 직접 담은 로드업, Then 후보에 남는다. Latent Space의 다른 글(인터뷰·에세이)도 남는다.
- [ ] AC5 (후보 제외 — 패치 범프): Given 라이브러리 릴리스 피드(Transformers, MCP servers, Pydantic AI, LlamaIndex, CrewAI, NumPy, pandas)의 패치 버전(`x.y.z`, z≥1) 항목, Then 후보에 오르지 않는다. 단 제목이나 저장된 요약에 보안 표현(`CVE`, `security`, `vulnerability`)이 있으면 남는다.
- [ ] AC6 (후보 제외 — 사전·포인트 릴리스): Given Node.js Blog의 alpha·nightly·point 릴리스, 또는 제목에 alpha/beta/nightly/canary/rc/milestone(`-M1` 등) 표시가 있는 릴리스, Then 후보에 오르지 않는다. Given 새 메이저 라인, LTS 전환, 보안 릴리스, Then 후보에 남는다. Node point 릴리스는 `x.y.z`(z≥1)이고, `x.y.0`은 제목으로 LTS 전환과 구분되지 않으므로 남는다(2026-11-27 M1 게이트 결정). Node.js Blog 피드에는 요약이 없어 보안 릴리스를 제목으로 가릴 수 없으므로, `data/security.json`의 Node "Security Releases" 공지와 24시간 이내에 나온 Node 릴리스는 보안 릴리스로 보고 남기며 tier 0이다(2026-11-28 PR #24 리뷰 후 master 결정, 11-11 `26.13.1`·`24.22.3`·`22.23.5`가 근거).
- [ ] AC7 (회귀 고정): 현재 `data/news.json`(1,268건)에서 뽑은 실제 제목으로 AC3~AC6 판정 사례(제외되는 것·남는 것 모두)가 테스트로 고정된다. 특히 11-26의 `[AINews] Gemini 4 Neon …`은 제외, InfoQ `Java News Roundup`·Spring 보안 공지·Hibernate `5.0.0.Final`은 남는다.
- [ ] AC8 (커밋 전 검사): Given 다이제스트에 상한 초과나 AC3~AC6 제외 대상이 들어 있으면, When 커밋하려 하면, Then 위반한 채로는 커밋되지 않는다. 루틴은 위반 항목을 빼고 다시 검사하며, 뺀 항목과 사유를 `data/digest-status.json`에 남긴다(조용히 통과시키지 않는다). 여러 날을 보충할 때는 `archive.json`에 들어가는 날짜분도 같은 검사를 거친다. 로컬 루틴과 클라우드 루틴 모두 같은 검사를 거친다.
- [ ] AC9 (역할 분담): 같은 우선순위 단계 안에서 무엇을 고를지와 `summary`·`detail` 작성은 계속 LLM이 맡는다. 결정론 단계는 후보 제외·우선순위 단계 분류·상한 검사만 한다.
- [ ] AC10 (문서 동기화): `CLAUDE.md`의 Item Selection Rules, 로컬 SKILL.md STEP 3, 클라우드 루틴 프롬프트의 선별 단계가 같은 수치(10건·3건)와 같은 제외 규칙을 말하고, 기계 판정 부분은 스크립트를 가리킨다.

## 3. 범위 & 비목표
- 포함: 후보 제외 규칙의 결정론화, 우선순위 단계 분류, 하루·카테고리 상한, 커밋 전 검사, 세 문서의 규칙 갱신.
- 하지 말 것(non-goals):
  - 중요도 점수화 — #22
  - 마감 기준(digest `updated`) 변경 — #19
  - GitHub 예약 실행 지연 — #20
  - 클라우드 403 사이트 — #21
  - 사이트 화면(UI) 변경 — #23
  - 피드 추가·삭제, `reclassify()` 변경, 카테고리 명부 변경
  - 요청 안 한 리팩터·헬퍼·추상화
  - 손대지 말 것: `data/news.json`·`data/security.json`의 수집 형식, `deploy.yml`

## 4. 제약
- 스택: Python 3.12(Actions) / 로컬 루틴의 python3, 의존성은 `requirements.txt` 범위 안.
- 컨벤션: `scripts/`의 기존 형식(`fetch_news.py`, `test_*.py`), 영어 코드 주석·커밋 요약. 다이제스트 데이터는 루틴이 main에 직접 커밋하고, 코드 변경은 `feature/18-digest-selection` 브랜치와 PR로.
- 로컬 루틴은 앱 내장 브라우저로 본문을 읽고, 클라우드는 WebFetch만 쓴다 — 결정론 단계는 본문 없이 `news.json` 필드(title·source·category·summary·published·collected_at)만으로 판정해야 한다.

## 5. 파일/모듈 계약
- 계층: 순수 판정(제목·출처·요약 → 제외/단계) → 경계(`news.json`·`digest.json` 읽기, 검사 결과 출력) → 배선(두 루틴 프롬프트가 호출).
- 새/수정 파일(구체 설계는 /tasks에서):
  - `scripts/` 아래 선별 스크립트와 그 테스트: 후보 제외·단계 분류·상한 검사
  - `CLAUDE.md` Item Selection Rules
  - `~/.claude/scheduled-tasks/lesserpanda-digest-fallback/SKILL.md` STEP 2·3·6 (repo 밖)
  - 클라우드 루틴 프롬프트 (RemoteTrigger로 갱신, repo 밖)

## 6. 자기검증 방법
- 순수 로직: 새 `scripts/test_*.py`를 기존처럼 `python scripts/test_<name>.py`(pytest 없이 plain assert)로 실행해 통과 (AC3~AC7).
- 경계: 현재 `news.json`과 11-26 다이제스트(18건 원본, archive)에 스크립트를 돌려 `[AINews]` 제외·상한 위반 보고를 관찰(AC1·AC8).
- 배선: 다음 로컬 09:39 실행의 `digest-status.json`(candidates·picked)과 실린 건수, 클라우드 루틴은 수동 실행 로그로 확인(AC8·AC10).
- spec 대비 교차 확인은 /gate-review.

## 7. 리스크
- 제목 패턴의 오탐·미탐: 패치 번호가 붙은 보안 릴리스를 패치 범프로 오인하거나, 새 형태의 모음글을 놓칠 수 있다 → AC7 회귀 사례로 고정하고, 놓친 사례는 테스트에 추가.
- 규칙 사본 세 곳(repo `CLAUDE.md`, 로컬 SKILL.md, 클라우드 프롬프트)이 어긋날 위험 → AC10.
- 커밋 전 검사가 무인 실행을 막아 그날 다이제스트가 비는 경우 → 위반 항목을 빼고 다시 검사하도록 루틴에 적되, 조용히 통과시키지는 않는다.
- 상한 10건이 너무 빡빡해 중요한 글이 빠질 수 있다 → 1~2주 운영 후 #22·#23과 함께 재검토.
