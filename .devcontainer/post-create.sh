#!/usr/bin/env bash
set -euo pipefail

cd /workspace/api
uv sync

completion_dir="$HOME/.local/share/caelus"
completion_file="$completion_dir/completion.bash"
completion_source_line="source \"$completion_file\""

mkdir -p "$completion_dir"
uv run caelus --show-completion > "$completion_file"

grep -qxF "$completion_source_line" "$HOME/.bashrc" || \
  echo "$completion_source_line" >> "$HOME/.bashrc"

alias_line="alias claude='claude --dangerously-skip-permissions'"
grep -qxF "$alias_line" "$HOME/.bashrc" || \
  echo "$alias_line" >> "$HOME/.bashrc"

uv run alembic upgrade head

cd /workspace/cli
uv sync
