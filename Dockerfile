# Python 3.13.16 / Debian bookworm, pinned to the verified image.
FROM python:3.13-slim-bookworm@sha256:5024f48ba9441d4b13a95d3945abc6365538e3a31109833367a1923523c6efed

ARG LOCAL_UID=1000
ARG LOCAL_GID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid "${LOCAL_GID}" developer \
    && useradd --uid "${LOCAL_UID}" --gid developer --create-home --shell /bin/bash developer \
    && python -m venv /opt/venv \
    && mkdir -p /home/developer/work/logi-scope \
    && chown -R developer:developer /opt/venv /home/developer/work/logi-scope

# Keep uv outside the project venv so `uv sync` cannot remove itself.
RUN python -m pip install --no-cache-dir uv==0.12.23

WORKDIR /home/developer/work/logi-scope
USER developer

COPY --chown=developer:developer pyproject.toml uv.lock ./
COPY --chown=developer:developer src ./src
RUN uv sync --locked

# Keep shell-based development; start Uvicorn explicitly inside the container.
CMD ["sleep", "infinity"]
