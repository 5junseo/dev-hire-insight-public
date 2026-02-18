import re

NOISE_REGEXES = [
    r"남은기간\|[0-9일 :]+",
    r"시작일\|\d{4}\.\d{2}\.\d{2}.*?",
    r"마감일\|\d{4}\.\d{2}\.\d{2}.*?",
    r"추천공고\|[^|]+",
    r"[^|]+채용관",
    r"지도보기",
]

def normalize_description(desc: str) -> str:
    text = desc or ""

    for reg in NOISE_REGEXES:
        text = re.sub(reg, "", text)

    # 숫자 흔들림 제거 (시간/카운트)
    text = re.sub(r"\d+", "", text)

    # 구분자 / 공백 정리
    text = re.sub(r"\|+", "|", text)
    text = re.sub(r"\s+", " ", text).strip("| ").strip()

    return text
