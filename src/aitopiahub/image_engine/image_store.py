"""
Görsel depolama — local dosya sistemi (dev) veya S3 (prod).
"""

from __future__ import annotations

import uuid
from pathlib import Path

from aitopiahub.core.config import get_settings
from aitopiahub.core.logging import get_logger

log = get_logger(__name__)


class ImageStore:
    """Görsel byte'larını diske yazar, public URL döndürür."""

    def __init__(self):
        settings = get_settings()
        self.storage_type = settings.storage_type
        self.local_path = Path(settings.storage_local_path)
        self.public_base_url = settings.public_base_url.rstrip("/")
        self.local_path.mkdir(parents=True, exist_ok=True)

    async def save(
        self,
        image_bytes: bytes,
        account_id: str,
        filename: str | None = None,
        subfolder: str = "posts",
    ) -> tuple[str, str]:
        """
        Görseli kaydet.
        (storage_path, public_url) döndür.
        """
        if not filename:
            filename = f"{uuid.uuid4().hex}.jpg"

        if self.storage_type == "local":
            return await self._save_local(image_bytes, account_id, filename, subfolder)

        # Gelecekte S3 buraya
        return await self._save_local(image_bytes, account_id, filename, subfolder)

    async def _save_local(
        self,
        image_bytes: bytes,
        account_id: str,
        filename: str,
        subfolder: str,
    ) -> tuple[str, str]:
        dir_path = self.local_path / account_id / subfolder
        dir_path.mkdir(parents=True, exist_ok=True)

        file_path = dir_path / filename
        file_path.write_bytes(image_bytes)

        storage_path = str(file_path)
        # Instagram Graph API için mutlak/public URL şart.
        public_url = f"{self.public_base_url}/images/{account_id}/{subfolder}/{filename}"

        log.debug("image_saved", path=storage_path, size=len(image_bytes))
        return storage_path, public_url

    async def read(self, storage_path: str) -> bytes:
        return Path(storage_path).read_bytes()
