# lesserpanda-note

Java · Spring Boot · AI 최신 뉴스와 직접 정리한 인사이트를 모아두는 정적 사이트.

👉 **https://lesserpanda-note.github.io/**

## 구조

```
index.html              화면 (바닐라 HTML/CSS/JS)
assets/style.css        스타일 (라이트/다크 자동)
assets/app.js           data/*.json 을 읽어 렌더
data/news.json          RSS 수집 결과 (배치가 생성)
data/notes.json         인사이트 렌더 결과 (배치가 생성)
notes/*.md              ← 인사이트를 여기에 작성
scripts/fetch_news.py   RSS → data/news.json
scripts/build_notes.py  notes/*.md → data/notes.json
.github/workflows/update.yml   6시간마다 도는 배치
```

## 인사이트 쓰는 법

`notes/`에 `YYYY-MM-DD-제목.md` 로 마크다운을 추가하고 main에 push하면 끝.
push 즉시 배치가 돌아 사이트에 반영된다.

```markdown
---
title: 가상 스레드 실전 정리
date: 2026-06-23
tags: java, concurrency
---
본문(마크다운)...
```

front matter(title·date·tags)는 생략 가능 — 파일명과 첫 `# 제목`에서 추론한다.

## 갱신은 어디서 도나 (배치)

정적 호스팅(GitHub Pages)이라 페이지가 스스로 갱신하지 못한다. 그래서 **GitHub
Actions**가 배치 역할을 한다:

1. cron(6시간) 또는 `notes/` push 시 워크플로 실행
2. `fetch_news.py` + `build_notes.py` 로 `data/*.json` 재생성
3. 변경이 있으면 main에 자동 커밋·push → GitHub Pages 재배포

GitHub Actions를 고른 이유: 레포와 같은 곳에 있어 추가 인프라·결제가 없고,
public 레포라 Actions 사용 시간이 무료다. 봇 커밋(`GITHUB_TOKEN`)은 워크플로를
재트리거하지 않아 무한 루프도 없다.

## 로컬에서 미리보기

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/fetch_news.py
.venv/bin/python scripts/build_notes.py
python3 -m http.server 8000      # http://localhost:8000
```
