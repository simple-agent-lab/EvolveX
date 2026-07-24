FROM ubuntu:24.04@sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90

ARG MINISWE_VERSION=2.4.5
ARG SOURCE_REVISION=unknown
ARG BUILD_TIMESTAMP=unknown
ARG UV_VERSION=0.7.13

LABEL org.opencontainers.image.revision="${SOURCE_REVISION}" \
      org.opencontainers.image.created="${BUILD_TIMESTAMP}" \
      io.evolve.miniswe.version="${MINISWE_VERSION}" \
      io.evolve.uv.version="${UV_VERSION}"

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
RUN curl -LsSf https://astral.sh/uv/${UV_VERSION}/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"
RUN uv tool install --python 3.13 --with fastapi --with orjson "mini-swe-agent==${MINISWE_VERSION}"
RUN mv /root/.local/bin/uv /root/.local/bin/uv-real
COPY uv-wrapper /root/.local/bin/uv
RUN chmod 755 /root/.local/bin/uv
COPY required-tools.txt /opt/evolve/required-tools.txt
RUN git config --system --add safe.directory /app/task/workspace

WORKDIR /app
