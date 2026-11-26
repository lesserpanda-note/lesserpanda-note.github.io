# Tasks: 다이제스트 선별 결정론화와 하루 상한           (specs/18-digest-selection/tasks.md)

> spec: `specs/18-digest-selection/spec.md` (2026-11-27 master 승인). 이슈 #18.
> 계층: pure = 판정 함수 / edge = news.json·digest.json을 읽는 CLI / glue = 두 루틴 프롬프트·CLAUDE.md 배선.
> 범례: ∥ = 병렬 가능(서브에이전트 위임 후보)

## 작업 환경 주의
- 다이제스트 루틴이 **이 repo 작업 디렉터리의 main**에서 09:39 KST에 돈다. 구현은 `git worktree`로 `feature/18-digest-selection`을 따로 체크아웃해서 하고, 원래 디렉터리는 main에 둔다.
- 테스트는 기존 관례대로 pytest 없이 plain assert: `python scripts/test_<name>.py`.
- 로컬 SKILL.md(`~/.claude/scheduled-tasks/lesserpanda-digest-fallback/SKILL.md`)와 클라우드 루틴 프롬프트(RemoteTrigger)는 repo 밖이라 PR에 안 들어간다 — M3에서 PR 머지 **후** 갱신한다(머지 전 갱신하면 루틴이 main에 없는 스크립트를 부른다).

