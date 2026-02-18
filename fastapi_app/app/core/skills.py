from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text

# =========================
# Skill Aliases (표준 키 -> alias 목록)
# =========================
SKILL_ALIASES = {
    # Backend
    "python": ["python", "파이썬"],
    "java": ["java", "자바"],
    "kotlin": ["kotlin"],
    "go": ["go", "golang"],
    "php": ["php"],
    "nodejs": ["node.js", "nodejs", "node js", "노드", "노드js"],
    "spring": ["spring", "spring boot", "스프링", "스프링부트"],
    "django": ["django"],
    "flask": ["flask"],
    "fastapi": ["fastapi"],
    "nestjs": ["nestjs", "nest js"],
    "express": ["express"],

    # Frontend
    "javascript": ["javascript", "자바스크립트"],
    "typescript": ["typescript"],
    "react": ["react", "리액트"],
    "vue": ["vue", "vue.js"],
    "angular": ["angular"],
    "nextjs": ["next.js", "nextjs"],
    "nuxt": ["nuxt"],
    "svelte": ["svelte"],

    # Mobile
    "android": ["android", "안드로이드"],
    "ios": ["ios"],
    "swift": ["swift"],
    "flutter": ["flutter"],

    # DB
    "mysql": ["mysql"],
    "mariadb": ["mariadb"],
    "postgresql": ["postgresql", "postgres"],
    "oracle": ["oracle"],
    "mssql": ["mssql", "sql server"],
    "mongodb": ["mongodb", "mongo"],
    "redis": ["redis"],
    "elasticsearch": ["elasticsearch", "elastic"],

    # DevOps
    "docker": ["docker", "도커"],
    "kubernetes": ["kubernetes", "k8s", "쿠버네티스"],
    "aws": ["aws", "아마존웹서비스"],
    "gcp": ["gcp"],
    "azure": ["azure"],

    # Data / AI
    "pandas": ["pandas"],
    "numpy": ["numpy"],
    "tensorflow": ["tensorflow"],
    "pytorch": ["pytorch"],
    "scikit-learn": ["scikit learn", "sklearn"],
    "spark": ["spark"],
    "hadoop": ["hadoop"],
    "data-mining": ["data mining", "데이터마이닝"],

    # ETC
    "linux": ["linux", "리눅스"],
    "git": ["git", "깃"],
    "msa": ["msa", "microservice", "마이크로서비스"],
    "crawling": ["crawling", "scraping", "크롤링", "웹크롤링"],
    "c": ["c", "c언어"],
    "cpp": ["c++"],
    "csharp": ["c#", "csharp"],
}


# =========================
# Trends: Companies
# =========================
def get_company_trends(db: Session, days: int = 7, top: int = 20):
    """
    최근 N일 기준 회사별 공고 수 TOP N
    반환 형태: [{"key": 회사명, "count": n}, ...]
    """
    since = datetime.now() - timedelta(days=days)

    sql = text("""
        SELECT
            c.name AS `key`,
            COUNT(*) AS `count`
        FROM jobs j
        JOIN companies c ON j.company_id = c.id
        WHERE j.created_at >= :since
        GROUP BY c.name
        ORDER BY `count` DESC
        LIMIT :top
    """)

    rows = db.execute(sql, {"since": since, "top": top}).mappings().all()
    return rows


# =========================
# Trends: Skills
# =========================
def get_skill_trends(db: Session, days: int = 7, top: int = 20):
    """
    최근 N일 기준 기술별 공고 수 TOP N (alias 합산)
    반환 형태: [{"key": skill_key, "count": n}, ...]
    """
    since = datetime.now() - timedelta(days=days)

    # alias마다 COUNT(*) 합산
    sql = text("""
        SELECT COUNT(*) AS cnt
        FROM jobs
        WHERE created_at >= :since
          AND skills LIKE :pattern
    """)

    results = []

    for skill, aliases in SKILL_ALIASES.items():
        total_count = 0

        for alias in aliases:
            cnt = db.execute(
                sql,
                {"since": since, "pattern": f"%{alias}%"}
            ).scalar() or 0

            total_count += cnt

        if total_count > 0:
            results.append({"key": skill, "count": total_count})

    results.sort(key=lambda x: x["count"], reverse=True)
    return results[:top]
