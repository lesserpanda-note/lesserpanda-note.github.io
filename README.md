# lesserpanda-note

Java · Spring Boot · AI 최신 뉴스를 모아 보여주는 정적 사이트.

👉 **https://lesserpanda-note.github.io/**

## 구조

```
index.html                            화면 (바닐라 HTML/CSS/JS)
assets/style.css                      스타일 (라이트/다크 자동)
assets/app.js                         data/*.json 을 읽어 렌더 (뉴스·다이제스트·아카이브·소스) + 검색
data/news.json                        RSS 수집 결과 (배치가 생성)
data/digest.json                      오늘의 데일리 다이제스트
data/archive.json                     지난 다이제스트 보관
data/digest-status.json               다이제스트 루틴 실행 heartbeat (마지막 실행 시각)
data/sources.json                     카테고리별 참조 소스 (FEEDS 에서 fetch_news.py 가 생성)
scripts/fetch_news.py                 RSS → data/news.json + data/sources.json (피드 병렬 수집)
.github/workflows/deploy.yml          6시간마다 뉴스 재생성 + 배포
.github/workflows/promote-digest.yml  다이제스트 루틴 산출물을 main 으로 승격
```

## 검색 · 소스 페이지

- **뉴스 검색**: 카테고리 필터와 함께 제목·요약·출처를 즉시 필터링.
- **아카이브 검색**: 검색하면 매칭된 날짜 전체가 아니라 **개별 기사만** 관련도 순으로 나온다.
  키워드+동의어 방식으로, 다국어 동의어 확장 덕에 한글 `예측` 질의가 영어 `prediction`·`forecast` 기사까지
  매칭된다. 사전 기반이라 즉시 동작하고 다운로드가 없다. (브라우저 내 임베딩 기반 시맨틱 검색도 시도했으나,
  모델이 무거워 기기에 따라 페이지가 버벅여 걷어냈다.)
- **카테고리별 소스**: `#sources` 섹션이 `data/sources.json`(FEEDS 에서 생성)을 읽어 각 카테고리가
  어떤 매체(RSS)를 참조하는지 보여준다. FEEDS 를 고치면 소스 목록도 자동으로 따라간다.

## 뉴스 출처

`scripts/fetch_news.py` 의 `FEEDS` 에서 관리한다.

- **Java** (Kotlin·JVM 포함): Inside Java, InfoQ Java, Foojay, Kotlin
- **Spring**: Spring Blog (Spring Boot 릴리스 포함)
- **AI** (모델·LLM 트렌드 포함): Google AI, Hugging Face, MIT Tech Review, InfoQ AI/ML, Anthropic, Ollama, Ahead of AI, Import AI, Hacker News (Grok / Llama), Transformers (라이브러리 릴리스)
- **Agents**: Simon Willison, Latent Space, Eugene Yan, Hacker News (Claude Code / 에이전트 / 컨텍스트 엔지니어링 / MCP), 프레임워크 릴리스 (MCP servers · LangGraph · Pydantic AI · OpenAI Agents SDK · LlamaIndex · CrewAI · Agent Framework)
- **Architecture**: InfoQ Architecture, Martin Fowler
- **Python**: Real Python, Python Insider, Python Speed, PyPI Blog (공급망·보안)
- **DataScience**: ML Mastery, KDnuggets, Analytics Vidhya, Towards Data Science, Statistical Modeling, NumPy·pandas (라이브러리 릴리스) — 실무 예측모델(scikit-learn·XGBoost·표 데이터·특성공학·통계기법). LLM·agent·RAG 글은 제목 기준으로 AI·Agents 에 자동 재분류(`reclassify`)한다.

피드를 추가/제거하려면 `FEEDS` 리스트에 `(url, 출처명, 카테고리)` 항목을 넣으면 된다. 카테고리는 페이지 필터·그룹을 결정한다. DataScience 로 들어온 항목 중 제목이 LLM/agent/RAG 류이면 `reclassify` 가 AI·Agents 로 옮긴다(피드 단위 분류의 한계를 글 단위로 보정; 키워드 휴리스틱).

## 갱신은 어디서 도나 (배치)

정적 호스팅(GitHub Pages)이라 페이지가 스스로 갱신하지 못한다. 그래서 **GitHub
Actions**가 배치 역할을 한다. Pages Source는 "GitHub Actions"이고,
`deploy.yml` 한 워크플로가 생성과 배포를 같이 한다:

1. cron(6시간) · main push · 수동 실행 시 워크플로 실행
2. `fetch_news.py` 로 `data/news.json` 재생성
3. 사이트 전체를 아티팩트로 묶어 `deploy-pages` 로 그대로 배포

매 실행이 곧 배포라 데이터를 main에 커밋백할 필요가 없다 — 봇 커밋도, 무한
루프도, 레거시 Jekyll 빌드 실패도 없다. 레포에 커밋된 `data/news.json`은 시드일
뿐이고, 실제 배포본은 매번 새로 생성된다. public 레포라 Actions는 무료다.

## 데일리 다이제스트

매일 09:00 KST에 클라우드 루틴이 최근 뉴스에서 카테고리별 하이라이트를 골라
`data/digest.json`(오늘) · `data/archive.json`(보관) · `data/digest-status.json`
(실행 heartbeat)을 만든다. 이 루틴은 예약 실행 시 main에 직접 push할 자격이 없어
결과를 매번 새 `claude/*` 브랜치에 남기는데, GitHub Pages는 main만 배포한다. 그래서
`promote-digest.yml` 이 그 브랜치의 산출물을 main으로 승격하고 배포를 트리거한다.
heartbeat는 항상 승격되므로 루틴이 멈추면 사이트 상단의 "마지막 실행 시각"이
오래된 채로 남아 바로 눈에 띈다.

## 로컬에서 미리보기

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/fetch_news.py
python3 -m http.server 8000      # http://localhost:8000
```
