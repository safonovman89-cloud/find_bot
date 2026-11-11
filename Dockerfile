FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY certs/russian-trusted-root-ca.crt /usr/local/share/ca-certificates/russian-trusted-root-ca.crt

RUN apt-get update \
    && apt-get install --yes --no-install-recommends antiword ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 10001 findinfobot \
    && useradd --system --uid 10001 --gid findinfobot --home-dir /app findinfobot

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install --requirement requirements.txt

COPY --chown=findinfobot:findinfobot bot ./bot

USER 10001:10001

CMD ["python", "-m", "bot.cli", "polling"]
