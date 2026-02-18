"""
채용 공고 상세 페이지 파싱 (크롤러 · 백필 공용).

Next.js 하이드레이션 페이로드(__next_f)의 JOBS 블록에서 구조화 필드
(근무지/경력/급여/근무조건)와 스킬 목록을 뽑는다. DB·네트워크·scrapy 에
의존하지 않는 순수 파싱 계층 — 크롤러 파이프라인과 backfill 스크립트가
같은 로직을 공유하도록 여기 한곳에 둔다.
"""
import json
import re

from lxml import html

# --------------------------------------------------------------- 지역
# 주소는 '대한민국' 접두어가 붙거나 시도 풀네임(경상남도 등)으로
# 오는 경우가 많다. 풀네임/약칭을 모두 짧은 시도명(DB 표준)으로 매핑한다.
SIDO_ALIASES = {
    "서울특별시": "서울", "서울": "서울",
    "부산광역시": "부산", "부산": "부산",
    "대구광역시": "대구", "대구": "대구",
    "인천광역시": "인천", "인천": "인천",
    "광주광역시": "광주", "광주": "광주",
    "대전광역시": "대전", "대전": "대전",
    "울산광역시": "울산", "울산": "울산",
    "세종특별자치시": "세종", "세종": "세종",
    "경기도": "경기", "경기": "경기",
    "강원특별자치도": "강원", "강원도": "강원", "강원": "강원",
    "충청북도": "충북", "충북": "충북",
    "충청남도": "충남", "충남": "충남",
    "전북특별자치도": "전북", "전라북도": "전북", "전북": "전북",
    "전라남도": "전남", "전남": "전남",
    "경상북도": "경북", "경북": "경북",
    "경상남도": "경남", "경남": "경남",
    "제주특별자치도": "제주", "제주도": "제주", "제주": "제주",
}
# 긴 별칭 우선 매칭(풀네임이 약칭보다 먼저 걸리도록).
_SIDO_ALIASES_SORTED = sorted(SIDO_ALIASES, key=len, reverse=True)

# --------------------------------------------------------------- 스킬
# 공고 skills 배열에는 기술스택과 인성 키워드가 섞여 들어온다.
# 5만 건 백필 후 전수 점검한 결과, '순수 한글 = 인성' 접미사 규칙은 오판이 잦았다
# (자바/리눅스/딥러닝/백엔드가 인성으로 빠지고, 스트레스관리가 기술로 남았다).
# → 인성어는 종류가 유한하므로 명시적 블랙리스트로 전환한다. 목록에 없으면 기술.
SOFT_SKILLS = {
    # 성향/태도
    "계획성", "성실성", "협동심", "꼼꼼함", "적응성", "창의성", "책임감", "적극성",
    "친화력", "리더십", "도전정신", "열정", "인내심", "긍정적", "정직성", "배려심",
    "신속성", "유연성", "자기주도성", "판단력", "집중력", "이해력", "명확성", "정확성",
    "원만한대인관계", "밝은성격", "친절함", "예의바름", "화합", "성장지향성", "성취지향성",
    "윤리의식", "고객지향성", "목표지향성", "메타인지", "자기개발", "글로벌마인드",
    "주인의식", "소통능력", "스트레스관리", "자존감", "도전정신",
    # 역량 표현(직무 스킬 아님)
    "커뮤니케이션능력", "의사소통능력", "논리적사고", "분석력", "기획력", "추진력",
    "프레젠테이션", "문제해결", "문제해결능력", "협업", "리더십역량", "커뮤니케이션",
}

# 순수 한글이라 인성으로 오인되기 쉽지만 실제로는 기술/직무 스킬인 항목.
# blacklist 방식에서는 굳이 필요 없지만, 문서화 목적으로 남긴다.
TECH_OVERRIDE = {
    "전자정부표준프레임워크", "정보처리기사", "형상관리", "보안", "네트워크관리",
    "풀스택", "임베디드리눅스", "딥러닝", "머신러닝", "자바", "리눅스", "백엔드",
    "프론트엔드", "빅데이터", "모의해킹", "정보보안", "컴퓨터비전", "데이터분석",
    "데이터시각화", "데이터마이닝", "웹개발", "자율주행", "펌웨어", "미들웨어",
}

# job_details 적재 컬럼 순서 (job_id 는 별도). 크롤러/백필이 공유한다.
DETAIL_COLS = [
    "posting_id", "status_type", "is_deleted", "address", "sido", "sigungu",
    "latitude", "longitude", "career_type", "career_min", "career_max",
    "education_code", "graduation_type", "pay_type", "pay_from", "pay_to",
    "pay_is_placeholder", "work_week_type", "work_start", "work_end",
    "benefit_count", "subway_count", "subway_min_dist",
    "posted_at", "closes_at",
]


def _date_only(v):
    """ISO 문자열('2026-08-05T17:03:39+09:00')에서 날짜(YYYY-MM-DD)만 뽑는다."""
    if not v or not isinstance(v, str):
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2})", v)
    return m.group(1) if m else None


def is_tech_skill(name: str) -> bool:
    """기술스택과 인성 키워드를 분리한다. 원천은 둘을 같은 배열로 준다.
    블랙리스트 방식: SOFT_SKILLS 에 있으면 인성, 그 외 전부 기술."""
    n = name.strip()
    if n in SOFT_SKILLS:
        return False
    return True


