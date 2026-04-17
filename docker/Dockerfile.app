FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    fonts-liberation \
    fonts-noto \
    imagemagick \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# ImageMagick policy fix for security-related font rendering errors
# Flexible search for policy.xml location
RUN POLICY_PATH=$(find /etc -name policy.xml | grep ImageMagick) && \
    if [ -n "$POLICY_PATH" ]; then \
        sed -i 's/policy domain="path" rights="none" pattern="@\*"/policy domain="path" rights="read|write" pattern="@\*"/g' "$POLICY_PATH"; \
    fi

# Poetry
RUN pip install --no-cache-dir poetry==1.8.3
ENV POETRY_VIRTUALENVS_CREATE=false

COPY pyproject.toml poetry.lock* ./
COPY src ./src
RUN poetry lock --no-update && poetry install --no-interaction --no-ansi

COPY . .

EXPOSE 8000

CMD ["uvicorn", "aitopiahub.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
