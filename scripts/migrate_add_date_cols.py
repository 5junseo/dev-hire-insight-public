"""job_details 에 posted_at / closes_at 컬럼 추가 (일회성, 멱등).

크롤/백필이 게시일을 쓰기 전에 한 번 실행한다. MariaDB 의 IF NOT EXISTS 로
이미 있으면 건너뛴다. 사용: python scripts/migrate_add_date_cols.py
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

url = (
    f"mysql+pymysql://{os.getenv('DB_USER')}:{quote_plus(os.getenv('DB_PASSWORD'))}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT', '3306')}/{os.getenv('DB_NAME')}?charset=utf8mb4"
)
engine = create_engine(url)
stmts = [
    "ALTER TABLE job_details ADD COLUMN IF NOT EXISTS posted_at DATE NULL COMMENT '게시 시작일' AFTER is_deleted",
    "ALTER TABLE job_details ADD COLUMN IF NOT EXISTS closes_at DATE NULL COMMENT '마감일' AFTER posted_at",
    "ALTER TABLE job_details ADD INDEX IF NOT EXISTS idx_posted (posted_at)",
]
with engine.begin() as conn:
    for s in stmts:
        conn.execute(text(s))
        print("OK:", s.split("job_details ")[1][:60])
print("완료 — 이제 크롤/백필이 posted_at/closes_at 를 채운다.")
