"""
통합 크롤 검증 — 최근 N분 내 job_details 에 새로 쓰인 행을 점검한다.

크롤러가 수집과 동시에 job_details / job_skills 를 채우는지 확인용.
(backfilled_at 이 최근인 행 = 이번 크롤이 쓴 것)

    python scripts/check_recent_details.py            # 최근 30분
    python scripts/check_recent_details.py --min 10   # 최근 10분
"""
import argparse
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


def main():
    p = argparse.ArgumentParser(description="통합 크롤 검증")
    p.add_argument("--min", type=int, default=30, help="최근 N분 (기본 30)")
    args = p.parse_args()

    eng = make_engine()
    with eng.connect() as conn:
        win = {"m": args.min}
        total = conn.execute(text(
            "SELECT COUNT(*) FROM job_details "
            "WHERE backfilled_at >= NOW() - INTERVAL :m MINUTE"), win).scalar()
        print(f"최근 {args.min}분 내 쓰인 job_details : {total:,}행")
        if not total:
            print("  (이번 창에 새로 쓰인 행 없음 — 전부 기존/스킵이었을 수 있음)")
            return

        by = pd.read_sql(text("""
            SELECT backfill_status AS st, COUNT(*) AS c,
                   SUM(sido IS NOT NULL) AS with_sido
            FROM job_details
            WHERE backfilled_at >= NOW() - INTERVAL :m MINUTE
            GROUP BY backfill_status ORDER BY c DESC
        """), conn, params=win)
        for _, r in by.iterrows():
            print(f"    {r['st']:<8} {int(r['c']):>5,}  (sido O {int(r['with_sido']):,})")

        # 이 행들에 스킬이 실제로 붙었는지
        with_skills = conn.execute(text("""
            SELECT COUNT(DISTINCT d.job_id)
            FROM job_details d JOIN job_skills s ON s.job_id = d.job_id
            WHERE d.backfilled_at >= NOW() - INTERVAL :m MINUTE
        """), win).scalar()
        print(f"  그중 job_skills 붙은 공고        : {with_skills:,}")

        print("  샘플 5건:")
        samp = pd.read_sql(text("""
            SELECT job_id, backfill_status AS st, sido, sigungu, career_min
            FROM job_details
            WHERE backfilled_at >= NOW() - INTERVAL :m MINUTE
            ORDER BY backfilled_at DESC LIMIT 5
        """), conn, params=win)
        for _, r in samp.iterrows():
            print(f"    job_id={r['job_id']}  {r['st']}  "
                  f"{r['sido']}/{r['sigungu']}  경력min={r['career_min']}")


if __name__ == "__main__":
    main()
