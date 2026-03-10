#!/usr/bin/env bash
# =============================================================================
# update_server.sh — 一键更新服务器前后端代码
#
# 用法：
#   ./update_server.sh              # 自动判断是否需要构建前端
#   ./update_server.sh --fe         # 强制重新构建前端
#   ./update_server.sh --no-fe      # 跳过前端构建
#   ./update_server.sh --no-push    # 只更新服务器，不做 git commit/push
#
# 依赖：ssh、git、node（可选，仅前端改动时需要）
# =============================================================================

set -euo pipefail

# ── 配置 ─────────────────────────────────────────────────────────────────────
SERVER_USER="root"
SERVER_IP="157.173.207.152"
SERVER_DIR="/opt/bquant/rsi"
SERVICE_NAME="rsi.service"
SSH_OPTS="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -o PasswordAuthentication=yes"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="${SCRIPT_DIR}/frontend"
# ─────────────────────────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${CYAN}[update]${NC} $*"; }
ok()   { echo -e "${GREEN}[  ok  ]${NC} $*"; }
warn() { echo -e "${YELLOW}[ warn ]${NC} $*"; }
die()  { echo -e "${RED}[error ]${NC} $*" >&2; exit 1; }

# ── 参数解析 ──────────────────────────────────────────────────────────────────
BUILD_FE="auto"   # auto | yes | no
DO_PUSH=true

for arg in "$@"; do
  case "$arg" in
    --fe)      BUILD_FE="yes" ;;
    --no-fe)   BUILD_FE="no" ;;
    --no-push) DO_PUSH=false ;;
    --help|-h)
      sed -n '2,12p' "$0" | sed 's/^# //'
      exit 0 ;;
    *) die "未知参数: $arg （用 --help 查看帮助）" ;;
  esac
done

# ── 检测前端是否有改动（auto 模式）───────────────────────────────────────────
fe_has_changes() {
  # 检查 frontend/src/ 或 frontend/vite.config.js 是否有未提交/已提交的变更
  local changed
  changed=$(git -C "${SCRIPT_DIR}" status --porcelain -- frontend/src frontend/vite.config.js frontend/index.html 2>/dev/null | wc -l)
  [[ "$changed" -gt 0 ]]
}

# ── 构建前端 ──────────────────────────────────────────────────────────────────
build_frontend() {
  if [[ ! -d "${FRONTEND_DIR}" ]]; then
    warn "frontend/ 目录不存在，跳过构建"
    return
  fi

  if ! command -v node >/dev/null 2>&1; then
    warn "本机未安装 Node.js，跳过构建（使用已提交的 dist/）"
    return
  fi

  log "安装前端依赖..."
  npm --prefix "${FRONTEND_DIR}" install --silent

  log "构建 Vue 前端..."
  npm --prefix "${FRONTEND_DIR}" run build

  ok "前端构建完成 → frontend/dist/"
}

# ── git commit & push ────────────────────────────────────────────────────────
git_push() {
  cd "${SCRIPT_DIR}"

  local status
  status=$(git status --porcelain 2>/dev/null | wc -l)

  if [[ "$status" -eq 0 ]]; then
    ok "工作区干净，无需 commit"
  else
    log "暂存并提交本地变更..."
    git add -A
    # 生成提交信息：列出改动文件
    local msg="chore: update $(date '+%Y-%m-%d %H:%M')"
    git commit -m "${msg}"
    ok "已 commit: ${msg}"
  fi

  log "推送到 Gitee..."
  git push origin master
  ok "推送成功"
}

# ── 更新服务器 ────────────────────────────────────────────────────────────────
update_server() {
  local ssh_target="${SERVER_USER}@${SERVER_IP}"
  log "连接服务器 ${ssh_target}..."

  ssh ${SSH_OPTS} "${ssh_target}" bash <<EOF
set -euo pipefail

echo "[server] 当前目录: ${SERVER_DIR}"
cd "${SERVER_DIR}"

echo "[server] git pull..."
git pull origin master

echo "[server] 重启服务 ${SERVICE_NAME}..."
systemctl restart ${SERVICE_NAME}

echo "[server] 服务状态："
systemctl is-active ${SERVICE_NAME} && echo "  → 运行中" || echo "  → 启动失败，请检查日志"

echo "[server] 最新 5 条日志："
journalctl -u ${SERVICE_NAME} -n 5 --no-pager 2>/dev/null || true
EOF

  ok "服务器更新完成"
}

# ── 主流程 ────────────────────────────────────────────────────────────────────
main() {
  echo -e "${CYAN}================================================${NC}"
  echo -e "${CYAN}  RSI Bot — 服务器更新脚本${NC}"
  echo -e "${CYAN}  目标: ${SERVER_USER}@${SERVER_IP}:${SERVER_DIR}${NC}"
  echo -e "${CYAN}================================================${NC}"

  # 1. 决定是否构建前端
  if [[ "${BUILD_FE}" == "yes" ]]; then
    log "强制构建前端..."
    build_frontend
  elif [[ "${BUILD_FE}" == "auto" ]]; then
    if fe_has_changes; then
      log "检测到前端改动，自动构建..."
      build_frontend
    else
      log "前端无改动，跳过构建"
    fi
  else
    log "已跳过前端构建（--no-fe）"
  fi

  # 2. commit + push
  if $DO_PUSH; then
    git_push
  else
    log "已跳过 git push（--no-push）"
  fi

  # 3. 服务器拉代码 + 重启
  update_server

  echo ""
  ok "全部完成！访问 http://${SERVER_IP} 验证"
}

main
