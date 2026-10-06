FROM node:24.21.0-bookworm-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6

ARG LOCAL_UID=1000
ARG LOCAL_GID=1000
RUN groupmod --gid "${LOCAL_GID}" node \
    && usermod --uid "${LOCAL_UID}" --login developer --home /home/developer --move-home node \
    && mkdir -p /home/developer/work/logi-scope/frontend \
    && chown -R developer:node /home/developer

WORKDIR /home/developer/work/logi-scope/frontend
USER developer
COPY --chown=developer:node package.json package-lock.json ./
RUN npm ci
COPY --chown=developer:node . .
CMD ["sleep", "infinity"]
