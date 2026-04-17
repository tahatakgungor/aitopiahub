from __future__ import annotations

import hashlib
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse


class LinkTracker:
    """UTM üretimi + kısa kod map kaydı."""

    def __init__(self, redis, account_handle: str, campaign: str):
        self.redis = redis
        self.account_handle = account_handle
        self.campaign = campaign

    @staticmethod
    def _append_query(base_url: str, params: dict[str, str]) -> str:
        parsed = urlparse(base_url)
        query = dict(parse_qsl(parsed.query))
        query.update(params)
        return urlunparse(parsed._replace(query=urlencode(query)))

    async def build_tracking_url(
        self,
        offer_id: str,
        base_url: str,
        keyword: str,
        draft_id: str,
    ) -> tuple[str, str]:
        utm_url = self._append_query(
            base_url,
            {
                "utm_source": "instagram",
                "utm_medium": "social",
                "utm_campaign": self.campaign,
                "utm_content": offer_id,
                "utm_term": keyword[:50],
            },
        )
        code_raw = f"{self.account_handle}:{offer_id}:{draft_id}"
        code = hashlib.sha1(code_raw.encode("utf-8")).hexdigest()[:10]

        await self.redis.hset(
            f"link_map:{self.account_handle}",
            code,
            utm_url,
        )
        await self.redis.hset(
            f"link_meta:{self.account_handle}",
            code,
            f"{offer_id}|{draft_id}",
        )

        return code, utm_url

    async def resolve(self, code: str) -> str | None:
        return await self.redis.hget(f"link_map:{self.account_handle}", code)

    async def register_click(self, code: str) -> None:
        await self.redis.hincrby(f"affiliate_clicks:{self.account_handle}", code, 1)
