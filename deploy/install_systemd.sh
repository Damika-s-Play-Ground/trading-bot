#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/install_systemd.sh [repo_root] [run_user]" >&2
  exit 1
fi

REPO_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RUN_USER="${2:-$(logname 2>/dev/null || echo ${SUDO_USER:-root})}"
SYSTEMD_DIR="/etc/systemd/system"
TEMPLATE_DIR="$REPO_ROOT/deploy/systemd"

render_unit() {
  local template="$1"
  local output="$2"
  sed \
    -e "s|__REPO_ROOT__|$REPO_ROOT|g" \
    -e "s|__RUN_USER__|$RUN_USER|g" \
    "$template" > "$output"
}

install -d -m 755 "$SYSTEMD_DIR"
chmod +x "$REPO_ROOT/scripts/run_web.sh" "$REPO_ROOT/scripts/run_cycle.sh" "$REPO_ROOT/scripts/healthcheck.sh"

render_unit "$TEMPLATE_DIR/trading-bot-web.service.template" "$SYSTEMD_DIR/trading-bot-web.service"
render_unit "$TEMPLATE_DIR/trading-bot-cycle.service.template" "$SYSTEMD_DIR/trading-bot-cycle.service"
render_unit "$TEMPLATE_DIR/trading-bot-cycle.timer.template" "$SYSTEMD_DIR/trading-bot-cycle.timer"
render_unit "$TEMPLATE_DIR/trading-bot-healthcheck.service.template" "$SYSTEMD_DIR/trading-bot-healthcheck.service"
render_unit "$TEMPLATE_DIR/trading-bot-healthcheck.timer.template" "$SYSTEMD_DIR/trading-bot-healthcheck.timer"

systemctl daemon-reload
systemctl enable --now trading-bot-web.service
systemctl enable --now trading-bot-cycle.timer
systemctl enable --now trading-bot-healthcheck.timer

echo "Installed trading-bot-web.service, trading-bot-cycle.timer, and trading-bot-healthcheck.timer"
echo "Inspect with: systemctl status trading-bot-web.service trading-bot-cycle.timer trading-bot-healthcheck.timer"
