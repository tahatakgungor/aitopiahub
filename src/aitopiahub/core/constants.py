from enum import Enum


class AccountNiche(str, Enum):
    NEWS = "news"
    SPOR = "spor"
    ANIMAL = "animal"
    ENTERTAINMENT = "entertainment"


class PostFormat(str, Enum):
    SINGLE = "single"
    CAROUSEL = "carousel"
    STORY = "story"
    SHORT_SCRIPT = "short_script"
    LONG_EPISODE = "long_episode"


class PostStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    QUEUED = "queued"
    POSTED = "posted"
    REJECTED = "rejected"
    FAILED = "failed"


class ContentAngle(str, Enum):
    INFORMATIVE = "informative"   # Bilgilendirici / analitik
    ENGAGING = "engaging"         # Soru / engagement-bait


class ImageProvider(str, Enum):
    POLLINATIONS = "pollinations"
    PILLOW_TEMPLATE = "pillow_template"


class TemplateType(str, Enum):
    BREAKING_NEWS = "breaking_news"
    ANALYSIS = "analysis"
    STAT_CARD = "stat_card"
    QUOTE_CARD = "quote_card"


class Language(str, Enum):
    TR = "tr"
    EN = "en"
