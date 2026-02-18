"""
DB 현황 점검 (읽기 전용)

- .env 는 dotenv 가 직접 읽으며, 접속 정보를 화면에 출력하지 않는다.
- SELECT / SHOW 만 수행한다. 쓰기 없음.

사용법:
    python scripts/inspect_db.py
"""
import os
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# stdout 인코딩 (Windows cp949 대응)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def connect():
    missing = [k for k in ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME") if not os.getenv(k)]
    if missing:
        print(f"[중단] .env 에 다음 값이 없습니다: {', '.join(missing)}")
        sys.exit(1)

    return pymysql.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
    )


def section(title):
    print("\n" + "=" * 62)
    print(title)
    print("=" * 62)


def main():
    try:
        conn = connect()
    except Exception as e:
        print(f"[접속 실패] {type(e).__name__}: {e}")
        print("Lightsail 인스턴스가 꺼져 있거나 방화벽에 현재 IP가 없을 수 있습니다.")
        sys.exit(1)

    cur = conn.cursor()

    # ---------- 테이블 목록 ----------
    section("테이블 목록")
    cur.execute("SHOW TABLES")
    key = list(cur.fetchone().keys())[0] if cur.rowcount else None
    cur.execute("SHOW TABLES")
    tables = [r[key] for r in cur.fetchall()] if key else []
    for t in tables:
        cur.execute(f"SELECT COUNT(*) AS c FROM `{t}`")
        print(f"  {t:<22} {cur.fetchone()['c']:>8,} rows")

    # ---------- 컬럼 구조 ----------
    for t in tables:
        section(f"[{t}] 컬럼")
        cur.execute(f"SHOW COLUMNS FROM `{t}`")
        for c in cur.fetchall():
            print(f"  {c['Field']:<20} {c['Type']:<22} "
                  f"null={c['Null']:<4} key={c['Key'] or '-':<4} def={c['Default']}")

    if "jobs" not in tables:
        print("\n[주의] jobs 테이블이 없습니다. 이후 점검을 건너뜁니다.")
        conn.close()
        return

    # ---------- URL 중복 실태 ----------
    section("URL 중복 실태 (백필 규모 산정의 핵심)")
    cur.execute("SELECT COUNT(*) AS c FROM jobs")
    total = cur.fetchone()["c"]

    sys.path.insert(0, str(BASE_DIR / "devhire_crawler"))
    from devhire_crawler.utils.target import detail_path

    delim = detail_path()
    # 추적 파라미터를 제거한 공고 고유 ID 기준 중복도
    cur.execute(
        """
        SELECT COUNT(DISTINCT SUBSTRING_INDEX(SUBSTRING_INDEX(url, %s, -1), '?', 1)) AS uniq
        FROM jobs
        """,
        (delim,),
    )
    uniq = cur.fetchone()["uniq"]

    print(f"  전체 행           : {total:>8,}")
    print(f"  고유 공고(ID 기준) : {uniq:>8,}")
    if uniq:
        print(f"  중복 배수         : {total / uniq:>8.2f}x")
        print(f"  제거 가능 행      : {total - uniq:>8,}")
    print(f"\n  => 백필 대상은 '고유 공고' {uniq:,}건 (2초 지연 시 약 {uniq * 2 / 60:.0f}분)")

    # ---------- 중복 상위 사례 ----------
    section("중복 상위 5건")
    cur.execute(
        """
        SELECT SUBSTRING_INDEX(SUBSTRING_INDEX(url, %s, -1), '?', 1) AS gid,
               COUNT(*) AS c, MIN(title) AS title
        FROM jobs
        GROUP BY gid HAVING c > 1
        ORDER BY c DESC LIMIT 5
        """,
        (delim,),
    )
    rows = cur.fetchall()
    if not rows:
        print("  중복 없음")
    for r in rows:
        print(f"  {r['gid']:<12} {r['c']:>3}회  {(r['title'] or '')[:40]}")

    # ---------- 수집 시간 범위 ----------
    section("수집 기간 (시계열 분석 가능 여부)")
    cur.execute("SELECT MIN(created_at) AS a, MAX(created_at) AS b, COUNT(DISTINCT DATE(created_at)) AS d FROM jobs")
    r = cur.fetchone()
    print(f"  최초 수집 : {r['a']}")
    print(f"  최근 수집 : {r['b']}")
    print(f"  수집 일수 : {r['d']}일  <- 시계열 트렌드는 이 값이 충분해야 성립")

    # ---------- 스킬 보유율 ----------
    section("스킬 컬럼 상태")
    cur.execute("""
        SELECT
          SUM(skills IS NULL OR skills = '') AS empty,
          COUNT(*) AS total
        FROM jobs
    """)
    r = cur.fetchone()
    filled = r["total"] - (r["empty"] or 0)
    print(f"  스킬 있음 : {filled:,} / {r['total']:,} ({filled / r['total'] * 100:.0f}%)" if r["total"] else "  (행 없음)")

    # ---------- crawl_runs ----------
    if "crawl_runs" in tables:
        section("crawl_runs 최근 5건")
        cur.execute("SELECT * FROM crawl_runs ORDER BY id DESC LIMIT 5")
        for r in cur.fetchall():
            print(f"  #{r.get('id')} {r.get('started_at')} ~ {r.get('finished_at')} "
                  f"status={r.get('status')} total={r.get('total_items')} "
                  f"ins={r.get('inserted_count')} upd={r.get('updated_count')} "
                  f"skip={r.get('skipped_count')} err={r.get('error_count')}")

    cur.close()
    conn.close()
    print("\n점검 완료 (쓰기 작업 없음)")


if __name__ == "__main__":
    main()
