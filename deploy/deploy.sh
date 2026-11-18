#!/usr/bin/env bash
# Rebuild and restart the backend on the server, then wait until it reports healthy.
#
# GitHub Actions runs this over SSH after checking out the commit to deploy:
#   git fetch origin && git checkout --detach <sha> && deploy/deploy.sh
# The checkout happens before this script starts, so it never changes under bash's feet.
set -euo pipefail

main() {
    cd "$(dirname "$0")"
    [[ -f .env ]] || { echo "deploy/.env is missing (copy .env.example)" >&2; exit 1; }

    echo "Deploying $(git rev-parse --short HEAD)"
    docker compose build backend
    docker compose up -d --remove-orphans

    local container status
    container="$(docker compose ps -q backend)"
    for _ in $(seq 1 40); do
        status="$(docker inspect --format '{{.State.Health.Status}}' "$container")"
        if [[ "$status" == healthy ]]; then
            echo "Backend is healthy"
            docker image prune -f >/dev/null
            return 0
        fi
        sleep 3
    done
    echo "Backend did not become healthy (last status: $status)" >&2
    docker compose logs --tail 50 backend >&2
    exit 1
}

main "$@"
