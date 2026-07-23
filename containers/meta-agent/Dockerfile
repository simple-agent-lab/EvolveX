FROM ubuntu:latest

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        build-essential \
        ca-certificates \
        coreutils \
        curl \
        diffutils \
        file \
        findutils \
        git \
        jq \
        less \
        openssh-client \
        patch \
        procps \
        python3 \
        python3-pip \
        python3-venv \
        python-is-python3 \
        ripgrep \
        rsync \
        sed \
        tree \
        unzip \
        zip \
    && rm -rf /var/lib/apt/lists/*
RUN curl -LsSf https://astral.sh/uv/0.7.13/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"
RUN uv tool install --python 3.13 --with fastapi --with orjson mini-swe-agent
RUN mv /root/.local/bin/uv /root/.local/bin/uv-real
COPY uv-wrapper /root/.local/bin/uv
RUN chmod 755 /root/.local/bin/uv

WORKDIR /app
