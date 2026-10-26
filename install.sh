#!/usr/bin/env bash
# Manual installer: copies the cost-oracle agent and skill into ~/.copilot (and ~/.claude if present).
# Prefer the plugin install (see README) when you use GitHub Copilot CLI plugins.
set -euo pipefail

COPILOT_HOME="${COPILOT_HOME:-$HOME/.copilot}"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 is required (3.10+)" >&2
  exit 1
fi

mkdir -p "$COPILOT_HOME/agents" "$COPILOT_HOME/skills"
cp "$REPO_DIR/agents/cost-oracle.md" "$COPILOT_HOME/agents/cost-oracle.md"
rm -rf "$COPILOT_HOME/skills/cost-oracle"
cp -R "$REPO_DIR/skills/cost-oracle" "$COPILOT_HOME/skills/cost-oracle"

echo "Installed:"
echo "  agent  -> $COPILOT_HOME/agents/cost-oracle.md"
echo "  skill  -> $COPILOT_HOME/skills/cost-oracle/"

if [ -d "$CLAUDE_HOME" ]; then
  mkdir -p "$CLAUDE_HOME/agents" "$CLAUDE_HOME/skills"
  cp "$REPO_DIR/agents/cost-oracle.md" "$CLAUDE_HOME/agents/cost-oracle.md"
  rm -rf "$CLAUDE_HOME/skills/cost-oracle"
  cp -R "$REPO_DIR/skills/cost-oracle" "$CLAUDE_HOME/skills/cost-oracle"
  echo "  agent  -> $CLAUDE_HOME/agents/cost-oracle.md"
  echo "  skill  -> $CLAUDE_HOME/skills/cost-oracle/"
fi

echo
echo "Next steps:"
echo "  1. Start a new GitHub Copilot CLI session."
echo "  2. Run the training round:  /cost-oracle train"
echo "  3. Ask for an estimate:     /cost-oracle how much to add OAuth login?"
