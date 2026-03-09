#!/usr/bin/env bash
set -euo pipefail

##
## 部署脚本：把当前 RSI 项目部署到 Linux 服务器（systemd 方式守护）
##
## 作用：
##   - 安装基础依赖（python3, python3-venv, rsync, nginx）
##   - 创建 /opt/bquant/rsi 目录并同步代码
##   - 在 /opt/bquant/venv-rsi 创建虚拟环境并安装 requirements.txt
##   - 生成 Nginx 反向代理配置（rsi.bquant.com → 127.0.0.1:8000）
##   - 安装 systemd 单元 rsi.service 并启动
##
## 用法（在服务器上，从项目根目录执行）：
##
##   sudo ./deploy_rsi.sh
##

BASE_DIR="/opt/bquant/rsi"
VENV_DIR="/opt/bquant/venv-rsi"
RSI_DOMAIN="rsi.bquant.com"
APP_USER="rsi"
APP_GROUP="rsi"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { echo "[deploy-rsi] $*"; }
die() { echo "[deploy-rsi] ERROR: $*" >&2; exit 1; }

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    die "请以 root 身份运行（使用 sudo）"
  fi
}

has_cmd() { command -v "$1" >/dev/null 2>&1; }

detect_pkg_mgr() {
  if has_cmd apt-get; then echo "apt"; return; fi
  if has_cmd dnf; then echo "dnf"; return; fi
  if has_cmd yum; then echo "yum"; return; fi
  die "未检测到受支持的包管理器（apt/dnf/yum）"
}

install_pkgs() {
  local mgr; mgr="$(detect_pkg_mgr)"
  log "使用 ${mgr} 安装基础依赖..."
  if [[ "${mgr}" == "apt" ]]; then
    apt-get update -y
    apt-get install -y python3 python3-venv rsync nginx
  elif [[ "${mgr}" == "dnf" ]]; then
    dnf install -y python3 rsync nginx
  else
    yum install -y python3 rsync nginx
  fi
}

ensure_user() {
  if id "${APP_USER}" >/dev/null 2>&1; then
    log "用户 ${APP_USER} 已存在"
  else
    log "创建系统用户 ${APP_USER}..."
    useradd --system --home "${BASE_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
  fi

  if getent group "${APP_GROUP}" >/dev/null 2>&1; then
    log "用户组 ${APP_GROUP} 已存在"
  else
    log "创建系统用户组 ${APP_GROUP}..."
    groupadd --system "${APP_GROUP}" || true
  fi

  usermod -a -G "${APP_GROUP}" "${APP_USER}" || true
}

sync_code() {
  log "创建目录 ${BASE_DIR} ..."
  mkdir -p "${BASE_DIR}"

  log "同步代码到 ${BASE_DIR} ..."
  rsync -a --delete-delay \
    --exclude ".git" \
    --exclude ".env" \
    --exclude "__pycache__" \
    --exclude "*.pyc" \
    "${REPO_ROOT}/" "${BASE_DIR}/"

  if [[ ! -f "${BASE_DIR}/.env" && -f "${BASE_DIR}/.env.example" ]]; then
    log "检测到 .env 不存在，从 .env.example 复制一份（请手动编辑密钥）"
    cp "${BASE_DIR}/.env.example" "${BASE_DIR}/.env"
  fi

  chown -R "${APP_USER}:${APP_GROUP}" "${BASE_DIR}"
}

create_venv() {
  log "创建虚拟环境 ${VENV_DIR} ..."
  python3 -m venv "${VENV_DIR}"

  log "安装 Python 依赖..."
  "${VENV_DIR}/bin/pip" install -U pip wheel setuptools
  if [[ -f "${BASE_DIR}/requirements.txt" ]]; then
    "${VENV_DIR}/bin/pip" install -r "${BASE_DIR}/requirements.txt"
  else
    log "未找到 requirements.txt，跳过依赖安装"
  fi
}

install_systemd_unit() {
  local unit_src="${BASE_DIR}/rsi.service"
  local unit_dst="/etc/systemd/system/rsi.service"

  if [[ ! -f "${unit_src}" ]]; then
    die "未找到 ${unit_src}，请确认 rsi.service 已随代码一起同步到服务器"
  fi

  log "安装 systemd 单元到 ${unit_dst} ..."
  cp "${unit_src}" "${unit_dst}"

  systemctl daemon-reload
  systemctl enable --now rsi.service
  systemctl restart rsi.service
}

nginx_conf_path() {
  if [[ -d /etc/nginx/sites-available ]]; then
    echo "/etc/nginx/sites-available/rsi.conf"
  else
    echo "/etc/nginx/conf.d/rsi.conf"
  fi
}

setup_nginx() {
  if ! has_cmd nginx; then
    log "未检测到 nginx，跳过反向代理配置"
    return
  fi

  log "配置 Nginx 反向代理 (${RSI_DOMAIN} → 127.0.0.1:8000)..."
  local conf; conf="$(nginx_conf_path)"

  mkdir -p "$(dirname "${conf}")"
  cat > "${conf}" <<EOF
upstream rsi_upstream {
  server 127.0.0.1:8000;
  keepalive 16;
}

server {
  listen 80;
  server_name ${RSI_DOMAIN};

  location /ws {
    proxy_pass http://rsi_upstream;
    proxy_http_version 1.1;
    proxy_set_header Upgrade \$http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
  }

  location / {
    proxy_pass http://rsi_upstream;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
  }
}
EOF

  # Debian 系列启用站点
  if [[ -d /etc/nginx/sites-enabled ]]; then
    ln -sf "${conf}" /etc/nginx/sites-enabled/rsi.conf
  fi

  nginx -t
  systemctl enable --now nginx
  systemctl reload nginx
}

main() {
  require_root

  install_pkgs
  ensure_user
  sync_code
  create_venv
  install_systemd_unit
  setup_nginx

  log "部署完成。"
  log "可用命令： systemctl status rsi.service"
  log "如 DNS 已指向本机，可通过: http://${RSI_DOMAIN} 访问"
}

main "$@"
