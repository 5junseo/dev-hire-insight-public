"""
공고 상세 페이지 백필

기존 jobs 테이블의 url 로 상세 페이지를 다시 방문해
목록 수집 때 놓친 필드(근무지/위경도/경력연차/급여/근무조건)를 job_details 에 채운다.

설계 메모
  * jobs 테이블은 읽기만 한다. 쓰기는 job_details / job_skills 로만.
  * 이미 성공(OK)한 job_id 는 건너뛴다 → 언제든 중단하고 이어받기 가능.
  * Ctrl+C 는 현재 배치를 커밋하고 정상 종료한다.

사용 예
    python scripts/backfill_details.py --create-schema      # 최초 1회 (DDL)
    python scripts/backfill_details.py --limit 200          # 소규모 시험
    python scripts/backfill_details.py --since-days 30      # 최근 30일치만
    python scripts/backfill_details.py                      # 전량 (이어받기)
    python scripts/backfill_details.py --retry-errors       # 실패분만 재시도
    python scripts/backfill_details.py --refix-region       # 재크롤 없이 지역만 재산출
"""
import argparse
import json
import os
import re
import signal
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pymysql
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# 상세 파싱 로직은 크롤러와 공용 모듈(detail_parser)을 쓴다.
sys.path.insert(0, str(BASE_DIR / "devhire_crawler"))
from devhire_crawler.utils.detail_parser import (  # noqa: E402
    DETAIL_COLS, build_skill_rows, extract_jobs_block, is_tech_skill,
    parse_detail, posting_id_of, split_address,
)
from devhire_crawler.utils.target import detail_path  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")

_stop = False


def _on_sigint(signum, frame):
    global _stop
    if _stop:
        print("\n강제 종료.")
        sys.exit(1)
    _stop = True
    print("\n[중단 요청] 현재 배치를 커밋하고 종료합니다. (한 번 더 누르면 강제 종료)")


signal.signal(signal.SIGINT, _on_sigint)


# ---------------------------------------------------------------- DB
def connect():
    missing = [k for k in ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME") if not os.getenv(k)]
    if missing:
        sys.exit(f"[중단] .env 에 없는 값: {', '.join(missing)}")
    return pymysql.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=15,
    )


def create_schema(conn):
    ddl_path = BASE_DIR / "sql" / "002_job_details.sql"
    if not ddl_path.exists():
        sys.exit(f"[중단] DDL 파일 없음: {ddl_path}")
    sql = ddl_path.read_text(encoding="utf-8")
    cur = conn.cursor()
    for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
        cur.execute(stmt)
    conn.commit()
    cur.close()
    print(f"스키마 적용 완료 ({ddl_path.name})")


# ------------------------------------------------------------- 파싱
def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")


# extract_jobs_block / split_address / parse_detail / posting_id_of 는
# 크롤러와 공용인 detail_parser 모듈에서 import 한다 (상단 참조).


# ------------------------------------------------------------ 워커
def process(row, delay):
    """네트워크 구간. DB 는 건드리지 않는다."""
    job_id, url = row["id"], row["url"]
    out = {"job_id": job_id, "posting_id": posting_id_of(url)}
    try:
        page = fetch(url)
    except urllib.error.HTTPError as e:
        # 404 는 삭제된 공고. 재시도해도 의미 없으므로 GONE 으로 분리한다.
        status = "GONE" if e.code in (404, 410) else "ERROR"
        out.update(status=status, error=f"HTTP {e.code}"[:255])
        time.sleep(delay)
        return out
    except Exception as e:
        out.update(status="ERROR", error=f"{type(e).__name__}: {e}"[:255])
        time.sleep(delay)
        return out

    jd = extract_jobs_block(page)
    if not jd:
        out.update(status="NO_DATA", error="JOBS 블록 없음")
        time.sleep(delay)
        return out

    try:
        fields, skills = parse_detail(jd)
        out.update(status="OK", fields=fields, skills=skills, raw=jd)
    except Exception as e:
        out.update(status="ERROR", error=f"parse: {type(e).__name__}: {e}"[:255])
    time.sleep(delay)
    return out


