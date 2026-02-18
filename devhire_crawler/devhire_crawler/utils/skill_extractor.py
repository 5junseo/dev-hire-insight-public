# devhire_crawler/utils/skill_extractor.py

import re
from .skill_map import SKILL_ALIASES

# 단어 경계가 필요한 짧은 키워드
SHORT_KEYWORDS = {
    "c", "go", "js", "ts"
}

def _contains_word(text: str, word: str) -> bool:
    """
    단어 경계 기반 매칭 (영문/숫자)
    """
    pattern = rf"\b{re.escape(word)}\b"
    return re.search(pattern, text) is not None


def extract_skills(description: str) -> str:
    if not description:
        return ""

    text = description.lower()
    found = set()

    for standard, aliases in SKILL_ALIASES.items():
        for alias in aliases:
            alias_l = alias.lower()

            # 짧은 키워드 → 엄격 매칭
            if standard in SHORT_KEYWORDS or alias_l in SHORT_KEYWORDS:
                if _contains_word(text, alias_l):
                    found.add(standard)
                    break
            else:
                if alias_l in text:
                    found.add(standard)
                    break

    return "|".join(sorted(found))
