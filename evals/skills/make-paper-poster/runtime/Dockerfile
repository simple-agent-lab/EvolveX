FROM node:22-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        librsvg2-bin \
        poppler-utils \
        python3 \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @openai/codex@0.145.0

WORKDIR /root/task
