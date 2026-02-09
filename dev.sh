#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load .env if present (gitignored — safe for tokens)
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi
APPHOST="$SCRIPT_DIR/RiparianPoc.AppHost"
SCHEMA_FILE="$SCRIPT_DIR/sql/create_schemas.sql"
PID_FILE="$SCRIPT_DIR/.aspire.pid"
POSTGIS_IMAGE="postgis/postgis:16-3.4"
SONAR_CONTAINER="riparian-sonarqube"
SONAR_SCANNER_IMAGE="sonarsource/sonar-scanner-cli:latest"

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

green()  { printf '\033[0;32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[1;33m%s\033[0m\n' "$*"; }
red()    { printf '\033[0;31m%s\033[0m\n' "$*"; }
info()   { green  "[INFO]  $*"; }
warn()   { yellow "[WARN]  $*"; }
error()  { red    "[ERROR] $*"; }

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

check_drive() {
    if [ ! -d "/Volumes/Mac OS Extended 1/riparian-poc" ]; then
        error "External drive not mounted at /Volumes/Mac OS Extended 1/"
        error "Mount the drive and try again."
        exit 1
    fi
}

check_docker() {
    if ! docker info >/dev/null 2>&1; then
        error "Docker is not running. Start Docker Desktop and try again."
        exit 1
    fi
}

check_dotnet() {
    if ! command -v dotnet >/dev/null 2>&1; then
        error "dotnet SDK not found. Install .NET 10 SDK."
        exit 1
    fi
}

check_node() {
    if ! command -v node >/dev/null 2>&1; then
        error "Node.js not found. Install Node.js 20+."
        exit 1
    fi
}

preflight() {
    check_drive
    check_docker
    check_dotnet
    check_node
}

# ---------------------------------------------------------------------------
# PostGIS helpers
# ---------------------------------------------------------------------------

get_postgis_container() {
    docker ps --filter "ancestor=$POSTGIS_IMAGE" --format '{{.ID}}' | head -1
}

# Run psql inside the PostGIS container using its own POSTGRES_PASSWORD env var.
# Aspire configures scram-sha-256 auth, so every psql call needs the password.
container_psql() {
    local cid="$1"; shift
    docker exec -i "$cid" bash -c 'PGPASSWORD=$POSTGRES_PASSWORD psql -U postgres "$@"' -- "$@"
}

wait_for_db() {
    info "Waiting for PostGIS + ripariandb to be ready..."
    local max_wait=90
    local elapsed=0

    while [ "$elapsed" -lt "$max_wait" ]; do
        local cid
        cid=$(get_postgis_container)
        if [ -n "$cid" ]; then
            if container_psql "$cid" -d ripariandb -c '\q' 2>/dev/null; then
                info "PostGIS is ready (${elapsed}s)"
                return 0
            fi
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done

    warn "Timed out after ${max_wait}s waiting for PostGIS."
    return 1
}

apply_schema() {
    local cid
    cid=$(get_postgis_container)
    if [ -z "$cid" ]; then
        warn "No PostGIS container found — schema not applied."
        return 1
    fi

    # Check if schema is already present (bronze.streams as sentinel)
    if container_psql "$cid" -d ripariandb \
        -c "SELECT 1 FROM bronze.streams LIMIT 0" >/dev/null 2>&1; then
        info "Schema already applied — skipping."
    else
        info "Applying database schema from sql/create_schemas.sql ..."
        docker exec -i "$cid" bash -c 'PGPASSWORD=$POSTGRES_PASSWORD psql -U postgres -d ripariandb' < "$SCHEMA_FILE"
        info "Schema applied successfully."
    fi
}

# ---------------------------------------------------------------------------
# Install frontend deps if needed
# ---------------------------------------------------------------------------

