FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Keep the manager QR scanner inside our own static bundle. The pinned artifact
# is downloaded only while building the image and is rejected if its SHA-512
# digest differs from the reviewed html5-qrcode 2.3.8 release.
RUN mkdir -p /app/cards/static/cards/vendor \
    && curl --fail --silent --show-error --location \
      https://cdnjs.cloudflare.com/ajax/libs/html5-qrcode/2.3.8/html5-qrcode.min.js \
      --output /app/cards/static/cards/vendor/html5-qrcode.min.js \
    && echo "afaac303b5ba65e421be5f12ef24554142951dd7b1abe18094d90d36a542ed8c8857e370a824c97b684358289f7d3c9134e78613345127d89fbd19bf1c2cc662  /app/cards/static/cards/vendor/html5-qrcode.min.js" \
      | sha512sum --check --strict

RUN chmod +x /app/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