def split_address(addr):
    """'대한민국 경기도 성남시 분당구 ...' -> ('경기', '성남시')

    '대한민국'/'한국' 접두어를 걷어내고 시도 풀네임/약칭을 함께 매칭한다.
    해외 주소(예: '일본 도쿄')는 매칭 실패 → (None, None).
    """
    if not addr:
        return None, None
    parts = addr.replace(",", " ").split()
    while parts and parts[0] in ("대한민국", "한국"):
        parts.pop(0)
    if not parts:
        return None, None
    first = parts[0]
    sido = None
    for alias in _SIDO_ALIASES_SORTED:
        if first.startswith(alias):
            sido = SIDO_ALIASES[alias]
            break
    if sido is None:
        return None, None
    sigungu = parts[1] if len(parts) > 1 and re.search(r"(시|군|구)$", parts[1]) else None
    return sido, sigungu


def posting_id_of(url):
    """추적 파라미터를 제거한 공고 고유키. 패턴은 .env 의 TARGET_POSTING_ID_REGEX."""
    from devhire_crawler.utils.target import posting_id_pattern

    m = posting_id_pattern().search(url or "")
    return m.group(1) if m else None


def extract_jobs_block(page_html):
    """Next.js 하이드레이션 페이로드(__next_f)에서 JOBS 쿼리 데이터를 꺼낸다.

    page_html: 상세 페이지 HTML 문자열 (scrapy response.text / urllib 응답 모두 가능).
    실패 시 None.
    """
    doc = html.fromstring(page_html)
    for script in doc.xpath("//script[contains(., '__next_f.push')]/text()"):
        if "queryKey" not in script or "JOBS" not in script:
            continue
        m = re.search(r'self\.__next_f\.push\(\[1,\s*"(.*?)"\]\)', script, re.S)
        if not m:
            continue
        try:
            decoded = bytes(m.group(1), "utf-8").decode("unicode_escape").encode("latin1").decode("utf-8")
            i = decoded.find('"state":')
            if i == -1:
                continue
            part = "{" + decoded[i:]
            part = part[:part.rfind("}") + 1]
            for q in json.loads(part)["state"]["queries"]:
                if q["queryKey"][0] == "JOBS":
                    return q["state"]["data"]
        except Exception:
            continue
    return None


def parse_detail(job_data):
    """JOBS 블록 -> (job_details 컬럼 dict, 스킬명 목록)."""
    base = job_data.get("base") or {}
    wc = base.get("workCondition") or {}
    wp = wc.get("workplace") or {}
    req = base.get("requirement") or {}

    d = {
        "status_type": base.get("statusType"),
        "is_deleted": 1 if base.get("deleted") else 0,
    }

    # 게시/마감일 — 구조화 데이터의 실제 공고 날짜(시계열용). CLOSE 공고도 유지된다.
    post = base.get("post") or {}
    d["posted_at"] = _date_only(post.get("postingStartAt") or post.get("firstPostedAt"))
    d["closes_at"] = _date_only(post.get("postingEndAt"))

    # 근무지
    locs = wp.get("locationAttributes") or []
    if locs:
        loc = locs[0]
        d["address"] = (loc.get("fullAddress") or loc.get("address") or "").strip()[:300] or None
        d["latitude"] = loc.get("latitude")
        d["longitude"] = loc.get("longitude")
        d["sido"], d["sigungu"] = split_address(d["address"])

    # 경력 — range.from/to 는 정수 연차. 문자열로 뭉개지 않는다.
    careers = req.get("careers") or []
    if careers:
        c0 = careers[0]
        d["career_type"] = c0.get("type")
        rng = c0.get("range") or {}
        d["career_min"] = rng.get("from")
        d["career_max"] = rng.get("to")
    d["education_code"] = req.get("educationCode")
    d["graduation_type"] = req.get("graduationType")

    # 급여 — 단위가 payType 에 따라 다르므로 반드시 함께 저장
    pay = wc.get("pay") or {}
    d["pay_type"] = pay.get("payType")
    pr = pay.get("payRange") or {}
    d["pay_from"] = pr.get("from")
    d["pay_to"] = pr.get("to")
    # to = from + 1 은 실제 범위가 아니라 '이상' 의 관례적 표기 → 집계 제외 플래그
    d["pay_is_placeholder"] = (
        1 if (d["pay_from"] is not None and d["pay_to"] is not None
              and d["pay_to"] - d["pay_from"] <= 1) else 0
    )

    # 근무 조건
    ws = wc.get("workSchedule") or {}
    d["work_week_type"] = ws.get("workWeekType")
    hours = ws.get("workHoursRanges") or []
    if hours:
        d["work_start"] = hours[0].get("startTime")
        d["work_end"] = hours[0].get("endTime")
    d["benefit_count"] = len(wc.get("benefitCodes") or [])

    subways = wp.get("nearbySubwayAttributes") or []
    d["subway_count"] = len(subways)
    dists = [s.get("distance") for s in subways if s.get("distance") is not None]
    d["subway_min_dist"] = min(dists) if dists else None

    # 스킬
    skills = ((job_data.get("extension") or {}).get("common") or {}).get("skills") or []
    names = [s.get("name", "").strip() for s in skills if s.get("name")]

    return d, names


def build_skill_rows(job_id, names):
    """스킬명 목록 -> job_skills 적재 행 [(job_id, skill, skill_norm, is_tech)].
    소문자 정규화 키로 중복 제거."""
    rows, seen = [], set()
    for name in names or []:
        norm = name.lower().strip()
        if not norm or norm in seen:
            continue
        seen.add(norm)
        rows.append((job_id, name[:100], norm[:100], 1 if is_tech_skill(name) else 0))
    return rows
