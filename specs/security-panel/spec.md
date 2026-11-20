# Spec: 보안 공지 패널            (specs/security-panel/spec.md)

## 1. 의도
- 무엇을: Java·Spring·Node·Go·Python·Rust 공식 사이트가 내는 보안 공지를 한곳에 모아 보여 주는 별도 패널을 사이트에 추가합니다.
- 왜: 다이제스트는 카테고리당 최대 5건만 고르고 오전 실행 시점에 보인 것만 다룹니다. 2026-11-19에 Spring 공지 50건 가까이가 실행 직후에 올라와 통째로 빠졌고, Java4Shell은 수집돼 있었는데도 선별에서 빠졌습니다. 보안 공지는 고르는 대상이 아니라 전부 확인해야 하는 목록입니다.
- 사용자가 할 수 있게 되는 것: 생태계·심각도별로 최근 공지를 훑고, 원문 공지로 바로 갑니다.

## 2. 인수조건 (AC)
- [ ] AC1: `scripts/fetch_news.py` 실행 후 `data/security.json`이 생기고, 각 항목은 `{ecosystem, source, title, link, published, severity, ids}` 형태입니다. `severity`는 CRITICAL/HIGH/MEDIUM/LOW 또는 null, `ids`는 CVE·GO-ID 목록입니다.
- [ ] AC2: 아래 6개 출처에서 각각 1건 이상 수집됩니다(실제 실행으로 확인).
  | 생태계 | 출처 | 방식 |
  |---|---|---|
  | Java | OpenJDK Vulnerability Advisories (`openjdk.org/groups/vulnerability/advisories/`) | HTML 목록 → 날짜별 공지 1건, 본문 위험 매트릭스에서 CVE·최고 CVSS |
  | Java | Oracle Security Alerts RSS | RSS, 제목 그대로 |
  | Spring | `spring.io/security.atom` | Atom, 제목의 `- HIGH -` 등에서 심각도 |
  | Node | `nodejs.org/en/feed/vulnerability.xml` | RSS |
  | Go | `vuln.go.dev` (stdlib·toolchain 모듈만) | 인덱스 → 최근 항목의 ID JSON에서 요약·CVE |
  | Python | `security-announce@python.org` 메일링 리스트 피드 | RSS, 제목의 CVE |
  | Rust | GitHub 보안 공지 API (`rust-lang/rust`, `rust-lang/cargo`) | JSON, 심각도 포함 |
- [ ] AC3: 한 출처가 실패(타임아웃·4xx·파싱 오류)해도 다른 출처와 `news.json` 수집은 계속되고, 기존 `security.json` 항목은 남습니다.
- [ ] AC4: `security.json`은 링크 기준으로 누적되고 365일이 지난 항목만 지워집니다(news.json의 30일과 별개).
- [ ] AC5: 사이트에 "🛡️ 보안 공지" 패널과 사이드바 링크가 생기고, 최근 90일 공지가 최신순으로 나옵니다. 각 줄은 생태계 배지, 심각도 배지(있을 때), 제목(원문 링크), 출처, 날짜입니다.
- [ ] AC6: 생태계 필터 칩(전체/Java/Spring/Node/Go/Python/Rust, 건수 표시)과 "Critical·High만" 토글이 동작합니다.
- [ ] AC7: GitHub Actions가 `data/security.json` 변경도 커밋하고, 그 커밋이 배포를 다시 트리거하지 않습니다.
- [ ] AC8: 라이트·다크 모드와 720px 이하 폭에서 깨지지 않고, 콘솔 오류가 없습니다.

## 3. 범위 & 비목표
- 포함: 수집 스크립트 확장, `data/security.json`, 패널 UI, 워크플로 커밋 대상 추가, README의 데이터 파일 설명.
- 하지 말 것:
  - 다이제스트 선별 규칙·루틴 프롬프트 변경(보안 공지가 다이제스트에 들어가는 방식은 그대로)
  - 공지 본문 번역·요약 생성(LLM 없음, 제목과 원문 링크만)
  - GitHub Advisory DB·rustsec 같은 생태계 전체 패키지 DB(관계없는 라이브러리 공지가 대부분을 차지함)
  - Kotlin·TypeScript(별도 공식 보안 피드가 없음)
  - 알림(메일·푸시)
  - 기존 news 패널·검색 리팩터

## 4. 제약
- 정적 사이트(GitHub Pages), 바닐라 JS, 빌드 도구 없음. Python 3.12 + feedparser(기존 의존성만).
- 기존 컨벤션: `fetch_feed`의 타임아웃·예외 처리 방식, `escapeHTML`·`el` 헬퍼, `.badge`·`.filter` 스타일, 주석은 영어.

## 5. 파일/모듈 계약
- `scripts/fetch_news.py`: `SECURITY_SOURCES`와 출처별 파서(순수 함수: 원문 → 항목 목록), 누적·보존 로직, `data/security.json` 쓰기. 네트워크는 기존 `urlopen(timeout)` 패턴.
- `scripts/test_security.py`: 파서 단위 테스트(저장한 샘플 문자열 입력 → 항목), 심각도·CVE 추출, 보존 기간.
- `index.html`: 패널 섹션과 사이드바 링크.
- `assets/app.js`: `security.json` 로드, 필터·토글, 렌더.
- `assets/style.css`: 심각도 배지 색, 패널 목록 스타일.
- `.github/workflows/deploy.yml`: persist 단계와 `paths-ignore`에 `data/security.json`.
- `README.md`: 데이터 파일 설명에 한 줄.

## 6. 자기검증 방법
- 순수 로직: `python3 scripts/test_security.py`, `python3 scripts/test_reclassify.py` 통과.
- 경계: 로컬에서 `python3 scripts/fetch_news.py` 실제 실행 → 출처별 건수 출력, 한 URL을 일부러 틀리게 해서 AC3 확인.
- UI: 로컬 미리보기에서 필터·토글·다크 모드·모바일 폭 확인, 콘솔 오류 0, `node --check assets/app.js`.
- 배포 후 라이브 `data/security.json`과 패널 확인.

## 구현 중 변경
- 심각도 토글: "Critical·High만"은 등급이 없는 Node·Go·Oracle 공지까지 숨겨서, Medium·Low로 등급이 매겨진 것만 숨기는 "Medium·Low 숨기기"로 바꿨습니다.
- Rust 출처: 블로그 피드는 최근 10개 글만 담고 그중 보안 공지가 없어(2026-11-20 확인), 프로젝트가 std·Cargo 공지를 올리는 GitHub 보안 공지 API로 바꿨습니다. Actions에서는 워크플로 토큰으로 호출해 IP당 호출 한도를 피합니다.

## 7. 리스크
- OpenJDK 공지 페이지는 HTML 스크레이핑이라 마크업이 바뀌면 깨집니다. 실패 시 그 출처만 0건이 되도록 격리합니다.
- Oracle RSS는 Java 외 Oracle 제품 전체의 월간 패치 공지입니다. Java SE 해당 여부는 제목으로 알 수 없어 그대로 싣습니다.
- vuln.go.dev는 항목마다 JSON을 따로 받으므로, 최근 90일 항목만 받도록 제한합니다.
