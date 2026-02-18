from sqlalchemy.orm import Session
from sqlalchemy import text


def get_jobs(
    db: Session,
    skill: str | None,
    limit: int,
    offset: int,
):
    """
    공고 목록 조회
    - skill: 기술 키워드 (선택)
    - pagination: limit / offset
    """
    where_clause = ""
    params = {
        "limit": limit,
        "offset": offset,
    }

    if skill:
        where_clause = "WHERE j.skills LIKE :skill"
        params["skill"] = f"%{skill.lower()}%"

    sql = text(f"""
        SELECT
            j.id,
            c.name AS company,
            j.title,
            j.url,
            j.apply_type,
            j.skills,
            j.created_at,
            j.updated_at
        FROM jobs j
        LEFT JOIN companies c ON j.company_id = c.id
        {where_clause}
        ORDER BY j.created_at DESC
        LIMIT :limit OFFSET :offset
    """)

    return db.execute(sql, params).mappings().all()
