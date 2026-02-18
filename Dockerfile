FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

ENV TZ=Asia/Seoul

RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    libxshmfence1 \
    libgtk-3-0 \
    fonts-liberation \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY devhire_crawler/requirements.txt /app/requirements.txt

RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && playwright install chromium

COPY devhire_crawler /app/devhire_crawler
COPY scripts /app/scripts

CMD ["python", "scripts/run_crawler.py"]
