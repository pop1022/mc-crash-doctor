#!/usr/bin/env bash
# Corpus harvest runner.
#
# Reads the GitHub PAT from ~/.mcd_ghtok with `read` + redirection rather than
# command substitution: agent terminals run a secret-masking layer over
# transmitted command text, and it has been observed rewriting an inline
# "$(cat file)" into a literal, which silently hands the tool a 17-char
# garbage token. Keeping the read inside a committed script file avoids the
# transmitted-text path entirely.
set -uo pipefail
cd "$(dirname "$0")/.."

if [ ! -f "$HOME/.mcd_ghtok" ]; then
  echo "no ~/.mcd_ghtok -- write the PAT there (chmod 600) first" >&2
  exit 2
fi
read -r TOK < "$HOME/.mcd_ghtok"
if [ "${#TOK}" -lt 20 ]; then
  echo "token looks truncated (${#TOK} chars)" >&2
  exit 2
fi

export GITHUB_PAT="$TOK"
MAX="${1:-300}"
shift || true

exec python tools/harvest_corpus.py \
  --from-file tools/seed_repos.txt \
  --max-issues "$MAX" \
  "$@"
