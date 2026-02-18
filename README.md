# DevHire Insight

개발자 채용 공고를 수집·정제하고, **지역 × 스택** 인사이트로 시각화하는 데이터 파이프라인.

라이브: [dev-hire-insight.vercel.app](https://dev-hire-insight.vercel.app)

Scrapy로 원천을 적재하고, pandas ETL로 분석 마트(`mart_*`)를 만든 뒤 FastAPI는 마트만 읽습니다. 프론트는 Vite + React입니다. 수집 대상 URL은 코드에 없고 로컬 `.env`로만 주입합니다.

## 규모

기준일 <!--stat:as_of-->2026-09-16<!--/stat:as_of--> (마트 적재 <!--stat:built_at-->2026-09-16 09:09:37<!--/stat:built_at-->)

| 항목 | 값 |
|---|---|
| 수집 공고 | <!--stat:jobs_total-->73,189<!--/stat:jobs_total--> |
| 상세 파싱 성공 | <!--stat:details_ok-->71,217<!--/stat:details_ok--> |
| 파싱 성공률 | <!--stat:parse_rate-->97.3%<!--/stat:parse_rate--> |
| 분석 마트 공고 | <!--stat:mart_jobs-->70,037<!--/stat:mart_jobs--> |
| 집계 스킬 | <!--stat:skill_count-->2,288<!--/stat:skill_count--> |

성공률 = `job_details.backfill_status='OK'` / `jobs` 행 수.

## 왜 만들었나

“이 스택은 어느 지역에서 얼마나 뽑히나”, “함께 요구되는 기술은 뭔가”를 공고 데이터로 답하려고 만들었습니다. 화면은 지도·추이·연봉·연관 스택이고, 핵심은 그 숫자를 만드는 파이프라인입니다.

## 구조

```
채용 게시판  ──▶  Scrapy (목록 + 상세, 대상은 .env)
                    │
                    ▼
              MariaDB raw
              jobs / job_details / job_skills
                    │
                    ▼
              build_mart.py  (TRUNCATE 후 재적재)
                    │
                    ▼
              mart_*  ◀── FastAPI /api/*  ◀── React (Vercel)
```

- 수집: `devhire_crawler/` — 실패 상세는 `NO_DATA`로 남겨 `backfill_details.py`가 재시도
- ETL: `scripts/build_mart.py` — 지역×스킬×경력 밴드, 동시출현 Lift, 주별 추이, 연봉 사분위
- API: `fastapi_app/` — 공개 GET. raw 조인 없음
- UI: `frontend/` — Vite + React. 지도는 공고 수 log 스케일

실행·배포는 [RUN.md](RUN.md), [DEPLOY.md](DEPLOY.md).

## 설계에서 고른 것

**1. 헤드리스 렌더 대신 RSC 페이로드 파싱**  
상세가 Next.js App Router라 Playwright 렌더는 수만 건에서 병목이었습니다. HTML의 `__next_f` 블록을 HTTP로 파싱하고, 파서(`detail_parser.py`)는 수집과 백필이 공유합니다.

**2. 본문 해시 3단 스킵**  
날짜·잔여일 같은 노이즈를 지운 뒤 SHA-256을 뜹니다. (1) 해시가 같으면 UPDATE 없음 (2) 필드 diff가 없어도 없음 (3) 바뀐 게 description/skills뿐이고 스킬 집합이 같으면 오탐으로 보고 스킵합니다.

**3. 동시출현은 빈도가 아니라 Lift**  
`Lift = P(B|A) / P(B)`. 빈도(%)만 쓰면 git/aws가 도배하고, Lift만 쓰면 희소 스킬이 1등이 됩니다. 관련 스킬 최소 공고 수 50(`MIN_REL_BASE`)과 동시출현 최소 5건으로 두 편향을 같이 줄입니다.

**4. ‘한글 = 인성’을 버렸다**  
전수 점검에서 자바/리눅스/딥러닝/백엔드가 인성으로 떨어지고, 스트레스관리가 기술로 남았습니다. 인성 키워드는 유한 블랙리스트로 두고, 목록 밖은 기술로 봅니다.

## 한계

- 수집 소스는 설정한 공개 채용 게시판 하나입니다. 지금 열린 자리만 보는 서비스가 아니고, 마감 공고도 트렌드용으로 마트에 넣습니다.
- 요구연차(`career_min`)가 없는 공고는 `junior`/`senior` 밴드에 안 들어갑니다. 연봉은 연봉형 하한만 쓰고, 표본이 적은 스킬은 랭킹에서 뺍니다.
- 공개 API에 인증·레이트리밋은 없습니다.

## 로컬 실행

```powershell
copy .env.example .env   # 값 채우기 (DB, TARGET_*, CORS_ORIGINS)
python scripts/run_crawler.py         # 수집 (필요할 때만)
python scripts/build_mart.py          # 마트 재생성
cd fastapi_app; python -m uvicorn app.main:app --reload --port 8000
cd frontend; npm install; npm run dev   # http://localhost:5173
```

자세한 순서는 [RUN.md](RUN.md). `.env`는 커밋하지 않습니다.
