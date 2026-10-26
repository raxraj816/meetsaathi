# MeetSaathi backend image (API, worker and migrations share one image; the command selects the role).
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv
RUN useradd --system --uid 10001 meetsaathi
RUN apt-get update && apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml requirements.lock ./
RUN pip install --require-hashes -r requirements.lock
COPY app ./app
COPY migrations ./migrations
COPY certs/rds-global-bundle.pem /etc/ssl/certs/rds-global-bundle.pem
RUN pip install --no-deps .
RUN mkdir -p /var/lib/meetsaathi/objects && chown -R meetsaathi /var/lib/meetsaathi
USER meetsaathi
ENV MS_OBJECT_STORE_DIR=/var/lib/meetsaathi/objects
ENV MS_DATABASE_CA_FILE=/etc/ssl/certs/rds-global-bundle.pem
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
