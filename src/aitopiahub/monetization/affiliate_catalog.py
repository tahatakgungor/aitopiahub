from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AffiliateOffer:
    offer_id: str
    name: str
    provider: str
    commission_type: str
    base_url: str
    target_tags: tuple[str, ...]
    cta_templates: tuple[str, ...]


DEFAULT_OFFERS: tuple[AffiliateOffer, ...] = (
    AffiliateOffer(
        offer_id="notion_ai",
        name="Notion AI",
        provider="Notion",
        commission_type="trial_signup",
        base_url="https://www.notion.so/product/ai",
        target_tags=("productivity", "automation", "notes", "workflow", "ai"),
        cta_templates=(
            "Notlarını ve iş akışını hızlandırmak istersen bunu da inceleyebilirsin:",
            "Eğer pratik bir AI asistanı arıyorsan şu aracı da deneyebilirsin:",
        ),
    ),
    AffiliateOffer(
        offer_id="canva_magic",
        name="Canva Magic Studio",
        provider="Canva",
        commission_type="trial_signup",
        base_url="https://www.canva.com/magic-studio/",
        target_tags=("design", "content", "social", "marketing", "visual"),
        cta_templates=(
            "İçerik üretimini hızlandırmak için şu araca da göz at:",
            "Görsel üretim tarafında işini kolaylaştırabilecek bir alternatif:",
        ),
    ),
    AffiliateOffer(
        offer_id="grammarly",
        name="Grammarly",
        provider="Grammarly",
        commission_type="trial_signup",
        base_url="https://www.grammarly.com/",
        target_tags=("writing", "english", "communication", "editor", "ai"),
        cta_templates=(
            "Yazı kalitesini artırmak istersen bunu da test edebilirsin:",
            "Metin tarafında daha hızlı kalite almak isteyenler için:",
        ),
    ),
)


class AffiliateCatalog:
    def __init__(self, offers: tuple[AffiliateOffer, ...] | None = None):
        self._offers = offers or DEFAULT_OFFERS

    def list_offers(self) -> list[AffiliateOffer]:
        return list(self._offers)

    def get(self, offer_id: str) -> AffiliateOffer | None:
        for offer in self._offers:
            if offer.offer_id == offer_id:
                return offer
        return None