def write_batch(conn, results, save_raw):
    cur = conn.cursor()
    detail_rows, skill_rows, clear_ids = [], [], []

    for r in results:
        f = r.get("fields") or {}
        vals = [r.get("posting_id")] + [f.get(c) for c in DETAIL_COLS[1:]]
        vals += [r["status"], r.get("error"), datetime.now(),
                 json.dumps(r["raw"], ensure_ascii=False) if (save_raw and r.get("raw")) else None,
                 r["job_id"]]
        detail_rows.append(vals)

        if r["status"] == "OK":
            clear_ids.append(r["job_id"])
            skill_rows.extend(build_skill_rows(r["job_id"], r.get("skills")))

    # DETAIL_COLS + backfill_status, backfill_error, backfilled_at, raw_json, job_id
    placeholders = ", ".join(["%s"] * (len(DETAIL_COLS) + 5))
    updates = ", ".join(f"{c}=VALUES({c})" for c in DETAIL_COLS)
    cur.executemany(
        f"""INSERT INTO job_details
              ({', '.join(DETAIL_COLS)}, backfill_status, backfill_error, backfilled_at, raw_json, job_id)
            VALUES ({placeholders})
            ON DUPLICATE KEY UPDATE
              {updates},
              backfill_status=VALUES(backfill_status),
              backfill_error=VALUES(backfill_error),
              backfilled_at=VALUES(backfilled_at),
              raw_json=VALUES(raw_json)""",
        detail_rows,
    )

    # 스킬은 전량 교체 (재실행 시 중복/잔여 방지)
    if clear_ids:
        cur.execute(
            f"DELETE FROM job_skills WHERE job_id IN ({','.join(['%s'] * len(clear_ids))})",
            clear_ids,
        )
    if skill_rows:
        cur.executemany(
            """INSERT INTO job_skills (job_id, skill, skill_norm, is_tech)
               VALUES (%s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE skill=VALUES(skill), is_tech=VALUES(is_tech)""",
            skill_rows,
        )
    conn.commit()
    cur.close()


def reclassify_skills(conn):
    """
    이미 적재된 job_skills 의 is_tech 를 현재 규칙으로 다시 매긴다.

    분류 규칙은 새 인성 키워드가 나올 때마다 손보게 되는데,
    그때마다 상세 페이지를 다시 긁을 수는 없다. 재크롤 없이 라벨만 고친다.
    """
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT skill, is_tech FROM job_skills")
    rows = cur.fetchall()

    flips = [(1 if is_tech_skill(r["skill"]) else 0, r["skill"])
             for r in rows
             if (1 if is_tech_skill(r["skill"]) else 0) != r["is_tech"]]

    if not flips:
        print(f"재분류 대상 없음 (고유 스킬 {len(rows):,}종)")
        cur.close()
        return

    cur.executemany("UPDATE job_skills SET is_tech=%s WHERE skill=%s", flips)
    conn.commit()

    to_soft = [s for t, s in flips if t == 0]
    to_tech = [s for t, s in flips if t == 1]
    print(f"고유 스킬 {len(rows):,}종 중 {len(flips)}종 재분류 (영향 행 {cur.rowcount:,})")
    if to_soft:
        print(f"  기술 → 인성 ({len(to_soft)}): {', '.join(to_soft[:15])}")
    if to_tech:
        print(f"  인성 → 기술 ({len(to_tech)}): {', '.join(to_tech[:15])}")
    cur.close()


def refix_region(conn):
    """
    이미 적재된 job_details 의 주소를 현재 split_address 로 다시 파싱해
    sido/sigungu 를 갱신한다. 상세 페이지 재크롤 없이 저장된 주소만 재해석.

    주소 파싱 규칙(대한민국 접두어/시도 풀네임)이 바뀌었을 때, 지역만 다시
    매긴다. OK 이면서 주소가 있는 행만 대상.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT job_id, address, sido, sigungu
        FROM job_details
        WHERE backfill_status='OK' AND address IS NOT NULL
    """)
    rows = cur.fetchall()

    updates, recovered = [], 0
    for r in rows:
        sido, sigungu = split_address(r["address"])
        if sido != r["sido"] or sigungu != r["sigungu"]:
            updates.append((sido, sigungu, r["job_id"]))
            if r["sido"] is None and sido is not None:
                recovered += 1

    if not updates:
        print(f"지역 재산출 대상 없음 (OK+주소 {len(rows):,}행 점검)")
        cur.close()
        return

    cur.executemany(
        "UPDATE job_details SET sido=%s, sigungu=%s WHERE job_id=%s",
        updates,
    )
    conn.commit()
    print(f"OK+주소 {len(rows):,}행 점검 → {len(updates):,}행 지역 갱신 "
          f"(그중 sido 신규 부여 {recovered:,}행 = 마트 추가 유입)")
    cur.close()


