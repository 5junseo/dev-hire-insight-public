"""
마트(mart) 재생성 ETL

raw 계층(job_details + job_skills)을 읽어 pandas 로 집계하고
분석 전용 요약 테이블을 다시 채운다. 하루 1회 배치로 도는 것을 상정.

  Extract : job_details(OK) + job_skills(is_tech=1) 를 DataFrame 으로
  Transform: 지역 × 스킬 × 경력밴드 groupby, 시도합계/전국순위 파생
  Load    : mart_* 테이블 TRUNCATE 후 일괄 적재 (멱등)

정책 메모
  * 공고 상태 CLOSE 도 포함한다 (트렌드/누적 분석용). "현재 열린 공고만"
    보려면 API 단에서 거르는 게 아니라, 필요 시 별도 마트를 판다.
  * career_band: junior=0~2년, senior=3년+, career_min 이 없으면(38%)
    'all' 에만 포함되고 junior/senior 어디에도 안 들어간다 → UI 에서 명시.
  * skill 은 공고 --min-count 건 이상만 (기본 5). 롱테일 노이즈 제거.

사용 예
    python scripts/build_mart.py --create-schema   # 최초 1회
    python scripts/build_mart.py                    # 재생성
    python scripts/build_mart.py --min-count 10     # 임계 조정
"""
import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pymysql
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def make_engine():
    missing = [k for k in ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME") if not os.getenv(k)]
    if missing:
        sys.exit(f"[중단] .env 에 없는 값: {', '.join(missing)}")
    url = (
        f"mysql+pymysql://{os.getenv('DB_USER')}:{quote_plus(os.getenv('DB_PASSWORD'))}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT', '3306')}/{os.getenv('DB_NAME')}"
        f"?charset=utf8mb4"
    )
    return create_engine(url, pool_pre_ping=True)


def create_schema(engine):
    ddl = (BASE_DIR / "sql" / "003_mart.sql").read_text(encoding="utf-8")
    with engine.begin() as conn:
        for stmt in [s.strip() for s in ddl.split(";") if s.strip()]:
            conn.execute(text(stmt))
    print("마트 스키마 적용 완료 (003_mart.sql)")


def _collapse(s):
    """스킬 표기변형을 하나로 모으는 축약키: 공백/점/하이픈/슬래시 제거 + 뒤쪽 js 제거.
    'spring boot'/'springboot' -> 'springboot', 'vue.js'/'vue' -> 'vue'."""
    k = re.sub(r"[\s._\-/]", "", s)
    k = re.sub(r"js$", "", k)
    return k or s


def canonicalize_skills(skills):
    """표기 정규화: 축약키가 같은 스킬을 '공고수 최다 표기'로 병합한다.

    원본 job_skills 는 건드리지 않고 마트 계층에서만 통합한다(재현 가능).
    react/reactjs/react.js -> react, spring boot/springboot -> spring boot 등.
    한 공고가 변형을 둘 다 갖고 있었다면 병합 후 중복행은 제거한다.
    """
    cnt = skills.groupby("skill_norm")["job_id"].nunique()
    groups = {}
    for sk in cnt.index:
        groups.setdefault(_collapse(sk), []).append(sk)

    canon = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        rep = max(members, key=lambda m: cnt[m])  # 공고수 최다 표기 = 대표
        for m in members:
            if m != rep:
                canon[m] = rep

    if canon:
        skills = skills.copy()
        skills["skill_norm"] = skills["skill_norm"].map(lambda x: canon.get(x, x))
        skills = skills.drop_duplicates(["job_id", "skill_norm"])
    print(f"  스킬 표기 통합: {len(canon):,}개 변형 → 대표표기로 병합")
    return skills


def career_band(v):
    """career_min(정수 연차) -> 밴드. NaN(미상)은 None."""
    if pd.isna(v):
        return None
    return "junior" if v < 3 else "senior"


def extract(engine):
    """OK 상세 + 기술스킬을 조인 가능한 형태로 읽는다."""
    print("추출 중...")
    details = pd.read_sql(
        text("""SELECT job_id, sido, sigungu, career_min, posted_at,
                       pay_type, pay_from, pay_is_placeholder
                FROM job_details
                WHERE backfill_status='OK' AND sido IS NOT NULL"""),
        engine,
    )
    # 연봉 하한(만원)만 신뢰: ANNUALLY_SALARY + placeholder 아닌 pay_from.
    # (MONTHLY/HOURLY 는 단위 상이, pay_to 는 +1 관례값 오염 → 제외)
    ann = (details["pay_type"] == "ANNUALLY_SALARY") & \
          (details["pay_from"].notna()) & \
          (details["pay_is_placeholder"].fillna(0) != 1)
    details["pay_ann"] = details["pay_from"].where(ann)
    skills = pd.read_sql(
        text("""SELECT job_id, skill_norm
                FROM job_skills WHERE is_tech=1"""),
        engine,
    )
    print(f"  상세 {len(details):,}행 · 스킬태그 {len(skills):,}행")
    return details, skills


def transform(details, skills, min_count):
    """지역 × 스킬 × 밴드 집계 + 파생 테이블들."""
    print("변형 중...")

    # 롱테일 스킬 제거: 전국 공고수 min_count 미만 스킬은 버린다
    skill_total = skills.groupby("skill_norm")["job_id"].nunique()
    keep = skill_total[skill_total >= min_count].index
    skills = skills[skills["skill_norm"].isin(keep)]
    print(f"  스킬 필터: {len(skill_total):,}종 → {len(keep):,}종 (공고 {min_count}건 이상)")

    # 상세에 밴드 부여
    details = details.copy()
    details["band"] = details["career_min"].map(career_band)

    # 공고-스킬 조인 (1 공고가 N 스킬)
    df = skills.merge(details, on="job_id", how="inner")

    # ---- mart_region_skill: 지역 × 스킬 × 밴드 ----
    def agg_region_skill(frame, band_label):
        # 시군구 단위
        g1 = (frame.groupby(["sido", "sigungu", "skill_norm"])["job_id"]
              .nunique().reset_index(name="cnt"))
        # 시도 합계 (sigungu = None)
        g2 = (frame.groupby(["sido", "skill_norm"])["job_id"]
              .nunique().reset_index(name="cnt"))
        g2.insert(1, "sigungu", None)
        out = pd.concat([g1, g2], ignore_index=True)
        out["career_band"] = band_label
        return out

    parts = [agg_region_skill(df, "all")]
    for b in ("junior", "senior"):
        sub = df[df["band"] == b]
        if len(sub):
            parts.append(agg_region_skill(sub, b))
    region_skill = pd.concat(parts, ignore_index=True)
    region_skill = region_skill[["sido", "sigungu", "skill_norm", "career_band", "cnt"]]

    # ---- mart_skill: 전국 스킬 순위 (all 밴드, 공고 유니크) ----
    skill_rank = (df.groupby("skill_norm")["job_id"].nunique()
                  .sort_values(ascending=False).reset_index(name="total_cnt"))
    skill_rank["rank_no"] = range(1, len(skill_rank) + 1)

    # ---- mart_region_total: 지역별 전체 공고 수 (스킬 무관) ----
    def agg_region_total(frame, band_label):
        g1 = frame.groupby(["sido", "sigungu"])["job_id"].nunique().reset_index(name="cnt")
        g2 = frame.groupby(["sido"])["job_id"].nunique().reset_index(name="cnt")
        g2.insert(1, "sigungu", None)
        out = pd.concat([g1, g2], ignore_index=True)
        out["career_band"] = band_label
        return out

    tparts = [agg_region_total(details, "all")]
    for b in ("junior", "senior"):
        sub = details[details["band"] == b]
        if len(sub):
            tparts.append(agg_region_total(sub, b))
    region_total = pd.concat(tparts, ignore_index=True)[["sido", "sigungu", "career_band", "cnt"]]

    # ---- mart_skill_cooccur: 스킬 동시출현 (전국, 방향성, lift 편향보정) ----
    # frame(job_id, skill_norm) 자기조인으로 스킬 쌍을 만든다.
    #   MIN_CO       : 우연한 공동등장 제거 (동시출현 공고 최소)
    #   MIN_REL_BASE : 추천 대상 스킬의 최소 공고수. 이게 없으면 'python 과만 등장하는
    #                  희소 스킬(perl 등)'이 lift 최대치로 도배된다(lift 고질병) → 니치 배제.
    MIN_CO = 5
    MIN_REL_BASE = 50

    def agg_cooccur(frame, band_label):
        base = frame.groupby("skill_norm")["job_id"].nunique()  # skill 별 공고 수
        n_jobs = frame["job_id"].nunique()                      # 동시출현 모집단(밴드별)
        pairs = frame[["job_id", "skill_norm"]].merge(
            frame[["job_id", "skill_norm"]], on="job_id", suffixes=("", "_r"))
        pairs = pairs[pairs["skill_norm"] != pairs["skill_norm_r"]]
        co = (pairs.groupby(["skill_norm", "skill_norm_r"])["job_id"]
              .nunique().reset_index(name="co_cnt"))
        co = co[co["co_cnt"] >= MIN_CO]
        # 관련스킬(related)이 어느 정도 수요 있는 것만 남긴다 → 희소 스킬 도배 방지
        co = co[co["skill_norm_r"].map(base) >= MIN_REL_BASE]
        co["pct"] = (co["co_cnt"] / co["skill_norm"].map(base) * 100).round(1)
        # lift = P(rel|skill)/P(rel) = co*N / (base_skill*base_rel).
        # 1=독립, >1=양의 연관. base_rel 큰 범용스킬(git/aws)은 lift 가 눌려 편향 보정.
        co["lift"] = (co["co_cnt"] * n_jobs
                      / (co["skill_norm"].map(base) * co["skill_norm_r"].map(base))).round(2)
        co["career_band"] = band_label
        return co.rename(
            columns={"skill_norm": "skill", "skill_norm_r": "related_skill"}
        )[["skill", "related_skill", "career_band", "co_cnt", "pct", "lift"]]

    cparts = [agg_cooccur(skills, "all")]
    for b in ("junior", "senior"):
        sub = skills[skills["job_id"].isin(details.loc[details["band"] == b, "job_id"])]
        if len(sub):
            cparts.append(agg_cooccur(sub, b))
    skill_cooccur = pd.concat(cparts, ignore_index=True)

    # ---- mart_trend / mart_trend_total: 게시일(posted_at) 기준 주별 추이 ----
    # posted_at 이 있는 공고만(백필로 채워진 것). 주 시작일(월요일)로 버킷팅한다.
    det = details[details["posted_at"].notna()].copy()
    det["posted_at"] = pd.to_datetime(det["posted_at"])
    det["week"] = (det["posted_at"] - pd.to_timedelta(det["posted_at"].dt.weekday, unit="D")).dt.date

    def agg_trend_total(frame, band_label):
        g = frame.groupby("week")["job_id"].nunique().reset_index(name="cnt")
        g["career_band"] = band_label
        return g.rename(columns={"week": "period"})[["period", "career_band", "cnt"]]

    tp = [agg_trend_total(det, "all")]
    for b in ("junior", "senior"):
        sub = det[det["band"] == b]
        if len(sub):
            tp.append(agg_trend_total(sub, b))
    trend_total = pd.concat(tp, ignore_index=True) if det.shape[0] else \
        pd.DataFrame(columns=["period", "career_band", "cnt"])

    # 스킬별: (필터 통과) 스킬 × 주. skills 는 이미 정규화·롱테일 제거된 상태.
    sd = skills.merge(det[["job_id", "week", "band"]], on="job_id", how="inner")

    def agg_trend_skill(frame, band_label):
        g = (frame.groupby(["skill_norm", "week"])["job_id"]
             .nunique().reset_index(name="cnt"))
        g["career_band"] = band_label
        return g.rename(columns={"week": "period"})[["skill_norm", "period", "career_band", "cnt"]]

    sp = [agg_trend_skill(sd, "all")]
    for b in ("junior", "senior"):
        sub = sd[sd["band"] == b]
        if len(sub):
            sp.append(agg_trend_skill(sub, b))
    trend_skill = pd.concat(sp, ignore_index=True) if sd.shape[0] else \
        pd.DataFrame(columns=["skill_norm", "period", "career_band", "cnt"])

    # ---- mart_skill_stat: 스킬별 급여/경력 통계 (밴드별) ----
    # df(job_id, skill_norm, career_min, band, pay_ann) 를 스킬×밴드로 요약.
    #   경력: career_min 평균 + 3구간 분포(주니어0-2/미들3-5/시니어6+)
    #   급여: 연봉 하한(pay_ann) 표본의 사분위. 표본 pay_n<MIN_PAY_N 이면 NULL.
    MIN_PAY_N = 10

    def career_bucket(v):
        if pd.isna(v):
            return None
        return "j" if v <= 2 else ("m" if v <= 5 else "s")

    dstat = df[["job_id", "skill_norm", "career_min", "band", "pay_ann"]].copy()
    dstat["cb"] = dstat["career_min"].map(career_bucket)

    def agg_stat(frame, band_label):
        recs = []
        for skill, grp in frame.groupby("skill_norm"):
            cvals = grp["career_min"].dropna()
            pvals = grp["pay_ann"].dropna()
            has_pay = len(pvals) >= MIN_PAY_N
            recs.append({
                "skill_norm": skill,
                "career_band": band_label,
                "career_n": int(len(cvals)),
                "career_avg": round(float(cvals.mean()), 1) if len(cvals) else None,
                "junior_cnt": int((grp["cb"] == "j").sum()),
                "mid_cnt": int((grp["cb"] == "m").sum()),
                "senior_cnt": int((grp["cb"] == "s").sum()),
                "pay_n": int(len(pvals)),
                "pay_p25": int(pvals.quantile(.25)) if has_pay else None,
                "pay_p50": int(pvals.quantile(.5)) if has_pay else None,
                "pay_p75": int(pvals.quantile(.75)) if has_pay else None,
                "pay_avg": int(round(pvals.mean())) if has_pay else None,
            })
        return recs

    stat_recs = agg_stat(dstat, "all")
    for b in ("junior", "senior"):
        sub = dstat[dstat["band"] == b]
        if len(sub):
            stat_recs += agg_stat(sub, b)
    cols_stat = ["skill_norm", "career_band", "career_n", "career_avg",
                 "junior_cnt", "mid_cnt", "senior_cnt",
                 "pay_n", "pay_p25", "pay_p50", "pay_p75", "pay_avg"]
    skill_stat = pd.DataFrame(stat_recs, columns=cols_stat)
    # NULL 사분위는 object dtype 로 두어 to_sql 이 NULL 로 넣게 함
    for c in ("pay_p25", "pay_p50", "pay_p75", "pay_avg", "career_avg"):
        skill_stat[c] = skill_stat[c].astype("object").where(skill_stat[c].notna(), None)

    weeks = det["week"].nunique() if det.shape[0] else 0
    pay_skills = int((skill_stat[skill_stat["career_band"] == "all"]["pay_n"] >= MIN_PAY_N).sum())
    print(f"  region_skill {len(region_skill):,}행 · skill {len(skill_rank):,}행 "
          f"· region_total {len(region_total):,}행 · cooccur {len(skill_cooccur):,}행")
    print(f"  trend: 전체 {len(trend_total):,}행 · 스킬별 {len(trend_skill):,}행 "
          f"(게시일 있는 공고 {det.shape[0]:,} · {weeks}주)")
    print(f"  skill_stat {len(skill_stat):,}행 (연봉 표본 {MIN_PAY_N}건+ 스킬 {pay_skills:,}종)")
    return (region_skill, skill_rank, region_total, skill_cooccur,
            trend_total, trend_skill, skill_stat)


def load(engine, region_skill, skill_rank, region_total, skill_cooccur,
         trend_total, trend_skill, skill_stat, unique_jobs):
    """TRUNCATE 후 일괄 적재. 실패해도 raw 는 안전."""
    print("적재 중...")
    with engine.begin() as conn:
        for t in ("mart_region_skill", "mart_skill", "mart_region_total",
                  "mart_skill_cooccur", "mart_trend", "mart_trend_total",
                  "mart_skill_stat"):
            conn.execute(text(f"TRUNCATE TABLE {t}"))

    region_skill.to_sql("mart_region_skill", engine, if_exists="append", index=False, chunksize=5000)
    skill_rank.to_sql("mart_skill", engine, if_exists="append", index=False, chunksize=5000)
    region_total.to_sql("mart_region_total", engine, if_exists="append", index=False, chunksize=5000)
    skill_cooccur.to_sql("mart_skill_cooccur", engine, if_exists="append", index=False, chunksize=5000)
    trend_total.to_sql("mart_trend_total", engine, if_exists="append", index=False, chunksize=5000)
    trend_skill.to_sql("mart_trend", engine, if_exists="append", index=False, chunksize=5000)
    skill_stat.to_sql("mart_skill_stat", engine, if_exists="append", index=False, chunksize=5000)

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM mart_meta WHERE meta_key IN ('built_at','unique_jobs','skill_count')"))
        conn.execute(
            text("INSERT INTO mart_meta (meta_key, meta_value) VALUES "
                 "(:k1,:v1),(:k2,:v2),(:k3,:v3)"),
            {"k1": "built_at", "v1": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             "k2": "unique_jobs", "v2": str(unique_jobs),
             "k3": "skill_count", "v3": str(len(skill_rank))},
        )
    print("적재 완료")


def main():
    p = argparse.ArgumentParser(description="마트 재생성 ETL")
    p.add_argument("--create-schema", action="store_true", help="DDL 적용 후 종료")
    p.add_argument("--min-count", type=int, default=5, help="스킬 최소 공고수 (기본 5)")
    args = p.parse_args()

    engine = make_engine()

    if args.create_schema:
        create_schema(engine)
        return

    started = datetime.now()
    details, skills = extract(engine)
    skills = canonicalize_skills(skills)
    unique_jobs = details["job_id"].nunique()
    (region_skill, skill_rank, region_total, skill_cooccur,
     trend_total, trend_skill, skill_stat) = transform(details, skills, args.min_count)
    load(engine, region_skill, skill_rank, region_total, skill_cooccur,
         trend_total, trend_skill, skill_stat, unique_jobs)

    print(f"\n완료 — 소요 {(datetime.now() - started).total_seconds():.1f}초 "
          f"(공고 {unique_jobs:,} · 스킬 {len(skill_rank):,}종)")


if __name__ == "__main__":
    main()
