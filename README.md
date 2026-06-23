# lesserpanda-note

Java · Spring Boot · AI 최신 뉴스를 모아 보여주는 정적 사이트.

👉 **https://lesserpanda-note.github.io/**

## 구조

```
index.html              화면 (바닐라 HTML/CSS/JS)
assets/style.css        스타일 (라이트/다크 자동)
assets/app.js           data/news.json 을 읽어 렌더
data/news.json          RSS 수집 결과 (배치가 생성)
scripts/fetch_news.py   RSS → data/news.json
.github/workflows/deploy.yml   6시간마다 데이터 재생성 + 배포
```

## 뉴스 출처

`scripts/fetch_news.py` 의 `FEEDS` 에서 관리한다.

- **Java**: Inside Java, InfoQ Java
- **Spring**: Spring Blog (Spring Boot 릴리스 포함)
- **AI**: Google AI, Hugging Face, MIT Tech Review, OpenAI
- **Agents**: Simon Willison, Latent Space, Hacker News (Claude Code / 에이전트·컨텍스트 엔지니어링)

피드를 추가/제거하려면 `FEEDS` 리스트에 `(url, 출처명, 카테고리)` 항목을 넣으면 된다.

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

## 로컬에서 미리보기

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/fetch_news.py
python3 -m http.server 8000      # http://localhost:8000
```
