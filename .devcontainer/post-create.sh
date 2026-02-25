#!/usr/bin/env bash
set -euo pipefail

cd /workspace/api

uv venv "$UV_PROJECT_ENVIRONMENT"
uv pip install --python "$UV_PROJECT_ENVIRONMENT/bin/python" -e .

source "$UV_PROJECT_ENVIRONMENT/bin/activate"

completion_dir="$HOME/.local/share/caelus"
completion_file="$completion_dir/completion.bash"
completion_source_line="source \"$completion_file\""

mkdir -p "$completion_dir"
caelus --show-completion > "$completion_file"

grep -qxF "$completion_source_line" "$HOME/.bashrc" || \
  echo "$completion_source_line" >> "$HOME/.bashrc"

alembic upgrade head