def select_targets(conn, args):
    where = ["j.url LIKE %s"]
    params = [f"%{detail_path()}%"]

    if args.retry_errors:
        where.append("d.backfill_status IN ('ERROR', 'NO_DATA')")  # GONE 제외
    else:
        where.append("(d.job_id IS NULL OR d.backfill_status <> 'OK')")

    if args.since_days:
        where.append("j.created_at >= NOW() - INTERVAL %s DAY")
        params.append(args.since_days)

    order = "j.created_at DESC" if args.order == "new" else "j.created_at ASC"
    sql = f"""
        SELECT j.id, j.url
        FROM jobs j
        LEFT JOIN job_details d ON d.job_id = j.id
        WHERE {' AND '.join(where)}
        ORDER BY {order}
    """
    if args.limit:
        sql += " LIMIT %s"
        params.append(args.limit)

    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def main():
    p = argparse.ArgumentParser(description="공고 상세 백필")
    p.add_argument("--create-schema", action="store_true", help="DDL 적용 후 종료")
    p.add_argument("--limit", type=int, help="처리 건수 상한")
    p.add_argument("--since-days", type=int, help="최근 N일 수집분만")
    p.add_argument("--order", choices=["new", "old"], default="new", help="최신순/오래된순 (기본 new)")
    p.add_argument("--delay", type=float, default=1.5, help="요청 간 지연 초 (기본 1.5)")
    p.add_argument("--workers", type=int, default=2, help="동시 요청 수 (기본 2)")
    p.add_argument("--batch", type=int, default=50, help="커밋 단위 (기본 50)")
    p.add_argument("--save-raw", action="store_true", help="원본 JSON 보존 (용량 큼)")
    p.add_argument("--retry-errors", action="store_true", help="실패분만 재시도")
    p.add_argument("--reclassify-skills", action="store_true",
                   help="재크롤 없이 기존 job_skills 의 기술/인성 라벨만 다시 매김")
    p.add_argument("--refix-region", action="store_true",
                   help="재크롤 없이 기존 job_details 주소로 sido/sigungu 재산출")
    p.add_argument("--dry-run", action="store_true", help="대상 건수만 출력")
    args = p.parse_args()

    conn = connect()

    if args.create_schema:
        create_schema(conn)
        conn.close()
        return

    if args.reclassify_skills:
        reclassify_skills(conn)
        conn.close()
        return

    if args.refix_region:
        refix_region(conn)
        conn.close()
        return

    targets = select_targets(conn, args)
    total = len(targets)
    rate = args.workers / max(args.delay, 0.01)
    print(f"대상 {total:,}건 | 동시 {args.workers} · 지연 {args.delay}s "
          f"→ 약 {rate:.1f} req/s · 예상 {total / rate / 3600:.1f}시간")

    if args.dry_run:
        conn.close()
        return
    if not total:
        print("처리할 대상이 없습니다.")
        conn.close()
        return

    stat = {"OK": 0, "NO_DATA": 0, "ERROR": 0, "GONE": 0}
    started = time.time()
    buf = []

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, res in enumerate(pool.map(lambda r: process(r, args.delay), targets), 1):
            stat[res["status"]] += 1
            buf.append(res)

            if len(buf) >= args.batch or _stop or i == total:
                write_batch(conn, buf, args.save_raw)
                buf = []
                elapsed = time.time() - started
                eta = (total - i) / (i / elapsed) if i else 0
                print(f"  {i:>6,}/{total:,} ({i / total * 100:5.1f}%) "
                      f"OK={stat['OK']:,} NO_DATA={stat['NO_DATA']:,} "
                      f"GONE={stat['GONE']:,} ERR={stat['ERROR']:,} "
                      f"| 남은 시간 {eta / 3600:.1f}h", flush=True)

            if _stop:
                break

    if buf:
        write_batch(conn, buf, args.save_raw)

    conn.close()
    done = sum(stat.values())
    print(f"\n{'중단됨' if _stop else '완료'} — 처리 {done:,}건 "
          f"(OK {stat['OK']:,} / NO_DATA {stat['NO_DATA']:,} / "
          f"GONE {stat['GONE']:,} / ERROR {stat['ERROR']:,})")
    print(f"소요 {(time.time() - started) / 60:.1f}분")
    if not _stop and done < total:
        print("남은 대상은 같은 명령을 다시 실행하면 이어받습니다.")


if __name__ == "__main__":
    main()
