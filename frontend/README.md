# DevHire Insight — 프론트엔드

지역 × 개발 스택 채용 지도 (Vite + React + TypeScript).

## 실행

```bash
npm install
npm run dev        # http://localhost:5173
```

FastAPI 백엔드가 `http://localhost:8000` 에서 떠 있어야 데이터가 채워진다.
백엔드 주소를 바꾸려면 `.env` 에 `VITE_API_BASE` 를 지정한다 (`.env.example` 참고).

```bash
npm run build      # 타입체크(tsc -b) + 프로덕션 번들
npm run preview    # 빌드 결과 미리보기
```

## 구조

```
src/
  data/korea-sido.json   시도 경계 GeoJSON (17개, DB 짧은 시도명으로 정규화됨)
  types.ts               /api 응답 스키마 타입
  api.ts                 API 클라이언트 (VITE_API_BASE)
  App.tsx                상태/조회 오케스트레이션
  components/
    KoreaMap.tsx         d3-geo 코로플레스 지도 (시도별 스킬 밀도 색칠 + 클릭/hover)
    SkillPicker.tsx      스킬 드롭다운 (전국 순위)
    CareerToggle.tsx     경력 밴드 (전체/주니어/시니어)
    RegionPanel.tsx      선택 지역 인기 스택 순위
    Legend.tsx           밀도 색상 범례
```

## 동작

1. 시작 시 `/api/skills` 로 드롭다운을 채우고 전국 1위 스킬을 기본 선택.
2. 스킬/경력 변경 → `/api/map` 재조회 → 시도별 밀도(%)로 지도 색칠.
3. 지도에서 시도 클릭 → `/api/region` 으로 그 지역 인기 스택 순위 표시.
   순위 항목을 클릭하면 그 스킬로 지도가 다시 칠해진다.

> 지도 밀도 = 해당 시도 전체 공고 대비 선택 스킬 공고 비율. `career_min` 이
> 없는 공고(약 38%)는 `전체` 밴드에만 집계된다 (마트 ETL 정책).
