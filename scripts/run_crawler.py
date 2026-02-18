# scripts/run_crawler.py
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import pymysql
from dotenv import load_dotenv
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings


def run():
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(BASE_DIR, ".env"))

    SCRAPY_PROJECT_DIR = os.path.join(BASE_DIR, "devhire_crawler")
    os.chdir(SCRAPY_PROJECT_DIR)

    if SCRAPY_PROJECT_DIR not in sys.path:
        sys.path.insert(0, SCRAPY_PROJECT_DIR)

    from devhire_crawler.spiders.job_board_spider import JobBoardSpider
    from devhire_crawler.utils import target

    db_host = os.getenv("DB_HOST")
    db_user = os.getenv("DB_USER")
    db_pw = os.getenv("DB_PASSWORD")
    db_name = os.getenv("DB_NAME")

    conn = pymysql.connect(
        host=db_host,
        user=db_user,
        password=db_pw,
        database=db_name,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )
    cur = conn.cursor()

    spider = target.spider_name()
    started_at = datetime.now(ZoneInfo("Asia/Seoul"))
    cur.execute(
        "INSERT INTO crawl_runs (spider_name, started_at) VALUES (%s, %s)",
        (spider, started_at),
    )
    os.environ["CRAWL_RUN_ID"] = str(cur.lastrowid)

    settings = get_project_settings()
    process = CrawlerProcess(settings)
    process.crawl(JobBoardSpider)
    process.start()

    finished_at = datetime.now(ZoneInfo("Asia/Seoul"))
    cur.execute(
        "UPDATE crawl_runs SET finished_at=%s, status='FINISHED' WHERE id=%s",
        (finished_at, os.environ["CRAWL_RUN_ID"]),
    )

    cur.close()
    conn.close()


if __name__ == "__main__":
    run()
