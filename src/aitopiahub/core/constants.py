from enum import StrEnum


class AccountNiche(StrEnum):
    NEWS = "news"
    SPOR = "spor"
    ANIMAL = "animal"
    ENTERTAINMENT = "entertainment"


class PostFormat(StrEnum):
    SINGLE = "single"
    CAROUSEL = "carousel"
    STORY = "story"
    SHORT_SCRIPT = "short_script"


class PostStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    QUEUED = "queued"
    POSTED = "posted"
    REJECTED = "rejected"
    FAILED = "failed"


class ContentAngle(StrEnum):
    INFORMATIVE = "informative"   # Bilgilendirici / analitik
    ENGAGING = "engaging"         # Soru / engagement-bait


class ImageProvider(StrEnum):
    POLLINATIONS = "pollinations"
    PILLOW_TEMPLATE = "pillow_template"


class TemplateType(StrEnum):
    BREAKING_NEWS = "breaking_news"
    ANALYSIS = "analysis"
    STAT_CARD = "stat_card"
    QUOTE_CARD = "quote_card"


class Language(StrEnum):
    TR = "tr"
    EN = "en"
