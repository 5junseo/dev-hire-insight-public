-- =====================================================================
-- 002_job_details.sql
-- 상세 페이지 백필 결과를 담는 계층 (raw 보존 / staging 분리)
--
-- 설계 원칙
--   * 기존 jobs 테이블은 건드리지 않는다 (원본 무손상)
--   * job_details 는 jobs 와 1:1, UPSERT 로 재실행 안전
--   * job_skills 는 분석용 정규화 테이블 (파이프 문자열 -> 행)
-- =====================================================================

CREATE TABLE IF NOT EXISTS job_details (
    job_id              INT             NOT NULL,
    posting_id          VARCHAR(20)     NULL COMMENT '상세 URL에서 추출한 공고 고유키 (쿼리스트링 제외)',

    -- 공고 상태
    status_type         VARCHAR(20)     NULL COMMENT 'POSTING / CLOSE',
    is_deleted          TINYINT(1)      NULL,

    -- 실제 공고 날짜 (구조화 데이터 postingStartAt/postingEndAt — 시계열용)
    posted_at           DATE            NULL COMMENT '게시 시작일',
    closes_at           DATE            NULL COMMENT '마감일',

    -- 근무지 (커버리지 99%)
    address             VARCHAR(300)    NULL,
    sido                VARCHAR(20)     NULL COMMENT '서울/경기/...',
    sigungu             VARCHAR(40)     NULL COMMENT '중구/강남구/성남시...',
    latitude            DECIMAL(10, 7)  NULL,
    longitude           DECIMAL(10, 7)  NULL,

    -- 경력 / 학력
    career_type         VARCHAR(20)     NULL COMMENT 'EXPERIENCED / NEW / ANY',
    career_min          SMALLINT        NULL COMMENT 'range.from — 정수 연차 (커버리지 69%)',
    career_max          SMALLINT        NULL,
    education_code      VARCHAR(20)     NULL,
    graduation_type     VARCHAR(20)     NULL,

    -- 급여 (커버리지 18%, payType 별 단위 상이하므로 반드시 함께 해석)
    pay_type            VARCHAR(30)     NULL COMMENT 'COMPANY_POLICY(82%) / ANNUALLY_SALARY / MONTHLY_SALARY',
    pay_from            INT             NULL COMMENT '단위: 만원. pay_type 없이 해석 금지',
    pay_to              INT             NULL,
    pay_is_placeholder  TINYINT(1)      NULL COMMENT 'to = from+1 형태의 관례적 표기 → 집계 제외 대상',

    -- 근무 조건
    work_week_type      VARCHAR(30)     NULL,
    work_start          VARCHAR(5)      NULL,
    work_end            VARCHAR(5)      NULL,
    benefit_count       SMALLINT        NULL,
    subway_count        SMALLINT        NULL,
    subway_min_dist     SMALLINT        NULL COMMENT '가장 가까운 역 거리 지표',

    -- 백필 관리
    backfill_status     VARCHAR(20)     NOT NULL DEFAULT 'PENDING' COMMENT 'OK / NO_DATA / ERROR',
    backfill_error      VARCHAR(255)    NULL,
    backfilled_at       DATETIME        NULL,
    raw_json            MEDIUMTEXT      NULL COMMENT '--save-raw 사용 시에만. 재크롤 없이 재파싱용',

    PRIMARY KEY (job_id),
    KEY idx_posting     (posting_id),
    KEY idx_sido        (sido),
    KEY idx_sigungu     (sigungu),
    KEY idx_posted      (posted_at),
    KEY idx_career_min  (career_min),
    KEY idx_status      (backfill_status),
    KEY idx_geo         (latitude, longitude),
    CONSTRAINT fk_job_details_job FOREIGN KEY (job_id)
        REFERENCES jobs (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;


-- ---------------------------------------------------------------------
-- 스킬 정규화 (파이프 문자열 -> 행)
-- is_tech = 0 : 계획성/성실성/협동심 등 인성 키워드 (표본 273개 중 15%)
--               동시출현 분석 시 반드시 제외해야 함
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_skills (
    job_id      INT             NOT NULL,
    skill       VARCHAR(100)    NOT NULL COMMENT '원본 표기',
    skill_norm  VARCHAR(100)    NOT NULL COMMENT '소문자 정규화 — 집계 키',
    is_tech     TINYINT(1)      NOT NULL DEFAULT 1,

    PRIMARY KEY (job_id, skill_norm),
    KEY idx_skill_norm (skill_norm),
    KEY idx_is_tech    (is_tech),
    CONSTRAINT fk_job_skills_job FOREIGN KEY (job_id)
        REFERENCES jobs (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;
