# Python 3.13.16 / Debian bookworm, pinned to the verified image.
FROM python:3.13-slim-bookworm@sha256:5024f48ba9441d4b13a95d3945abc6365538e3a31109833367a1923523c6efed

ARG LOCAL_UID=1000
ARG LOCAL_GID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid "${LOCAL_GID}" developer \
    && useradd --uid "${LOCAL_UID}" --gid developer --create-home --shell /bin/bash developer \
    && python -m venv /opt/venv \
    && mkdir -p /home/developer/work/logi-scope \
    && chown -R developer:developer /opt/venv /home/developer/work/logi-scope

WORKDIR /home/developer/work/logi-scope
USER developer

# Development shell container; the API is not implemented yet.
CMD ["sleep", "infinity"]
