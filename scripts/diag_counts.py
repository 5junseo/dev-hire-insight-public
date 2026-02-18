"""
데이터 흐름 진단 — 왜 마트 unique_jobs 가 안 늘었나.

raw(jobs) → 백필(job_details) → 마트 각 단계의 건수를 한 번에 찍어
어디서 막혔는지 본다. 읽기 전용(SELECT), 아무것도 안 고친다.

    python scripts/diag_counts.py
"""
import os
import sys
from pathlib import Path

import pandas as pd
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
    miss = [k for k in ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME") if not os.getenv(k)]
    if miss:
        sys.exit(f"[중단] .env 없음: {', '.join(miss)}")
    url = (
        f"mysql+pymysql://{os.getenv('DB_USER')}:{quote_plus(os.getenv('DB_PASSWORD'))}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT', '3306')}/{os.getenv('DB_NAME')}?charset=utf8mb4"
    )
    return create_engine(url, pool_pre_ping=True)


def one(conn, sql):
    return conn.execute(text(sql)).scalar()


# 수정 예정인 split_address 로직을 미리 적용해 복구 가능 건수를 가늠한다.
SIDO_ALIASES = {
    "서울특별시": "서울", "서울": "서울",
    "부산광역시": "부산", "부산": "부산",
    "대구광역시": "대구", "대구": "대구",
    "인천광역시": "인천", "인천": "인천",
    "광주광역시": "광주", "광주": "광주",
    "대전광역시": "대전", "대전": "대전",
    "울산광역시": "울산", "울산": "울산",
    "세종특별자치시": "세종", "세종": "세종",
    "경기도": "경기", "경기": "경기",
    "강원특별자치도": "강원", "강원도": "강원", "강원": "강원",
    "충청북도": "충북", "충북": "충북",
    "충청남도": "충남", "충남": "충남",
    "전북특별자치도": "전북", "전라북도": "전북", "전북": "전북",
    "전라남도": "전남", "전남": "전남",
    "경상북도": "경북", "경북": "경북",
    "경상남도": "경남", "경남": "경남",
    "제주특별자치도": "제주", "제주도": "제주", "제주": "제주",
}
_ALIASES_SORTED = sorted(SIDO_ALIASES, key=len, reverse=True)


def resolve_sido(addr):
    """국가 접두어 제거 후 시도 풀네임/약칭 매칭. 국내면 짧은 시도명, 아니면 None."""
    if not addr:
        return None
    parts = addr.replace(",", " ").split()
    while parts and parts[0] in ("대한민국", "한국"):
        parts.pop(0)
    if not parts:
        return None
    first = parts[0]
    for alias in _ALIASES_SORTED:
        if first.startswith(alias):
            return SIDO_ALIASES[alias]
    return None


def main():
    sys.path.insert(0, str(BASE_DIR / "devhire_crawler"))
    from devhire_crawler.utils.target import detail_path

    path_token = detail_path()
    like = f"%{path_token}%"
    eng = make_engine()
    with eng.connect() as conn:
        print("=" * 52)
        print(" RAW 계층 (jobs)")
        print("=" * 52)
        jobs_total = one(conn, "SELECT COUNT(*) FROM jobs")
        jobs_read = conn.execute(
            text("SELECT COUNT(*) FROM jobs WHERE url LIKE :like"),
            {"like": like},
        ).scalar()
        print(f"  jobs 전체            : {jobs_total:,}")
        print(f"  백필 대상(상세 URL)  : {jobs_read:,}")
        # 최근 수집 분포
        recent = pd.read_sql(text("""
            SELECT DATE(created_at) AS d, COUNT(*) AS c
            FROM jobs GROUP BY DATE(created_at) ORDER BY d DESC LIMIT 7
        """), conn)
        print("  최근 수집일별 건수(상위 7일):")
        for _, r in recent.iterrows():
            print(f"    {r['d']}  {r['c']:,}")

        print("=" * 52)
        print(" 백필 계층 (job_details)")
        print("=" * 52)
        det_total = one(conn, "SELECT COUNT(*) FROM job_details")
        print(f"  job_details 전체     : {det_total:,}")
        by_status = pd.read_sql(text("""
            SELECT COALESCE(backfill_status,'(null)') AS st,
                   COUNT(*) AS c,
                   SUM(sido IS NULL) AS sido_null
            FROM job_details GROUP BY backfill_status ORDER BY c DESC
        """), conn)
        for _, r in by_status.iterrows():
            print(f"    {r['st']:<10} {r['c']:>8,}  (sido_null {int(r['sido_null']):,})")

        ok_sido = one(conn, """
            SELECT COUNT(*) FROM job_details
            WHERE backfill_status='OK' AND sido IS NOT NULL
        """)
        print(f"  → 마트 입력(OK & sido O): {ok_sido:,}")

        print("=" * 52)
        print(" 아직 백필 안 된 대상")
        print("=" * 52)
        pending = conn.execute(text("""
            SELECT COUNT(*) FROM jobs j
            LEFT JOIN job_details d ON d.job_id = j.id
            WHERE j.url LIKE :like
              AND (d.job_id IS NULL OR d.backfill_status <> 'OK')
        """), {"like": like}).scalar()
        never = conn.execute(text("""
            SELECT COUNT(*) FROM jobs j
            LEFT JOIN job_details d ON d.job_id = j.id
            WHERE j.url LIKE :like AND d.job_id IS NULL
        """), {"like": like}).scalar()
        print(f"  백필 미완(전체 non-OK): {pending:,}")
        print(f"    그중 아예 시도 안 됨 : {never:,}")

        print("=" * 52)
        print(" 07-22 이후 유입분이 어디로 갔나 (jobs.created_at 기준)")
        print("=" * 52)
        since = pd.read_sql(text("""
            SELECT COALESCE(d.backfill_status,'(미백필)') AS st,
                   SUM(d.sido IS NULL OR d.job_id IS NULL) AS sido_null,
                   COUNT(*) AS c
            FROM jobs j
            LEFT JOIN job_details d ON d.job_id = j.id
            WHERE j.created_at > '2026-07-22'
            GROUP BY d.backfill_status ORDER BY c DESC
        """), conn)
        for _, r in since.iterrows():
            print(f"    {r['st']:<10} {int(r['c']):>7,}  (sido없음 {int(r['sido_null']):,})")
        new_ok_sido = one(conn, """
            SELECT COUNT(*) FROM jobs j JOIN job_details d ON d.job_id=j.id
            WHERE j.created_at > '2026-07-22'
              AND d.backfill_status='OK' AND d.sido IS NOT NULL
        """)
        print(f"  → 그중 마트에 들어갈 자격(OK & sido O): {new_ok_sido:,}")

        print("=" * 52)
        print(" ERROR 사유 집계 (backfill_error, 상위 12)")
        print("=" * 52)
        errs = pd.read_sql(text("""
            SELECT COALESCE(backfill_error,'(null)') AS err, COUNT(*) AS c
            FROM job_details WHERE backfill_status='ERROR'
            GROUP BY backfill_error ORDER BY c DESC LIMIT 12
        """), conn)
        for _, r in errs.iterrows():
            print(f"    {int(r['c']):>6,}  {r['err']}")

        print("=" * 52)
        print(" sido=NULL OK 행 분류 (수정 파서 적용 시)")
        print("=" * 52)
        nrows = pd.read_sql(text("""
            SELECT address FROM job_details
            WHERE backfill_status='OK' AND sido IS NULL
        """), conn)
        no_addr = int(nrows["address"].isna().sum())
        domestic = for_etc = 0
        for a in nrows["address"].dropna():
            if resolve_sido(a) is not None:
                domestic += 1
            else:
                for_etc += 1
        print(f"    주소없음(재택/비공개)   : {no_addr:,}  → 지역 못 매김")
        print(f"    해외/기타              : {for_etc:,}  → 지역 못 매김")
        print(f"    국내(파서수정시 복구)   : {domestic:,}  → 재크롤 없이 살릴 수 있음 ✅")

        print("=" * 52)
        print(" sido=NULL OK 주소 샘플 (상위 15)")
        print("=" * 52)
        samp = pd.read_sql(text("""
            SELECT address, COUNT(*) AS c
            FROM job_details
            WHERE backfill_status='OK' AND sido IS NULL
            GROUP BY address ORDER BY c DESC LIMIT 15
        """), conn)
        for _, r in samp.iterrows():
            a = r['address'] if r['address'] is not None else '(주소 자체가 NULL)'
            print(f"    {int(r['c']):>5,}  {a}")

        print("=" * 52)
        print(" 마트 (mart_meta)")
        print("=" * 52)
        meta = pd.read_sql(text("SELECT meta_key, meta_value FROM mart_meta"), conn)
        for _, r in meta.iterrows():
            print(f"  {r['meta_key']:<12}: {r['meta_value']}")


if __name__ == "__main__":
    main()