ensure_frontend_deps() {
    if [ ! -d "$SCRIPT_DIR/frontend/node_modules" ]; then
        info "Installing frontend dependencies..."
        (cd "$SCRIPT_DIR/frontend" && npm install)
    fi
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

cmd_start() {
    preflight
    ensure_frontend_deps

    info "Building solution..."
    dotnet build "$SCRIPT_DIR/RiparianPoc.sln" --verbosity quiet

    # Use HTTP-only (no HTTPS dev cert required)
    export ASPIRE_ALLOW_UNSECURED_TRANSPORT=true

    info "Starting Aspire AppHost (Ctrl+C to stop)..."
    info "Aspire dashboard will open — check terminal output for URL."
    echo ""

    # Launch Aspire in background so we can apply the schema
    dotnet run --project "$APPHOST" --no-build --launch-profile http &
    local aspire_pid=$!
    echo "$aspire_pid" > "$PID_FILE"

    # Forward Ctrl+C / SIGTERM to the Aspire process
    trap 'kill "$aspire_pid" 2>/dev/null; rm -f "$PID_FILE"; exit 0' INT TERM

    # Wait for DB and apply schema in background (non-blocking)
    (
        if wait_for_db; then
            apply_schema
            echo ""
            info "Ready! Services:"
            info "  Frontend:  http://localhost:3000"
            info "  API:       (see Aspire dashboard for port)"
            info "  Dashboard: (see terminal output above)"
        fi
    ) &

    # Block on the Aspire process — script exits when Aspire does
    wait "$aspire_pid" 2>/dev/null || true
    rm -f "$PID_FILE"
}

cmd_stop() {
    # Stop via PID file
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            info "Stopping Aspire (PID $pid)..."
            kill "$pid"
            sleep 2
        fi
        rm -f "$PID_FILE"
    fi

    # Also catch any orphaned AppHost processes
    local pids
    pids=$(pgrep -f "RiparianPoc.AppHost" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        info "Stopping remaining Aspire processes..."
        echo "$pids" | xargs kill 2>/dev/null || true
    fi

    info "Stopped. (PostGIS container persists — data is preserved.)"
}

cmd_restart() {
    cmd_stop
    sleep 2
    cmd_start
}

cmd_status() {
    echo "=== Riparian POC — Service Status ==="
    echo ""

    # Drive
    if [ -d "/Volumes/Mac OS Extended 1/riparian-poc" ]; then
        info "External drive:  mounted"
    else
        error "External drive:  NOT mounted"
    fi

    # Docker
    if docker info >/dev/null 2>&1; then
        info "Docker:          running"
    else
        error "Docker:          NOT running"
        return
    fi

    # PostGIS
    local cid
    cid=$(get_postgis_container)
    if [ -n "$cid" ]; then
        info "PostGIS:         running ($cid)"
        if container_psql "$cid" -d ripariandb -c '\q' 2>/dev/null; then
            info "ripariandb:      accessible"
            if container_psql "$cid" -d ripariandb \
                -c "SELECT 1 FROM bronze.streams LIMIT 0" >/dev/null 2>&1; then
                info "Schema:          applied"

                # Row counts
                local streams parcels buffers
                streams=$(container_psql "$cid" -d ripariandb -tAc \
                    "SELECT count(*) FROM bronze.streams" 2>/dev/null || echo "?")
                parcels=$(container_psql "$cid" -d ripariandb -tAc \
                    "SELECT count(*) FROM bronze.parcels" 2>/dev/null || echo "?")
                buffers=$(container_psql "$cid" -d ripariandb -tAc \
                    "SELECT count(*) FROM silver.riparian_buffers" 2>/dev/null || echo "?")
                info "Data:            streams=$streams  parcels=$parcels  buffers=$buffers"
            else
                warn "Schema:          NOT applied (run ./dev.sh to apply)"
            fi
        else
            warn "ripariandb:      database not created yet"
        fi
    else
        warn "PostGIS:         not running"
    fi

    # Aspire
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        info "Aspire:          running (PID $(cat "$PID_FILE"))"
    elif pgrep -f "RiparianPoc.AppHost" >/dev/null 2>&1; then
        info "Aspire:          running"
    else
        warn "Aspire:          not running"
    fi
}

# ---------------------------------------------------------------------------
# Update command — run incremental ETL
# ---------------------------------------------------------------------------

cmd_update() {
    local update_type="${1:-all}"
    local valid_types="full incremental ndvi all"
    if [[ ! " $valid_types " =~ " $update_type " ]]; then
        error "Invalid update type: $update_type"
        error "Valid types: $valid_types"
        exit 1
    fi

    check_drive
    check_docker

    local cid
    cid=$(get_postgis_container)
    if [ -z "$cid" ]; then
        error "PostGIS is not running. Start services first: ./dev.sh"
        exit 1
    fi

    # Apply incremental migration if meta schema doesn't exist yet
    if ! container_psql "$cid" -d ripariandb \
        -c "SELECT 1 FROM meta.etl_runs LIMIT 0" >/dev/null 2>&1; then
        info "Applying incremental migration..."
        docker exec -i "$cid" bash -c \
            'PGPASSWORD=$POSTGRES_PASSWORD psql -U postgres -d ripariandb' \
            < "$SCRIPT_DIR/sql/incremental_migration.sql"
    fi

    info "Running update (type: $update_type)..."

    # Check if ETL container is already running (long-lived scheduler mode)
    local etl_cid
    etl_cid=$(docker ps --filter "name=etl" --format '{{.ID}}' | head -1)

    if [ -n "$etl_cid" ]; then
        info "Using existing ETL container ($etl_cid)"
        docker exec "$etl_cid" python entrypoint.py --mode "$update_type"
    else
        # Build ETL image and run one-shot on the same network as PostGIS
        info "Building ETL image..."
        docker build -t riparian-etl "$SCRIPT_DIR/python-etl" --quiet

        local network
        network=$(docker inspect "$cid" --format 'json' | python3 -c "import sys,json; nets=json.load(sys.stdin)[0]['NetworkSettings']['Networks']; print(list(nets.keys())[0])")
        local pg_host
        pg_host=$(docker inspect "$cid" --format 'json' | python3 -c "import sys,json; nets=json.load(sys.stdin)[0]['NetworkSettings']['Networks']; print(list(nets.values())[0]['IPAddress'])")
        local pg_pass
        pg_pass=$(docker exec "$cid" printenv POSTGRES_PASSWORD)

        info "Running ETL update..."
        docker run --rm \
            --network="$network" \
            -e "DATABASE_URL=postgresql://postgres:${pg_pass}@${pg_host}:5432/ripariandb" \
            riparian-etl python entrypoint.py --mode "$update_type"
    fi

    info "Update complete."

    # Show latest run from meta.etl_runs
    local last_run
    last_run=$(container_psql "$cid" -d ripariandb -tAc \
        "SELECT run_type || ': ' || status || ' (' || records_inserted || ' ins, ' || records_updated || ' upd)' FROM meta.etl_runs ORDER BY started_at DESC LIMIT 1" \
        2>/dev/null || echo "unknown")
    info "Last run: $last_run"
}

# ---------------------------------------------------------------------------
# SonarQube — local static analysis
# ---------------------------------------------------------------------------

SONAR_COMPOSE="$SCRIPT_DIR/docker-compose.sonar.yml"

require_sonar_token() {
    if [ -z "${SONAR_TOKEN:-}" ]; then
        error "SONAR_TOKEN is not set."
        error ""
        error "Generate a token in SonarQube (http://localhost:9000):"
        error "  1. Log in (first time: admin / admin, then change password)"
        error "  2. My Account > Security > Generate Token"
        error "  3. export SONAR_TOKEN=\"your-token-here\""
        error ""
        error "Or add it to .env:  echo 'SONAR_TOKEN=your-token' >> .env"
        exit 1
    fi
}

wait_for_sonar() {
    info "Waiting for SonarQube to be ready..."
    local max_wait=120
    local elapsed=0
    while [ "$elapsed" -lt "$max_wait" ]; do
        if curl -sf http://localhost:9000/api/system/status 2>/dev/null | grep -q '"status":"UP"'; then
            return 0
        fi
        sleep 3
        elapsed=$((elapsed + 3))
    done
    warn "SonarQube did not become ready within ${max_wait}s."
    warn "Check: docker logs $SONAR_CONTAINER"
    return 1
}

cmd_sonar_start() {
    check_docker

    if docker ps --format '{{.Names}}' | grep -q "^${SONAR_CONTAINER}$"; then
        info "SonarQube is already running."
        info "Dashboard: http://localhost:9000"
        return 0
    fi

    info "Starting SonarQube Community Edition..."
    docker compose -f "$SONAR_COMPOSE" up -d

    if wait_for_sonar; then
        info "SonarQube is ready!"
        info "Dashboard: http://localhost:9000"
        info ""
        info "First time setup:"
        info "  1. Log in with admin / admin"
        info "  2. Change your password when prompted"
        info "  3. Generate a token: My Account > Security > Generate Token"
        info "  4. export SONAR_TOKEN=\"your-token-here\""
    fi
}

cmd_sonar_stop() {
    check_docker

    if docker ps --format '{{.Names}}' | grep -q "^${SONAR_CONTAINER}$"; then
        info "Stopping SonarQube..."
        docker compose -f "$SONAR_COMPOSE" down
        info "SonarQube stopped. Data is preserved in Docker volumes."
    else
        info "SonarQube is not running."
    fi
}

cmd_lint() {
    check_drive
    check_docker
    require_sonar_token

    # Verify SonarQube is running
    if ! curl -sf http://localhost:9000/api/system/status 2>/dev/null | grep -q '"status":"UP"'; then
        error "SonarQube is not running. Start it first: ./dev.sh --sonar"
        exit 1
    fi

    info "Running SonarQube analysis (Python + TypeScript + SQL)..."

    # On macOS, Docker containers reach the host via host.docker.internal.
    # The scanner runs inside Docker and needs to reach SonarQube on port 9000.
    local sonar_url="http://host.docker.internal:9000"

    docker run --rm \
        -v "$SCRIPT_DIR:/usr/src" \
        "$SONAR_SCANNER_IMAGE" \
        -Dsonar.host.url="$sonar_url" \
        -Dsonar.token="$SONAR_TOKEN"

    info "Analysis complete! View results at http://localhost:9000/dashboard?id=riparian-poc"
}

cmd_lint_dotnet() {
    check_drive
    check_docker
    check_dotnet
    require_sonar_token

    # Verify SonarQube is running
    if ! curl -sf http://localhost:9000/api/system/status 2>/dev/null | grep -q '"status":"UP"'; then
        error "SonarQube is not running. Start it first: ./dev.sh --sonar"
        exit 1
    fi

    # Install dotnet-sonarscanner if not present
    if ! dotnet tool list -g 2>/dev/null | grep -q "dotnet-sonarscanner"; then
        info "Installing dotnet-sonarscanner..."
        dotnet tool install --global dotnet-sonarscanner
    fi

    info "Running SonarQube analysis (C# .NET)..."

    # dotnet-sonarscanner runs on the host, so localhost works directly.
    # Temporarily hide sonar-project.properties (used by the non-.NET scanner)
    # because dotnet-sonarscanner rejects it during post-processing.
    if [ -f "$SCRIPT_DIR/sonar-project.properties" ]; then
        mv "$SCRIPT_DIR/sonar-project.properties" "$SCRIPT_DIR/sonar-project.properties.bak"
    fi

    dotnet sonarscanner begin \
        /k:"riparian-poc-dotnet" \
        /n:"Riparian POC — .NET API" \
        /d:sonar.host.url="http://localhost:9000" \
        /d:sonar.token="$SONAR_TOKEN" \
        /d:sonar.exclusions="**/node_modules/**,**/dist/**,**/bin/**,**/obj/**"

    dotnet build "$SCRIPT_DIR/RiparianPoc.sln" --no-incremental

    dotnet sonarscanner end /d:sonar.token="$SONAR_TOKEN"
    local exit_code=$?

    # Restore sonar-project.properties
    if [ -f "$SCRIPT_DIR/sonar-project.properties.bak" ]; then
        mv "$SCRIPT_DIR/sonar-project.properties.bak" "$SCRIPT_DIR/sonar-project.properties"
    fi

    [ $exit_code -ne 0 ] && exit $exit_code

    info "Analysis complete! View results at http://localhost:9000/dashboard?id=riparian-poc-dotnet"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

case "${1:-}" in
    --status)       cmd_status ;;
    --stop)         cmd_stop ;;
    --restart)      cmd_restart ;;
    --update)       cmd_update "${2:-all}" ;;
    --sonar)        cmd_sonar_start ;;
    --sonar-stop)   cmd_sonar_stop ;;
    --lint)         cmd_lint ;;
    --lint-dotnet)  cmd_lint_dotnet ;;
    --help|-h)
        echo "Usage: ./dev.sh [OPTION]"
        echo ""
        echo "  (no args)          Start everything (checks drive, builds, starts Aspire, applies schema)"
        echo "  --status           Check service health and data counts"
        echo "  --restart          Restart all services"
        echo "  --stop             Stop Aspire (PostGIS container persists)"
        echo "  --update [type]    Run incremental update (full|incremental|ndvi|all)"
        echo ""
        echo "  Code Quality (SonarQube):"
        echo "  --sonar            Start SonarQube server (http://localhost:9000)"
        echo "  --sonar-stop       Stop SonarQube server (data persists)"
        echo "  --lint             Run analysis: Python + TypeScript + SQL"
        echo "  --lint-dotnet      Run analysis: C# .NET projects"
        echo ""
        echo "  --help             Show this help"
        ;;
    "")             cmd_start ;;
    *)              error "Unknown option: $1 (try --help)"; exit 1 ;;
esac
