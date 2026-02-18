"""수집 대상은 코드가 아니라 .env 에 둔다.

실제 도메인·목록 URL·카테고리 ID 는 저장소에 넣지 않는다.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_ROOT / ".env")


def _get(key: str, default: str = "") -> str:
    return (os.getenv(key) or default).strip()


def require(key: str) -> str:
    v = _get(key)
    if not v:
        raise RuntimeError(
            f".env 에 {key} 가 없습니다. 루트 .env.example 을 복사해 채우세요."
        )
    return v


def spider_name() -> str:
    return _get("TARGET_SPIDER_NAME", "jobboard") or "jobboard"


def allowed_domains() -> list[str]:
    return [require("TARGET_ALLOWED_DOMAIN")]


def list_url() -> str:
    return require("TARGET_LIST_URL")


def list_form(page: int) -> dict[str, str]:
    return {
        "page": str(page),
        "pagesize": _get("TARGET_LIST_PAGESIZE", "50") or "50",
        "order": _get("TARGET_LIST_ORDER", "50") or "50",
        require("TARGET_FORM_MENU_KEY"): _get("TARGET_LIST_MENUCODE", "duty") or "duty",
        require("TARGET_FORM_CATEGORY_KEY"): require("TARGET_LIST_CATEGORY"),
    }


def posting_id_pattern() -> re.Pattern[str]:
    return re.compile(require("TARGET_POSTING_ID_REGEX"))


def detail_path() -> str:
    return require("TARGET_DETAIL_PATH")
