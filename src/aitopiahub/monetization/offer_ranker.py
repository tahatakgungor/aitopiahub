from __future__ import annotations

from dataclasses import dataclass

from aitopiahub.monetization.affiliate_catalog import AffiliateOffer


@dataclass
class RankedOffer:
    offer: AffiliateOffer
    commercial_intent_score: float


class OfferRanker:
    """Trend keyword + içerik bağlamına göre offer sıralar."""

    def rank(
        self,
        offers: list[AffiliateOffer],
        keyword: str,
        caption: str,
        limit: int = 3,
    ) -> list[RankedOffer]:
        haystack = f"{keyword} {caption}".lower()
        ranked: list[RankedOffer] = []

        for offer in offers:
            score = 0.15
            for tag in offer.target_tags:
                if tag.lower() in haystack:
                    score += 0.2
            if "ai" in haystack and "ai" in [t.lower() for t in offer.target_tags]:
                score += 0.15
            if "rehber" in haystack or "guide" in haystack:
                score += 0.1
            ranked.append(RankedOffer(offer=offer, commercial_intent_score=min(score, 1.0)))

        ranked.sort(key=lambda x: x.commercial_intent_score, reverse=True)
        return ranked[:limit]
