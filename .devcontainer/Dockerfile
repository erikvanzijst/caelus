FROM mcr.microsoft.com/devcontainers/python:3.13-trixie

RUN apt-get update -y && \
    apt-get install -y nodejs npm neovim btop httpie sqlite3 curl wget jq yq && \
    apt-get clean
RUN npm i -g @openai/codex
RUN mkdir /workspace && chown vscode:vscode /workspace

USER vscode
WORKDIR /workspace
RUN mkdir -p ~/.local/bin ~/.ssh ~/venvs
RUN chmod 700 ~/.ssh
RUN ssh-keyscan github.com >> ~/.ssh/known_hosts

ENV PATH=/home/vscode/.local/bin:$PATH
ENV COLORTERM=truecolor
ENV UV_PROJECT_ENVIRONMENT="/home/vscode/venv"
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
RUN curl -fsSL https://claude.ai/install.sh | bash
RUN curl -fsSL https://opencode.ai/install | bash

EXPOSE 8000 5173
CMD bash
