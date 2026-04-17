from __future__ import annotations

import random

from aitopiahub.monetization.affiliate_catalog import AffiliateOffer


class CTAInjector:
    """Caption sonuna tek ve doğal CTA ekler."""

    def inject(self, caption: str, offer: AffiliateOffer, tracking_url: str) -> tuple[str, str]:
        clean = (caption or "").strip()
        cta_line = random.choice(offer.cta_templates)
        variant = "soft_value_cta"

        # Birden fazla CTA riskini azaltmak için mevcut satış cümlelerini törpüle.
        normalized = clean.replace("satın al", "incele").replace("hemen dene", "denemek istersen")

        disclosure = "(Not: Bu bağlantı affiliate olabilir.)"
        addition = f"{cta_line} {tracking_url}\n{disclosure}"

        if addition in normalized:
            return normalized, variant

        merged = f"{normalized}\n\n{addition}".strip()
        return merged, variant
