import scrapy

class JobItem(scrapy.Item):
    company = scrapy.Field()
    title = scrapy.Field()
    url = scrapy.Field()
    apply_type = scrapy.Field()

    description = scrapy.Field()
    skills = scrapy.Field()
    desc_hash = scrapy.Field()

    # 상세 파싱 결과 — job_details / job_skills 적재용
    posting_id = scrapy.Field()    # 상세 URL에서 뽑은 공고 고유키
    detail = scrapy.Field()        # parse_detail 필드 dict (None 이면 파싱 실패 → NO_DATA)
    skill_names = scrapy.Field()   # 원본 스킬명 목록