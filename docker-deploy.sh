#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# RSI Bot — Docker 部署脚本
# 用法: bash docker-deploy.sh [start|stop|restart|logs|status|clean]
# ─────────────────────────────────────────────────────────────────────────────

set -e

COMPOSE="docker compose"
PROJECT_NAME="rsi-bot"

# ── Color output ──────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log_info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
log_ok()    { echo -e "${GREEN}[ OK ]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ── Pre-flight checks ─────────────────────────────────────────────────────────
check_docker() {
  if ! command -v docker &> /dev/null; then
    log_error "Docker is not installed. Please install Docker first."
    exit 1
  fi
  if ! docker info &> /dev/null; then
    log_error "Docker daemon is not running. Please start Docker."
    exit 1
  fi
  if ! $COMPOSE version &> /dev/null; then
    log_error "Docker Compose is not available. Please install Docker Compose."
    exit 1
  fi
}

ensure_env() {
  if [ ! -f .env ]; then
    log_warn ".env not found, copying from .env.docker ..."
    if [ -f .env.docker ]; then
      cp .env.docker .env
      log_warn "Please edit .env and set your SECRET_KEY and ENCRYPTION_KEY before starting!"
    else
      log_error ".env.docker not found either. Cannot create .env automatically."
      exit 1
    fi
  fi

  # Ensure data/ directory exists for SQLite persistence
  if [ ! -d data ]; then
    mkdir -p data
    log_info "Created ./data/ directory for database persistence."
  fi

  # Patch DATABASE_URL to use /app/data/ path inside the container
  if grep -q "DATABASE_URL=sqlite:///" .env 2>/dev/null; then
    if ! grep -q "sqlite:///./data/" .env 2>/dev/null; then
      sed -i.bak 's|DATABASE_URL=sqlite:///.*|DATABASE_URL=sqlite:///./data/trading.db|' .env
      log_info "Patched DATABASE_URL to persist to ./data/trading.db"
    fi
  fi
}

# ── Commands ───────────────────────────────────────────────────────────────────
cmd_start() {
  check_docker
  ensure_env
  log_info "Building Docker image (this may take a few minutes on first run)..."
  $COMPOSE build --pull
  log_info "Starting RSI Bot..."
  $COMPOSE up -d
  log_ok "RSI Bot started!"
  log_info "Access the app at: http://localhost:\${WEB_PORT:-8000}"
  log_info "API docs at:        http://localhost:\${WEB_PORT:-8000}/docs"
  $COMPOSE ps
}

cmd_stop() {
  check_docker
  log_info "Stopping RSI Bot..."
  $COMPOSE down
  log_ok "RSI Bot stopped."
}

cmd_restart() {
  check_docker
  cmd_stop
  cmd_start
}

cmd_logs() {
  check_docker
  $COMPOSE logs -f --tail=100
}

cmd_status() {
  check_docker
  echo ""
  echo "=== Container Status ==="
  $COMPOSE ps
  echo ""
  echo "=== Container Health ==="
  $COMPOSE ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
}

cmd_clean() {
  check_docker
  log_warn "This will remove ALL containers, images, and volumes for this project!"
  read -p "Type 'yes' to confirm: " confirm
  if [ "$confirm" = "yes" ]; then
    $COMPOSE down --volumes --rmi local
    log_ok "Cleaned up."
  else
    log_info "Cancelled."
  fi
}

cmd_rebuild() {
  check_docker
  ensure_env
  log_info "Rebuilding image without cache..."
  $COMPOSE build --no-cache
  $COMPOSE up -d --force-recreate
  log_ok "Rebuilt and restarted!"
}

# ── Main ──────────────────────────────────────────────────────────────────────
ACTION="${1:-start}"

case "$ACTION" in
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  restart) cmd_restart ;;
  logs)    cmd_logs ;;
  status)  cmd_status ;;
  clean)   cmd_clean ;;
  rebuild) cmd_rebuild ;;
  *)
    echo "用法: bash docker-deploy.sh [start|stop|restart|logs|status|clean|rebuild]"
    echo ""
    echo "Commands:"
    echo "  start   — Build and start the container (first run)"
    echo "  stop    — Stop and remove the container"
    echo "  restart — Stop then start"
    echo "  logs    — Tail live container logs"
    echo "  status  — Show container status"
    echo "  clean   — Remove containers, images, and volumes"
    echo "  rebuild — Rebuild image without cache and restart"
    exit 1
    ;;
esac
