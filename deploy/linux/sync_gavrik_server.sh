#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 4 ]]; then
  echo "Usage: $0 REPO_PATH REF VENV_PATH STATE_FILE" >&2
  exit 64
fi

repo_path=$1
ref=$2
venv_path=$3
state_file=$4

if [[ ! -d "$repo_path/.git" ]]; then
  echo "REPO_PATH is not a Git working tree: $repo_path" >&2
  exit 65
fi

cd -- "$repo_path"

if [[ -n "$(git status --porcelain=v1 --untracked-files=all)" ]]; then
  echo "Refusing to sync: the Git working tree is not clean." >&2
  exit 66
fi

git fetch --prune origin
commit=$(git rev-parse --verify "${ref}^{commit}")
git switch --detach "$commit"

if [[ ! -x "$venv_path/bin/python" ]]; then
  python3 -m venv "$venv_path"
fi

"$venv_path/bin/python" -m pip install --disable-pip-version-check -r requirements-dev.txt
"$venv_path/bin/python" -m pytest

install -d -m 0750 "$(dirname -- "$state_file")"
printf '%s\n' "$commit" >"$state_file"
chmod 0640 "$state_file"
printf 'Server code verified at %s. Application lifecycle was not changed.\n' "$commit"
