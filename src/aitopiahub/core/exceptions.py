class AitopiahubError(Exception):
    """Base exception."""


class TrendFetchError(AitopiahubError):
    """Trend verisi çekilemedi."""


class ContentGenerationError(AitopiahubError):
    """İçerik üretilemedi."""


class ContentQualityError(AitopiahubError):
    """İçerik kalite eşiğini geçemedi."""


class SafetyCheckError(AitopiahubError):
    """İçerik güvenlik kontrolünden geçemedi."""


class DuplicateContentError(AitopiahubError):
    """İçerik daha önce paylaşıldı."""


class ImageGenerationError(AitopiahubError):
    """Görsel üretilemedi."""


class PublishError(AitopiahubError):
    """Instagram'a yayınlama başarısız."""


class RateLimitError(AitopiahubError):
    """API rate limit aşıldı."""


class LLMError(AitopiahubError):
    """LLM çağrısı başarısız."""


class QualityGateError(AitopiahubError):
    """Publish öncesi kalite kapısı içerik akışını durdurdu."""
