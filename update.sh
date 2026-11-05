#!/usr/bin/env bash
set -euo pipefail

main() {
    local root branch upstream status
    root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cd "$root"
    if [[ "$(git rev-parse --show-toplevel 2>/dev/null || true)" != "$root" ]]; then
        printf 'This is not a Git checkout. Download or clone the project from its GitHub page first.\n' >&2
        return 1
    fi
    branch="$(git symbolic-ref --quiet --short HEAD || true)"
    if [[ -z "$branch" ]]; then
        printf 'A release tag/detached commit is checked out. Choose the intended branch before updating.\n' >&2
        return 1
    fi
    status="$(git status --porcelain)"
    if [[ -n "$status" ]]; then
        printf 'Local changes found. Commit, back up, or stash them yourself before updating. Nothing was changed.\n' >&2
        return 1
    fi
    upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)"
    if [[ -z "$upstream" ]]; then
        printf 'This branch has no upstream. Configure its tracking branch before updating.\n' >&2
        return 1
    fi
    printf 'Updating %s from %s (fast-forward only)…\n' "$branch" "$upstream"
    git pull --ff-only
    bash scripts/sync_source.sh
    bash start.sh
    printf 'Source updated. Your current vehicle profile, coding, mocks and firmware were kept.\n'
}

main "$@"
