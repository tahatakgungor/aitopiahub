#!/usr/bin/env python3
"""
Hesap verilerini veritabanına ekler.
Kullanım: python scripts/seed_accounts.py --account aitopiahub_news
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aitopiahub.core.config import AccountConfig, get_settings
from aitopiahub.core.database import get_engine, Base
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def seed(account_handle: str) -> None:
    config = AccountConfig.for_account(account_handle)

    # create_all öncesi model metadata'sını yükle
    from aitopiahub import models  # noqa: F401

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with factory() as session:
        from aitopiahub.models.account import Account
        from sqlalchemy import select

        result = await session.execute(
            select(Account).where(Account.handle == account_handle)
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"✓ Hesap zaten mevcut: {account_handle}")
            return

        account = Account(
            handle=account_handle,
            display_name=account_handle.replace("_", " ").title(),
            niche=config.niche,
            language_primary=config.language_primary,
            language_secondary=config.language_secondary,
            timezone=config.timezone,
            posting_frequency_per_day=config.posts_per_day,
        )
        session.add(account)
        await session.commit()
        print(f"✓ Hesap oluşturuldu: {account_handle} (niche={config.niche})")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", required=True)
    args = parser.parse_args()
    asyncio.run(seed(args.account))
