#!/bin/bash
# Reset all development databases to clean state

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
cd "$REPO_ROOT"

if [ ! -f ".env" ]; then
    echo "❌ .env file not found. Please run this script from the repository root."
    exit 1
fi

source .env

echo "🗑️  Resetting development databases..."

# Discover all services that have Alembic migrations and a matching *_db service in Docker Compose
compose_services=()
while IFS= read -r compose_service; do
    compose_services+=("$compose_service")
done < <(docker compose config --services)

service_dirs=()
db_services=()
db_names=()
while IFS= read -r dir; do
    [ -d "$dir/alembic" ] || continue
    service_name=$(basename "$dir")
    service_key=${service_name%_service}
    db_service="${service_key}_db"

    if [[ " ${compose_services[*]} " != *" ${db_service} "* ]]; then
        continue
    fi

    service_dirs+=("$dir")
    db_services+=("$service_key")
    db_names+=("huleedu_${service_key}")
done < <(find services -maxdepth 1 -mindepth 1 -type d -name "*_service" | sort)

if [ ${#db_services[@]} -eq 0 ]; then
    echo "ℹ️  No Alembic-enabled services found. Nothing to reset."
    exit 0
fi

compose_project=${COMPOSE_PROJECT_NAME:-$(basename "$REPO_ROOT")}

db_containers=()
db_volumes=()
for service in "${db_services[@]}"; do
    db_containers+=("${service}_db")
    db_volumes+=("${compose_project}_${service}_db_data")
done

echo "🛑 Stopping database containers..."
for container in "${db_containers[@]}"; do
    docker compose stop "$container" >/dev/null 2>&1 || true
    docker compose rm -f "$container" >/dev/null 2>&1 || true
done

echo "🧹 Removing database volumes..."
for volume in "${db_volumes[@]}"; do
    if docker volume inspect "$volume" >/dev/null 2>&1; then
        docker volume rm -f "$volume" >/dev/null
    fi
done

echo "🚀 Starting database containers..."
docker compose up -d "${db_containers[@]}"

echo "⏳ Waiting for databases to be ready..."
for idx in "${!db_containers[@]}"; do
    container="${db_containers[$idx]}"
    db_name="${db_names[$idx]}"
    printf "   → %s ..." "$container"
    wait_attempts=0
    until docker compose exec "$container" pg_isready -U "$HULEEDU_DB_USER" -d "$db_name" >/dev/null 2>&1; do
        wait_attempts=$((wait_attempts + 1))
        if [ $wait_attempts -ge 60 ]; then
            echo " failed (timeout)"
            exit 1
        fi
        sleep 2
    done
    echo " ready"
done

echo "📄 Running migrations..."
for idx in "${!db_services[@]}"; do
    service="${db_services[$idx]}"
    dir="${service_dirs[$idx]}"
    if [ -d "$dir" ]; then
        echo "   → ${service}_service"
        (cd "$dir" && ../../.venv/bin/alembic upgrade head)
    fi
done

echo "✅ Development databases reset complete!"
echo "💡 Seed test data with: ./scripts/seed-dev-data.sh"
