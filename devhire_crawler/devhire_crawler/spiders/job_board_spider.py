import json
import os

import scrapy

from devhire_crawler.items import JobItem
from devhire_crawler.utils import target
from devhire_crawler.utils.detail_parser import (
    extract_jobs_block,
    parse_detail as parse_detail_fields,
    posting_id_of,
)


class JobBoardSpider(scrapy.Spider):
    name = "jobboard"

    custom_settings = {
        "DOWNLOAD_DELAY": 2,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "CONCURRENT_REQUESTS": 1,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "LOG_LEVEL": "DEBUG",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = target.spider_name()
        self.allowed_domains = target.allowed_domains()
        self._list_url = target.list_url()

    def start_requests(self):
        yield self.make_request(1)

    def make_request(self, page):
        return scrapy.FormRequest(
            url=self._list_url,
            method="POST",
            formdata=target.list_form(page),
            headers={
                "User-Agent": self.settings.get("USER_AGENT"),
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "text/html, */*; q=0.01",
            },
            callback=self.parse,
            meta={"page": page},
            dont_filter=True,
        )

    def parse(self, response):
        page = response.meta["page"]
        rows = response.xpath("//tbody/tr")

        if not rows:
            self.logger.warning("데이터 없음. 수집 종료")
            return

        for row in rows:
            item = JobItem(
                company=row.xpath(".//td[1]//a/text()").get(),
                title=row.xpath(".//td[2]//strong/a/text()").get(),
                url=response.urljoin(
                    row.xpath(".//td[2]//strong/a/@href").get()
                ),
                apply_type=row.xpath(".//td[4]//button//span/text()").get(),
            )

            yield response.follow(
                url=item["url"],
                callback=self.parse_detail,
                meta={"item": item},
            )
        yield self.make_request(page + 1)

    def parse_detail(self, response):
        item = response.meta["item"]
        item["posting_id"] = posting_id_of(item.get("url"))

        job_data = extract_jobs_block(response.text)

        if not job_data:
            self.logger.warning(f"상세 페이로드 없음: {item.get('url')}")
            item["detail"] = None
            item["skill_names"] = []
            yield item
            return

        try:
            item["company"] = job_data.get("base", {}).get("post", {}).get("postingCompanyName")

            skill_list = []
            extension_skills = job_data.get("extension", {}).get("common", {}).get("skills", [])
            for s in extension_skills:
                name = s.get("name")
                if name:
                    skill_list.append(name.strip().lower())
            item["skills"] = "|".join(skill_list)

            requirement = job_data.get("requirement", {})
            experience = "경력" if requirement.get("careers") else None
            education = requirement.get("educationCode")
            pref_list = job_data.get("extension", {}).get("common", {}).get("preferences", [])
            preferences = {}
            if pref_list:
                preferences["기본우대"] = [p.get("name") for p in pref_list if p.get("name")]
            desc = {
                "experience": experience,
                "education": education,
                "core_competencies": None,
                "preferences": preferences if preferences else None,
            }
            desc = {k: v for k, v in desc.items() if v}
            item["description"] = json.dumps(desc, ensure_ascii=False)

            fields, names = parse_detail_fields(job_data)
            item["detail"] = fields
            item["skill_names"] = names

            yield item

        except Exception as e:
            self.logger.exception(f"parse_detail 실패 | {item.get('url')} | {e}")
