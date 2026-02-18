"""마트 조회 로직 — 모든 응답은 mart_* 테이블만 읽는다 (raw 조인 없음)."""
from sqlalchemy import text
from sqlalchemy.orm import Session

BANDS = ("all", "junior", "senior")


def _band(v: str) -> str:
    return v if v in BANDS else "all"


def list_skills(db: Session, limit: int):
    """드롭다운/순위용 스킬 목록 (전국 공고수 내림차순)."""
    rows = db.execute(
        text("""SELECT skill_norm AS skill, total_cnt, rank_no
                FROM mart_skill ORDER BY rank_no LIMIT :limit"""),
        {"limit": limit},
    ).mappings().all()
    return rows


def map_by_skill(db: Session, skill: str, career: str):
    """
    특정 스킬의 시도별 공고 수 + 시도 전체 대비 밀도.
    지도 색칠(choropleth)에 그대로 쓴다.
    """
    band = _band(career)
    rows = db.execute(
        text("""
            SELECT t.sido,
                   COALESCE(s.cnt, 0) AS count,
                   t.cnt              AS region_total,
                   ROUND(COALESCE(s.cnt, 0) / t.cnt * 100, 1) AS density
            FROM mart_region_total t
            LEFT JOIN mart_region_skill s
              ON  s.sido = t.sido AND s.sigungu IS NULL
              AND s.career_band = t.career_band
              AND s.skill_norm = :skill
            WHERE t.sigungu IS NULL AND t.career_band = :band
            ORDER BY count DESC
        """),
        {"skill": skill.lower().strip(), "band": band},
    ).mappings().all()
    return rows


def map_total(db: Session, career: str):
    """스킬 무관 — 시도별 전체 공고 수 (전체 보기 지도 색칠용)."""
    band = _band(career)
    rows = db.execute(
        text("""
            SELECT sido,
                   cnt AS count,
                   cnt AS region_total,
                   100.0 AS density
            FROM mart_region_total
            WHERE sigungu IS NULL AND career_band = :band
            ORDER BY count DESC
        """),
        {"band": band},
    ).mappings().all()
    return rows


def region_skills(db: Session, sido: str, sigungu: str | None, career: str, limit: int):
    """선택 지역의 인기 스택 순위. sigungu 없으면 시도 전체."""
    band = _band(career)
    params = {"sido": sido, "band": band, "limit": limit}
    sigungu_clause = "s.sigungu IS NULL" if not sigungu else "s.sigungu = :sigungu"
    if sigungu:
        params["sigungu"] = sigungu
    rows = db.execute(
        text(f"""
            SELECT skill_norm AS skill, cnt AS count
            FROM mart_region_skill s
            WHERE s.sido = :sido AND {sigungu_clause}
              AND s.career_band = :band
            ORDER BY cnt DESC LIMIT :limit
        """),
        params,
    ).mappings().all()
    return rows


def sigungu_by_skill(db: Session, sido: str, skill: str, career: str):
    """시도 클릭 시 드릴다운 — 그 시도 안 시군구별 스킬 공고 수."""
    band = _band(career)
    rows = db.execute(
        text("""
            SELECT sigungu, cnt AS count
            FROM mart_region_skill
            WHERE sido = :sido AND sigungu IS NOT NULL
              AND skill_norm = :skill AND career_band = :band
            ORDER BY count DESC
        """),
        {"sido": sido, "skill": skill.lower().strip(), "band": band},
    ).mappings().all()
    return rows


def sigungu_total(db: Session, sido: str, career: str):
    """스킬 무관 — 그 시도 안 시군구별 전체 공고 수 (전체 보기 드릴다운)."""
    band = _band(career)
    rows = db.execute(
        text("""
            SELECT sigungu, cnt AS count
            FROM mart_region_total
            WHERE sido = :sido AND sigungu IS NOT NULL AND career_band = :band
            ORDER BY count DESC
        """),
        {"sido": sido, "band": band},
    ).mappings().all()
    return rows


def related_skills(db: Session, skill: str, career: str, limit: int):
    """선택 스킬과 함께 요구되는 스택 (전국, lift 내림차순 = 편향보정된 '진짜 연관')."""
    band = _band(career)
    rows = db.execute(
        text("""
            SELECT related_skill AS skill, co_cnt AS count, pct, lift
            FROM mart_skill_cooccur
            WHERE skill = :skill AND career_band = :band
            ORDER BY lift DESC, co_cnt DESC
            LIMIT :limit
        """),
        {"skill": skill.lower().strip(), "band": band, "limit": limit},
    ).mappings().all()
    return rows


def trend(db: Session, skill: str | None, career: str):
    """게시일 기준 주별 공고 추이. skill 없으면 전체(스킬 무관) 라인."""
    band = _band(career)
    if skill:
        rows = db.execute(
            text("""SELECT period, cnt FROM mart_trend
                    WHERE skill_norm = :skill AND career_band = :band
                    ORDER BY period"""),
            {"skill": skill.lower().strip(), "band": band},
        ).mappings().all()
    else:
        rows = db.execute(
            text("""SELECT period, cnt FROM mart_trend_total
                    WHERE career_band = :band
                    ORDER BY period"""),
            {"band": band},
        ).mappings().all()
    return rows


def pay_ranking(db: Session, career: str, limit: int, min_n: int):
    """연봉(하한 중앙값) 상위 스킬 랭킹. 표본 min_n 미만 스킬은 제외."""
    band = _band(career)
    rows = db.execute(
        text("""
            SELECT skill_norm AS skill, pay_n, pay_p25, pay_p50, pay_p75, pay_avg
            FROM mart_skill_stat
            WHERE career_band = :band AND pay_p50 IS NOT NULL AND pay_n >= :min_n
            ORDER BY pay_p50 DESC, pay_avg DESC, pay_n DESC
            LIMIT :limit
        """),
        {"band": band, "min_n": min_n, "limit": limit},
    ).mappings().all()
    return rows


def skill_stat(db: Session, skill: str, career: str):
    """선택 스킬 상세 통계(경력 분포 + 연봉 사분위). 없으면 None."""
    band = _band(career)
    row = db.execute(
        text("""
            SELECT skill_norm AS skill, career_band,
                   career_n, career_avg, junior_cnt, mid_cnt, senior_cnt,
                   pay_n, pay_p25, pay_p50, pay_p75, pay_avg
            FROM mart_skill_stat
            WHERE skill_norm = :skill AND career_band = :band
        """),
        {"skill": skill.lower().strip(), "band": band},
    ).mappings().first()
    return row


def meta(db: Session):
    rows = db.execute(text("SELECT meta_key, meta_value FROM mart_meta")).mappings().all()
    return {r["meta_key"]: r["meta_value"] for r in rows}
