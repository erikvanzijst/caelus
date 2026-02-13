FROM docker:cli AS dockercli
FROM docker/buildx-bin AS buildxbin
FROM bitnami/kubectl AS kubectl
FROM derailed/k9s AS k9s
FROM mcr.microsoft.com/devcontainers/python:3.13-trixie

COPY --from=k9s /bin/k9s /usr/local/bin/k9s
COPY --from=kubectl /opt/bitnami/kubectl/bin/kubectl /usr/local/bin/kubectl
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=buildxbin /buildx /usr/libexec/docker/cli-plugins/docker-buildx

RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
      nodejs \
      npm \
      neovim \
      btop \
      httpie \
      sqlite3 \
      curl \
      wget \
      jq \
      yq \
      ca-certificates \
      gnupg && \
    install -m 0755 -d /etc/apt/keyrings && \
    wget -qO- https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/keyrings/google-chrome.gpg && \
    chmod a+r /etc/apt/keyrings/google-chrome.gpg && \
    echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update -y && \
    apt-get install -y --no-install-recommends \
      google-chrome-stable \
      fonts-liberation \
      libu2f-udev && \
    rm -rf /var/lib/apt/lists/*
RUN groupadd -f docker && usermod -aG docker vscode
RUN npm i -g @openai/codex
RUN mkdir /workspace && chown vscode:vscode /workspace

USER vscode
WORKDIR /workspace
RUN mkdir -p ~/.local/bin ~/.ssh ~/venv
RUN chmod 700 ~/.ssh
RUN ssh-keyscan github.com >> ~/.ssh/known_hosts

ENV PATH=/home/vscode/.local/bin:$PATH
ENV COLORTERM=truecolor
ENV UV_PROJECT_ENVIRONMENT="/home/vscode/venv"
ENV DOCKER_BUILDKIT=1
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
RUN curl -fsSL https://claude.ai/install.sh | bash
RUN curl -fsSL https://opencode.ai/install | bash

EXPOSE 8000 5173
CMD bash
