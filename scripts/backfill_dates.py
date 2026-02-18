"""저장된 공고를 재수집해 posted_at / closes_at 를 채운다 (시계열 과거 소급).

닫힌(CLOSE) 공고도 페이지가 게시일을 주므로 재수집으로 과거 날짜를 복구한다.
posted_at 이 아직 NULL 인 것만 대상 → 중단해도 재실행하면 이어서 진행(멱등).
GONE(삭제) 은 제외. 예의상 딜레이를 둔다.

선행: python scripts/migrate_add_date_cols.py  (컬럼 추가, 1회)
사용:
    python scripts/backfill_dates.py                 # 전량(NULL 인 것 전부)
    python scripts/backfill_dates.py --limit 2000    # 2000건만(나눠 돌리기)
    python scripts/backfill_dates.py --delay 1.5     # 딜레이 조정(기본 2.0초)
"""
import argparse
import os
import sys
import time
import urllib.request
from pathlib import Path

import pymysql
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
sys.path.insert(0, str(BASE_DIR / "devhire_crawler"))
from devhire_crawler.utils.detail_parser import extract_jobs_block, parse_detail  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _fmt(sec):
    """초 -> 'Xh Ym' / 'Ym Zs' / 'Zs'."""
    sec = int(max(sec, 0))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def fetch_dates(url):
    """(posted_at, closes_at) 또는 (None, None) + 결과코드."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
        html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
    except Exception as e:
        return None, None, (f"HTTP{getattr(e, 'code', '')}" if getattr(e, "code", None) else "ERR")
    job = extract_jobs_block(html)
    if not job:
        return None, None, "NO_DATA"
    fields, _ = parse_detail(job)
    return fields.get("posted_at"), fields.get("closes_at"), "OK"


def main():
    p = argparse.ArgumentParser(description="게시일 백필")
    p.add_argument("--limit", type=int, default=0, help="처리 건수 상한(0=전량)")
    p.add_argument("--delay", type=float, default=2.0, help="요청 간 딜레이 초(기본 2.0)")
    args = p.parse_args()

    conn = pymysql.connect(
        host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"), charset="utf8mb4", autocommit=False,
    )
    cur = conn.cursor()

    sql = """SELECT j.id, j.url FROM job_details d JOIN jobs j ON j.id=d.job_id
             WHERE d.posted_at IS NULL AND d.backfill_status <> 'GONE' AND j.url IS NOT NULL
             ORDER BY j.id"""
    if args.limit:
        sql += f" LIMIT {int(args.limit)}"
    cur.execute(sql)
    targets = cur.fetchall()
    print(f"대상 {len(targets):,}건 (posted_at NULL) · 딜레이 {args.delay}s "
          f"· 예상 {len(targets) * args.delay / 3600:.1f}h")

    stat = {"OK": 0, "NO_DATE": 0, "FAIL": 0}
    started = time.time()
    try:
        for i, (job_id, url) in enumerate(targets, 1):
            posted, closes, code = fetch_dates(url)
            if code == "OK" and posted:
                cur.execute(
                    "UPDATE job_details SET posted_at=%s, closes_at=%s WHERE job_id=%s",
                    (posted, closes, job_id),
                )
                stat["OK"] += 1
            elif code == "OK":
                stat["NO_DATE"] += 1  # 페이지는 있으나 날짜 필드 없음
            else:
                stat["FAIL"] += 1     # 404/삭제 등 — 다음 실행에서 재시도

            if i % 200 == 0:
                conn.commit()  # 커밋은 200건마다(DB 안전)
            if i % 50 == 0 or i == len(targets):
                el = time.time() - started
                rate = i / el if el else 0            # 건/초
                remain = (len(targets) - i) / rate if rate else 0
                pct = i / len(targets) * 100
                print(f"  {i:,}/{len(targets):,} ({pct:.1f}%)  "
                      f"OK {stat['OK']:,} · 무날짜 {stat['NO_DATE']} · 실패 {stat['FAIL']}  |  "
                      f"경과 {_fmt(el)} · 남음 ~{_fmt(remain)} · {rate * 60:.0f}건/분")
            time.sleep(args.delay)
    except KeyboardInterrupt:
        print("\n중단됨 — 여기까지 커밋하고 종료(재실행하면 이어서).")
    finally:
        conn.commit()
        conn.close()

    print(f"\n완료 — OK {stat['OK']:,} · 무날짜 {stat['NO_DATE']:,} · 실패 {stat['FAIL']:,}")


if __name__ == "__main__":
    main()
