import os
from datetime import datetime

import pymysql
from pymysql.cursors import DictCursor
from dotenv import load_dotenv

from devhire_crawler.utils.description_normalizer import normalize_description
from devhire_crawler.utils.hash_utils import make_hash
from devhire_crawler.utils.detail_parser import DETAIL_COLS, build_skill_rows

load_dotenv()

class MariaDBPipeline:

    def open_spider(self, spider):
        self.conn = pymysql.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            charset="utf8mb4",
            autocommit=False,
            cursorclass=DictCursor,
        )
        self.cursor = self.conn.cursor()

        run_id = os.getenv("CRAWL_RUN_ID")
        self.run_id = int(run_id) if run_id else None

        self.stats = {
            "total": 0,
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
            "error": 0,
        }

    def close_spider(self, spider):
        self.cursor.execute(
            """
            UPDATE crawl_runs
            SET
                total_items=%s,
                inserted_count=%s,
                updated_count=%s,
                skipped_count=%s,
                error_count=%s
            WHERE id=%s
            """,
            (
                self.stats["total"],
                self.stats["inserted"],
                self.stats["updated"],
                self.stats["skipped"],
                self.stats["error"],
                self.run_id,
            ),
        )
        self.conn.commit()
        self.cursor.close()
        self.conn.close()

    def process_item(self, item, spider):
        self.stats["total"] += 1

        try:
            # 1️⃣ 회사 처리
            company_id = self._get_or_create_company(item["company"])

            # 2️⃣ 기존 공고 조회
            existing = self._get_existing_job(item["url"])

            # 3️⃣ description 정규화 + 해시 생성
            raw_desc = item.get("description", "")
            normalized_desc = normalize_description(raw_desc)
            new_desc_hash = make_hash(normalized_desc)

            # =========================
            # 신규 공고
            # =========================
            if not existing:
                item["desc_hash"] = new_desc_hash

                self._insert_job(item, company_id)
                self._write_detail(self.cursor.lastrowid, item)
                self.stats["inserted"] += 1
                self.conn.commit()
                return item

            # =========================
            # 기존 공고
            # =========================
            old_desc_hash = existing.get("desc_hash")

            # 🔴 RULE 1: description 의미 동일 → 무조건 스킵
            if old_desc_hash == new_desc_hash:
                self.stats["skipped"] += 1
                self.conn.commit()
                return item

            # 4️⃣ 필드 diff 계산 (의미 변경일 때만)
            diff = self._diff_job(existing, item)

            # 🔴 RULE 2: diff가 없으면 스킵
            if not diff:
                self.stats["skipped"] += 1
                self.conn.commit()
                return item

            # 🔴 RULE 3: skills + description 오탐 방지
            if set(diff.keys()) <= {"description", "skills"}:
                old_skills = self._normalize_skills(existing.get("skills"))
                new_skills = self._normalize_skills(item.get("skills"))

                if old_skills == new_skills:
                    # description 노이즈로 인한 연쇄 변경
                    self.stats["skipped"] += 1
                    self.conn.commit()
                    return item

            # =========================
            # 의미 있는 변경 → UPDATE
            # =========================
            item["desc_hash"] = new_desc_hash

            self._update_job(existing["id"], item, company_id)
            self._log_job_update(existing["id"], item["url"], diff)
            self._write_detail(existing["id"], item)

            self.stats["updated"] += 1
            self.conn.commit()
            return item

        except Exception:
            self.conn.rollback()
            self.stats["error"] += 1
            raise

    # ---------- helpers ----------

    def _write_detail(self, job_id, item):
        """크롤 시점에 job_details / job_skills 를 함께 적재한다.

        detail 이 None(파싱 실패)이면 NO_DATA 로 남겨 백필(--retry-errors)
        재시도 대상으로 둔다. raw_json 은 건드리지 않는다(백필 --save-raw 전용).
        """
        detail = item.get("detail")
        if detail is None:
            status, fields, names = "NO_DATA", {}, []
        else:
            status, fields, names = "OK", detail, item.get("skill_names") or []

        # DETAIL_COLS + backfill_status, backfill_error, backfilled_at, raw_json, job_id
        vals = [item.get("posting_id")] + [fields.get(c) for c in DETAIL_COLS[1:]]
        vals += [status, None, datetime.now(), None, job_id]
        placeholders = ", ".join(["%s"] * (len(DETAIL_COLS) + 5))
        updates = ", ".join(f"{c}=VALUES({c})" for c in DETAIL_COLS)
        self.cursor.execute(
            f"""INSERT INTO job_details
                  ({', '.join(DETAIL_COLS)}, backfill_status, backfill_error, backfilled_at, raw_json, job_id)
                VALUES ({placeholders})
                ON DUPLICATE KEY UPDATE
                  {updates},
                  backfill_status=VALUES(backfill_status),
                  backfill_error=VALUES(backfill_error),
                  backfilled_at=VALUES(backfilled_at)""",
            vals,
        )

        # 스킬 전량 교체 (재크롤 시 중복/잔여 방지)
        if status == "OK":
            self.cursor.execute("DELETE FROM job_skills WHERE job_id=%s", (job_id,))
            rows = build_skill_rows(job_id, names)
            if rows:
                self.cursor.executemany(
                    """INSERT INTO job_skills (job_id, skill, skill_norm, is_tech)
                       VALUES (%s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE skill=VALUES(skill), is_tech=VALUES(is_tech)""",
                    rows,
                )

    def _get_or_create_company(self, name):
        self.cursor.execute(
            """
            INSERT INTO companies (name)
            VALUES (%s)
            ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)
            """,
            (name,),
        )
        return self.cursor.lastrowid

    def _get_existing_job(self, url):
        self.cursor.execute(
            """
            SELECT id, title, apply_type, skills, description, desc_hash
            FROM jobs
            WHERE url=%s
            ORDER BY id DESC
            LIMIT 1
            """,
            (url,),
        )
        return self.cursor.fetchone()

    def _diff_job(self, old, new):
        changed = {}
        for f in ["title", "apply_type", "skills", "description"]:
            old_v = (old.get(f) or "").strip()
            new_v = (new.get(f) or "").strip()
            if old_v != new_v:
                changed[f] = (old_v, new_v)
        return changed

    def _insert_job(self, item, company_id):
        self.cursor.execute(
            """
            INSERT INTO jobs
                (company_id, title, url, apply_type, skills, description, desc_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                company_id,
                item["title"],
                item["url"],
                item.get("apply_type"),
                item.get("skills"),
                item.get("description"),
                item.get("desc_hash"),
            ),
        )

    def _update_job(self, job_id, item, company_id):
        self.cursor.execute(
            """
            UPDATE jobs
            SET
                company_id=%s,
                title=%s,
                apply_type=%s,
                skills=%s,
                description=%s,
                desc_hash=%s
            WHERE id=%s
            """,
            (
                company_id,
                item["title"],
                item.get("apply_type"),
                item.get("skills"),
                item.get("description"),
                item.get("desc_hash"),
                job_id,
            ),
        )

    def _log_job_update(self, job_id, url, diff):
        self.cursor.execute(
            """
            INSERT INTO job_update_logs
                (job_id, url, changed_fields, before_data, after_data)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                job_id,
                url,
                ",".join(diff.keys()),
                "\n".join([f"{k}: {v[0]}" for k, v in diff.items()]),
                "\n".join([f"{k}: {v[1]}" for k, v in diff.items()]),
            ),
        )

    def _normalize_skills(self, skills):
        if not skills:
            return []
        return sorted(
            set(s.strip().lower() for s in skills.split(",") if s.strip())
        )