## 설계 결정 (spec의 "어떻게")
- 새 파일 `scripts/select_digest.py` 하나. 순수 함수 + 얇은 CLI.
  - `exclude_reason(item) -> str | None` — AC3~AC6. `item`은 news.json 항목(dict: title·source·category·summary …).
  - `tier(item) -> int` — 0 보안 공지(`source` ∈ {Spring Security, Node.js Security}, 제목에 `CVE-`, 또는 제목에 `Security Release(s)`), 1 메이저 릴리스(릴리스 제목의 `x.0`·`x.0.0` 정식판; LTS 전환은 제목으로 구분되지 않아 2), 2 나머지.
  - `check(highlights, candidates) -> list[str]` — AC1(전체 ≤10, 카테고리 ≤3), 제외 대상 포함 여부, AC2(제외되지 않은 후보가 상한을 넘는 카테고리에서 더 높은 tier 후보를 버리고 낮은 tier를 실었는지 — 실린 건수가 상한보다 적어도 적용). 위반 메시지 목록, 비면 통과.
  - CLI: `python scripts/select_digest.py candidates` — 현재 SKILL.md STEP 2의 후보 조건(마감 `updated`, 7일, 보안 면제, 기존 링크 제외)을 **그대로** 옮기고 제외 규칙을 적용해 카테고리·tier별 JSON 출력(제외된 항목과 사유도 함께). `python scripts/select_digest.py check [--date YYYY-MM-DD]` — 인자가 없으면 `data/digest.json`, `--date`면 `archive.json`의 그 날짜 항목을 검사, 위반 시 위반 목록(항목 링크·사유)을 출력하고 exit 1.
  - 마감 기준 변경(#19)은 하지 않는다. 다만 후보 조건이 이 스크립트 한 곳으로 모이므로 #19는 이후 여기 한 줄 수정이 된다.
- 상수(10, 3, 라이브러리 릴리스 피드 목록)는 스크립트 상단에 두고 `CLAUDE.md`는 수치와 "판정은 `scripts/select_digest.py`"를 적는다.
- `fetch_news.py`·`news.json` 형식·`deploy.yml`은 건드리지 않는다.

## 검증 계약 (AC → 이걸로 증명)
| AC   | 증명 테스트 / 검증 | 계층 |
|------|--------------------|------|
| AC1  | `scripts/test_select_digest.py`: 11건·카테고리 4건 하이라이트에 `check`가 각각 위반 보고, 10건/3건은 통과. 여러 날 보충은 `check --date`로 archive 날짜분을 검사(M2에서 archive 11-24 등 실제 항목으로 관찰, M3에서 SKILL.md에 날마다 호출 명시) | pure |
| AC2  | 같은 테스트: 제외되지 않은 후보가 3건을 넘는 카테고리에서 tier 0 후보를 버리고 tier 2를 실으면 위반(실린 건수가 3건 미만이어도), tier 0을 먼저 다 실으면 통과, 후보가 3건 이내인 카테고리는 선택에 맡김. `tier()` 사례: Spring Security·Node.js Security·`CVE-` 제목·`Security Releases` 제목 → 0, `x.0`·`x.0.0` 정식 릴리스 → 1, LTS 라인 `x.y.0`·일반 글 → 2 | pure |
| AC3  | 같은 테스트: Real Python `Quiz: …` 실제 제목 → 제외 사유 `quiz` | pure |
| AC4  | 같은 테스트: `[AINews] Gemini 4 Neon …` → 제외, `This Week in Spring …` → 제외, InfoQ `Java News Roundup …` → 남음, Latent Space 비-AINews 글 → 남음 | pure |
| AC5  | 같은 테스트: CrewAI·MCP servers 등 `x.y.z`(z≥1) → 제외, 같은 피드라도 요약에 `CVE`/`security`/`vulnerability` → 남음, `x.y.0`·`x.0.0` → 남음 | pure |
| AC6  | 같은 테스트: Node.js Blog alpha·point(`x.y.z`, z≥1) 릴리스 → 제외, Node 새 메이저 라인·`x.y.0`(LTS 전환 포함)·security release → 남음, 릴리스 제목에 alpha/beta/rc/milestone 표시 → 제외(정식판과 함께 나온 제목은 남음), 버전을 언급만 한 글 → 남음. nightly·canary는 AC7 예외대로 미고정 | pure |
| AC7  | 테스트 사례가 모두 현재 `data/news.json`의 실제 제목에서 왔음(테스트 파일 주석에 출처 날짜). Hibernate `5.0.0.Final`·Spring 보안 공지 → 남음. 예외(M1 게이트 합의): 출처가 news.json이 아닌 실제 제목 2건(Node.js Security는 `data/security.json`, Spring Batch `6.1.0-RC1 and 6.0.6`은 `data/archive.json` 10-23), 그리고 30일 창에 실제 제목이 없는 분기는 그 피드의 제목 형식으로 쓴 "shape" 사례로 고정(Node 메이저, 라이브러리 `x.0.0`, Spring `-M1`, 요약의 `vulnerability`로 남는 패치). 제목 형식을 본 적이 없는 분기는 미고정 — nightly·canary 릴리스, 제목에 보안 표현이 든 라이브러리 패치. 실제 제목이 들어오면 사례 추가. `check()` 사례는 문구와 무관한 상한·tier 순서 검사라 합성 제목 | pure |
| AC8  | (a) `python scripts/select_digest.py check`(와 `--date`)를 archive의 11-26 원본(18건, `[AINews]` 포함)으로 만든 임시 digest에 돌려 exit 1과 위반 목록 관찰, 현재 `data/digest.json`(17건)에는 상한 위반만 보고됨을 관찰 (b) 로컬·클라우드 루틴이 커밋 전에 `check`를 부르고, 실패하면 위반 항목을 빼고 다시 검사하며 뺀 항목·사유를 `digest-status.json`의 `dropped`에 기록 — 위반한 채로는 커밋하지 않음. 프롬프트 diff로 확인 + 다음 09:39 실행 관찰 | edge + glue |
| AC9  | 두 루틴 프롬프트 STEP 3: 스크립트 출력의 tier 순서 안에서 LLM이 고르고 요약을 쓴다는 문장, 결정론 단계가 제외·tier·상한만 한다는 문장 — diff로 확인 | glue |
| AC10 | `CLAUDE.md` Item Selection Rules, SKILL.md STEP 3, 클라우드 프롬프트에 10건·3건·제외 규칙·스크립트 경로가 같은 표현으로 있음 — 세 곳 grep 대조 | glue |

## 마일스톤
현재: M1 게이트 리뷰 3회차 수정 완료(2026-11-27) — spec 축 직전 지적 해소, 코드 기준 위반 없음. M1 게이트 사람 확인 대기. 열린 질문: 같은 CVE를 두 출처가 다룬 날·본문을 못 읽은 tier 0 후보를 AC2가 어떻게 다룰지(M2 CLI 설계에 영향).
다음: M1 게이트(/gate-review → master 확인) 후 M2 — `candidates`·`check` CLI

### M1: 판정 함수와 회귀 테스트 (`scripts/select_digest.py` 순수부, `scripts/test_select_digest.py`)
- 다룸: `exclude_reason`·`tier`·`check`와 실제 제목 기반 테스트 · 관련 AC: AC1~AC7
- 병렬: ∥ 실제 제목 사례 수집(news.json에서 AC3~AC6별 제외·유지 후보 뽑기)과 함수 구현
- 시작 커밋: 6780dfc
- [ ] 게이트 M1: `python scripts/test_select_digest.py` green + 기존 `test_reclassify.py`·`test_retry.py`·`test_security.py` green → /gate-review → 사람 확인
- 수정 기록:
  - `1 | Opus 5.5 | AC2 검사를 spec Given(후보가 상한 초과)으로 맞춤·테스트 docstring 출처 정정·tier 0 정의 문장 갱신·check 루프 풀어쓰기 | spec 해석 판단 3건(LTS·point, 사례 없는 칸, -M) master 확인 대기`
  - `2 | Opus 5.5 | master 결정 반영: spec AC6에 milestone·Node point 정의 추가, shape 사례 4건(라이브러리 x.0.0 제외·tier, vulnerability 패치, -M1), AC7 예외 기록 | 재리뷰 대기`
  - `3 | Opus 5.5 | 재리뷰 지적 반영: 검증 계약 AC2·AC6·AC7 행을 게이트 결정과 맞춤, 제목 보안 표현 패치 칸을 미고정으로 기록 | 해소(문서만 변경, 아래 확인)`

### M2: CLI (`candidates`·`check`)와 실데이터 확인
- 다룸: news.json·digest.json·archive.json을 읽는 두 하위 명령, README `scripts/` 표에 한 줄 · 관련 AC: AC8(a), AC1
- 시작 커밋: —
- [ ] 게이트 M2: 현재 데이터로 `candidates` 출력(제외 사유 포함)과 11-26 원본 `check` exit 1을 관찰 + M1 테스트 green → PR 열기(머지는 M3에서 `CLAUDE.md`까지 넣은 뒤) → /gate-review → 사람 확인
- 수정 기록:

### M3: 배선 (CLAUDE.md는 PR 안, 두 루틴 프롬프트는 머지 후)
- 다룸: `CLAUDE.md` Item Selection Rules 갱신(M2와 같은 PR) → 머지(`Closes #18`), 머지 직후 로컬 SKILL.md STEP 2·3·5/6과 클라우드 프롬프트(RemoteTrigger update) 갱신 — 후보는 `candidates` 출력으로, 커밋 전 `check` 필수(실패 시 위반 항목 빼고 재검사, 뺀 것은 `digest-status.json` `dropped`에 기록), 여러 날 보충 시 날마다 `check --date` · 관련 AC: AC8(b), AC9, AC10
- 시작 커밋: —
- [ ] 게이트 M3: 세 곳 grep 대조(AC10) + 클라우드 프롬프트 get으로 반영 확인 + 다음 09:39 로컬 실행의 picked ≤ 10, `check` 통과 기록 관찰 → /gate-review → 사람 확인
- 수정 기록:

## 완료 정의 (DoD)
- 전체 AC 증명 green · /verify 통과 · README·CLAUDE.md 갱신 · /gate-review · /code-review · 이슈 #18 닫기
