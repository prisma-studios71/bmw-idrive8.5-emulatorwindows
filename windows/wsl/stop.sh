#!/usr/bin/env bash
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
if docker info >/dev/null 2>&1 && docker inspect bmw-idrive85 >/dev/null 2>&1; then
    docker stop -t 15 bmw-idrive85 >/dev/null
    printf 'HMI container stopped.\n'
else
    printf 'HMI container is not running.\n'
fi
sync
