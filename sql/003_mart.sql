-- =====================================================================
-- 003_mart.sql  —  분석 전용 요약(mart) 계층
--
-- raw(job_details/job_skills)를 매번 조인하지 않도록 하루 1회 배치로
-- 미리 집계해 두는 작은 테이블들. FastAPI 는 이 테이블만 읽는다.
-- 재생성은 build_mart.py 가 TRUNCATE 후 다시 채운다 (멱등).
-- =====================================================================

-- 지역 × 스킬 × 경력밴드 공고 수
-- sigungu IS NULL 행 = 해당 시도 전체 합계 (지도 첫 화면용)
CREATE TABLE IF NOT EXISTS mart_region_skill (
    sido         VARCHAR(20)   NOT NULL,
    sigungu      VARCHAR(40)   NULL COMMENT 'NULL = 시도 전체 합계',
    skill_norm   VARCHAR(100)  NOT NULL,
    career_band  VARCHAR(10)   NOT NULL COMMENT 'all / junior(0-2) / senior(3+)',
    cnt          INT           NOT NULL,

    KEY idx_skill_band (skill_norm, career_band),
    KEY idx_sido       (sido, career_band),
    KEY idx_lookup     (skill_norm, career_band, sido)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;


-- 스킬 카탈로그 (드롭다운 + 전체 순위). career_band='all' 전국 합계 기준.
CREATE TABLE IF NOT EXISTS mart_skill (
    skill_norm   VARCHAR(100)  NOT NULL,
    total_cnt    INT           NOT NULL,
    rank_no      INT           NOT NULL,
    PRIMARY KEY (skill_norm),
    KEY idx_rank (rank_no)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;


-- 시도별 전체 공고 수 (스킬 무관 — 지도 기본 레이어/분모용)
CREATE TABLE IF NOT EXISTS mart_region_total (
    sido         VARCHAR(20)   NOT NULL,
    sigungu      VARCHAR(40)   NULL,
    career_band  VARCHAR(10)   NOT NULL,
    cnt          INT           NOT NULL,
    KEY idx_sido (sido, career_band)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;


-- 스킬 동시출현 (연관 스택). "skill 공고 중 related_skill 도 요구한 비율".
-- 방향성 있음: (python→aws) 와 (aws→python) 은 pct 가 다르다.
-- v1 은 전국 기준. career_band 별로 따로 집계.
CREATE TABLE IF NOT EXISTS mart_skill_cooccur (
    skill          VARCHAR(100) NOT NULL,
    related_skill  VARCHAR(100) NOT NULL,
    career_band    VARCHAR(10)  NOT NULL COMMENT 'all / junior / senior',
    co_cnt         INT          NOT NULL COMMENT '두 스킬 모두 요구한 공고 수',
    pct            DECIMAL(5,1) NOT NULL COMMENT 'skill 공고 중 related_skill 비율(%)',
    lift           DECIMAL(8,2) NOT NULL COMMENT 'P(rel|skill)/P(rel). 1=독립, >1=양의연관(범용스킬 편향보정)',
    KEY idx_lookup (skill, career_band, lift)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;


-- 공고 게시 추이 (시계열). 게시일(posted_at) 기준 주별 공고 수.
-- period = 그 주의 월요일(주 시작일). skill_norm 별 + career_band 별.
-- 전체 합계는 별도 mart_trend_total 에 둔다(스킬 무관 분모/개요 라인).
CREATE TABLE IF NOT EXISTS mart_trend (
    skill_norm   VARCHAR(100)  NOT NULL,
    period       DATE          NOT NULL COMMENT '주 시작일(월요일)',
    career_band  VARCHAR(10)   NOT NULL COMMENT 'all / junior / senior',
    cnt          INT           NOT NULL COMMENT '해당 주 게시 공고 수',
    KEY idx_lookup (skill_norm, career_band, period)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;


-- 전체 공고 게시 추이 (스킬 무관 — 개요 라인/분모용)
CREATE TABLE IF NOT EXISTS mart_trend_total (
    period       DATE          NOT NULL COMMENT '주 시작일(월요일)',
    career_band  VARCHAR(10)   NOT NULL,
    cnt          INT           NOT NULL,
    KEY idx_band (career_band, period)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;


-- 스킬별 급여/경력 통계 (연봉·요구경력 분석 뷰).
-- career_band 별로 따로 집계: all / junior(0-2) / senior(3+).
--   * 경력: career_min(요구 연차) 표본 기반 평균 + 3구간 분포(주니어0-2/미들3-5/시니어6+).
--   * 급여: 연봉(ANNUALLY_SALARY)·placeholder 제외 pay_from(하한, 만원) 표본의 사분위.
--           pay_to 는 +1 관례값 오염이 있어 신뢰 낮음 → 하한(pay_from)만 사용.
--   * 표본 부족(pay_n<10) 이면 급여 통계는 NULL. API 랭킹은 별도 최소표본으로 한 번 더 거른다.
CREATE TABLE IF NOT EXISTS mart_skill_stat (
    skill_norm   VARCHAR(100)  NOT NULL,
    career_band  VARCHAR(10)   NOT NULL COMMENT 'all / junior / senior',
    -- 경력
    career_n     INT           NOT NULL DEFAULT 0 COMMENT 'career_min 있는 공고 수',
    career_avg   DECIMAL(4,1)  NULL COMMENT '평균 요구연차',
    junior_cnt   INT           NOT NULL DEFAULT 0 COMMENT '0-2년',
    mid_cnt      INT           NOT NULL DEFAULT 0 COMMENT '3-5년',
    senior_cnt   INT           NOT NULL DEFAULT 0 COMMENT '6년+',
    -- 급여 (연봉 하한 pay_from, 단위: 만원)
    pay_n        INT           NOT NULL DEFAULT 0 COMMENT '연봉 숫자 있는 표본 수',
    pay_p25      INT           NULL,
    pay_p50      INT           NULL COMMENT '중앙값(만원)',
    pay_p75      INT           NULL,
    pay_avg      INT           NULL,
    PRIMARY KEY (skill_norm, career_band),
    KEY idx_pay_rank (career_band, pay_p50)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;


-- 마트 신선도/규모 메타 (화면 하단 "최종 갱신" 표기용)
CREATE TABLE IF NOT EXISTS mart_meta (
    meta_key     VARCHAR(50)   NOT NULL,
    meta_value   VARCHAR(255)  NULL,
    PRIMARY KEY (meta_key)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;
