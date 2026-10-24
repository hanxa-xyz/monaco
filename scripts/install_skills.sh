#!/usr/bin/env bash
# Install monaco's Claude Code skills and agents by symlink, so a `git pull` here updates them everywhere.
#
#   scripts/install_skills.sh                 # -> ~/.claude/skills (global: every project)
#   scripts/install_skills.sh /path/to/proj   # -> /path/to/proj/.claude/skills (that project only)
#   scripts/install_skills.sh --copy [dest]   # copy instead of symlink (for a machine that will not keep this checkout)
#
# The skills' Python scripts import the `monaco` package, so also run `pip install -e .` from this repo once.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE=link
if [[ "${1:-}" == "--copy" ]]; then MODE=copy; shift; fi
DEST_ROOT="${1:-$HOME}"
DEST="$DEST_ROOT/.claude"
mkdir -p "$DEST/skills" "$DEST/agents"

n=0
for src in "$HERE"/skills/*/; do
  name="$(basename "$src")"
  tgt="$DEST/skills/$name"
  if [[ -L "$tgt" || -d "$tgt" ]]; then rm -rf "$tgt"; fi
  if [[ "$MODE" == link ]]; then ln -s "$src" "$tgt"; else cp -R "$src" "$tgt"; fi
  n=$((n + 1))
done
for src in "$HERE"/.claude/agents/*.md; do
  name="$(basename "$src")"
  tgt="$DEST/agents/$name"
  rm -f "$tgt"
  if [[ "$MODE" == link ]]; then ln -s "$src" "$tgt"; else cp "$src" "$tgt"; fi
done

echo "installed $n skills + $(ls "$HERE"/.claude/agents/*.md | wc -l | tr -d ' ') agents -> $DEST ($MODE)"
python3 -c "import monaco" 2>/dev/null && echo "monaco package: importable" || echo "monaco package: NOT importable — run: pip install -e \"$HERE[all]\""
