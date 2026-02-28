FROM docker:cli AS dockercli
FROM docker/buildx-bin AS buildxbin
FROM docker/compose-bin AS composebin
FROM bitnami/kubectl AS kubectl
FROM derailed/k9s AS k9s
FROM d3fk/helm:latest AS helm
FROM mcr.microsoft.com/devcontainers/python:3.13-trixie

COPY --from=k9s /bin/k9s /usr/local/bin/k9s
COPY --from=kubectl /opt/bitnami/kubectl/bin/kubectl /usr/local/bin/kubectl
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=buildxbin /buildx /usr/libexec/docker/cli-plugins/docker-buildx
COPY --from=composebin /docker-compose /usr/libexec/docker/cli-plugins/docker-compose
COPY --from=helm /helm /usr/local/bin/helm

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
      dnsutils \
      postgresql-client \
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
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | gpg --dearmor -o /etc/apt/keyrings/githubcli-archive-keyring.gpg && \
    chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list && \
    apt-get update -y && \
    apt-get install -y --no-install-recommends gh && \
    wget -O - https://apt.releases.hashicorp.com/gpg | gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(grep -oP '(?<=UBUNTU_CODENAME=).*' /etc/os-release || lsb_release -cs) main" | tee /etc/apt/sources.list.d/hashicorp.list && \
    sudo apt update && apt install terraform && \
    rm -rf /var/lib/apt/lists/*
RUN groupadd --gid 968 -f docker && usermod -aG docker vscode
RUN npm i -g @openai/codex
RUN npm i -g @qwen-code/qwen-code@latest
RUN mkdir /workspace && chown vscode:vscode /workspace

ENV PATH=/home/vscode/.local/bin:$PATH
ENV COLORTERM=truecolor
ENV UV_PROJECT_ENVIRONMENT="/home/vscode/venv"
ENV DOCKER_BUILDKIT=1
# https://opencode.ai/docs/tools/#websearch
ENV OPENCODE_ENABLE_EXA=1

USER vscode
WORKDIR /workspace
RUN mkdir -p ~/.local/bin ~/.ssh ~/venv ~/.docker
RUN chmod 700 ~/.ssh ~/.docker
RUN ssh-keyscan github.com >> ~/.ssh/known_hosts
RUN echo '' >> ~/.bashrc && \
    echo '# Auto-activate Caelus virtualenv' >> ~/.bashrc && \
    echo 'if [ -f $UV_PROJECT_ENVIRONMENT/bin/activate ]; then source $UV_PROJECT_ENVIRONMENT/bin/activate; fi' >> ~/.bashrc

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
RUN curl -fsSL https://claude.ai/install.sh | bash
RUN curl -fsSL https://opencode.ai/install | bash

EXPOSE 8000 5173
CMD bash
