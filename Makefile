.PHONY: help up down logs install migrate seed test test-post lint server-status

help:
	@echo "Aitopiahub — Komutlar"
	@echo "─────────────────────────────────────────"
	@echo "  make up           Docker Compose stack'i başlat"
	@echo "  make down         Stack'i durdur"
	@echo "  make logs         Tüm container loglarını izle"
	@echo "  make install      Python bağımlılıklarını kur"
	@echo "  make migrate      Alembic migration çalıştır"
	@echo "  make seed         aitopiahub_news hesabını DB'ye ekle"
	@echo "  make test         pytest çalıştır"
	@echo "  make test-post    Dry-run post testi"
	@echo "  make lint         Ruff linting"
	@echo "  make server-status  Sunucudan anlık durum al (VPS ayarları gerekir)"

up:
	cd docker && docker-compose up -d
	@echo "✅ Stack başlatıldı"
	@echo "   Admin API  → http://localhost:8000"
	@echo "   Grafana    → http://localhost:3000 (admin/admin)"
	@echo "   MinIO      → http://localhost:9001"

down:
	cd docker && docker-compose down

logs:
	cd docker && docker-compose logs -f

install:
	pip install poetry && poetry install

migrate:
	alembic upgrade head

seed:
	python scripts/seed_accounts.py --account aitopiahub_news

test:
	pytest tests/ -v --tb=short

test-post:
	python scripts/test_post.py --account aitopiahub_news --keyword "artificial intelligence" --dry-run

lint:
	ruff check src/ scripts/ --fix

server-status:
	@bash -lc 'source .env >/dev/null 2>&1; ssh $$VPS_USER@$$VPS_HOST "bash $$VPS_REMOTE_PATH/scripts/server_status.sh"'

# Yeni hesap ekleme yardımcısı
add-account:
	@if [ -z "$(ACCOUNT)" ]; then echo "Kullanım: make add-account ACCOUNT=aitopiahub_spor"; exit 1; fi
	python scripts/seed_accounts.py --account $(ACCOUNT)
	@echo "✅ Hesap eklendi: $(ACCOUNT)"
	@echo "⚠️  configs/accounts/$(ACCOUNT).yaml ve .env.accounts/$(ACCOUNT).env dosyalarını oluşturmayı unutma!"
