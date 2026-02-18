# DevHire Insight 실행 가이드

전제: 모든 명령은 프로젝트 루트 기준. 루트 `.env.example` 을 복사해 `.env` 를 채운다.

---

## 0. 데이터 수집 (크롤)

```powershell
# 프로젝트 루트에서
python scripts/run_crawler.py
```

- 공개 채용 게시판 공고를 수집하면서 **`jobs` + `job_details` + `job_skills` 를 한 번에 적재**한다.
  (상세 페이지 파싱까지 크롤 시점에 끝나므로 별도 백필이 필요 없다.)
- 수집이 끝나면 곧바로 `1. 마트 재실행` 을 돌려야 API/프론트에 반영된다.

### 백필은 "보수 도구" — 평상시엔 안 돌림

크롤 때 실패(SSL/타임아웃 등)했거나 파싱 규칙이 바뀌었을 때만 사용한다.

```powershell
python scripts/backfill_details.py --retry-errors      # 실패분(ERROR/NO_DATA) 재시도
python scripts/backfill_details.py --refix-region       # 재크롤 없이 지역(sido/sigungu) 재산출
python scripts/backfill_details.py --reclassify-skills  # 재크롤 없이 기술/인성 라벨 재분류
```

### 검증 (선택)

```powershell
python scripts/check_recent_details.py --min 15   # 최근 15분 내 크롤러가 쓴 job_details 점검
python scripts/diag_counts.py                     # jobs→job_details→마트 흐름/누수 진단
```

---

## 1. 마트 재실행 (ETL)

원천(raw) 데이터를 더 수집했으면 **이걸 돌려야만** API/프론트에 반영된다.
API는 `mart_*` 테이블만 읽기 때문.

```powershell
# 프로젝트 루트에서
python scripts/build_mart.py
```

- `.env` 는 스크립트가 내부에서 알아서 로드함 (직접 건드릴 필요 없음).
- TRUNCATE + 재적재 방식이라 **몇 번을 돌려도 결과 동일**(멱등).
- 동작: `job_details`(backfill OK, 시도 있음) + `job_skills`(is_tech=1) 집계
  → `mart_region_skill / mart_skill / mart_region_total / mart_meta` 재생성.

### 옵션

```powershell
python scripts/build_mart.py --create-schema     # 최초 1회, 마트 테이블 DDL만 만들고 종료
python scripts/build_mart.py --min-count 10      # 스킬 최소 공고수 임계 조정 (기본 5, 롱테일 제거)
```

### 성공 확인

브라우저나 curl로 `built_at` 이 오늘 날짜로 바뀌었는지 확인:

```
http://localhost:8000/api/meta
```

`built_at` 이 실행 시각으로, `unique_jobs` 가 새 수집분만큼 늘었으면 성공.

> ⚠️ 이 DB는 Lightsail이라 로컬 셸에서 직접 붙으면 종종 타임아웃 남.
> 실행에 시간이 좀 걸릴 수 있음.

---

## 2. 백엔드 실행 (FastAPI, 포트 8000)

```powershell
# 프로젝트 루트에서
cd fastapi_app
python -m uvicorn app.main:app --reload --port 8000
```

- 모듈 경로는 반드시 **`app.main:app`**, 실행 위치는 **`fastapi_app` 폴더 안**이어야 함.
- `--reload` = 코드 수정 시 자동 재시작 (개발용). 그냥 띄우기만 하면 빼도 됨.

### 최초 1회 의존성 설치

```powershell
pip install -r fastapi_app/requirements.txt
```

(fastapi, uvicorn, sqlalchemy, pymysql, python-dotenv, pandas)

### 확인

```
http://localhost:8000/health        → {"status":"ok"}
http://localhost:8000/docs          → Swagger UI (엔드포인트 테스트)
```

> ⚠️ **포트 8000 이미 사용 중(에러 10048)** 이 뜨면 이전에 띄운 백엔드가 아직 살아있는 것.
> 그 경우 새로 띄울 필요 없음. 굳이 재시작하려면 8000 잡고 있는 프로세스부터 종료:
>
> ```powershell
> Get-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess
> Stop-Process -Id <PID>
> ```

---

## 3. 프론트엔드 실행 (Vite + React, 포트 5173)

```powershell
# 프로젝트 루트에서
cd frontend
npm install       # 최초 1회 (또는 의존성 바뀌었을 때)
npm run dev       # http://localhost:5173
```

- 백엔드(8000)가 떠 있어야 데이터가 채워짐. 지도는 떠도 값이 비면 백엔드부터 확인.
- API 주소를 바꾸려면 `frontend/.env` 에 `VITE_API_BASE=http://localhost:8000`
  (`.env.example` 참고). 안 만들면 기본값 `localhost:8000` 사용.

### 기타 스크립트

```powershell
npm run build     # 타입체크(tsc -b) + 프로덕션 번들 → dist/
npm run preview   # 빌드 결과 미리보기
npm run lint      # oxlint
```

---

## 전체 기동 순서 (한 번에)

1. **수집** → `python scripts/run_crawler.py` (새 공고 모을 때만. jobs+job_details+job_skills 동시)
2. **마트 최신화** → `python scripts/build_mart.py` (수집했을 때만)
3. **백엔드** → `fastapi_app` 에서 `python -m uvicorn app.main:app --reload --port 8000` (이미 떠 있으면 생략)
4. **프론트** → `frontend` 에서 `npm run dev`
5. 브라우저 → **http://localhost:5173**

> 데이터 갱신만 할 거면 1→2 만, 화면만 볼 거면 3→4 만 돌리면 된다.
