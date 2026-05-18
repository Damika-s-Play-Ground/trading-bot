# VPS runtime packaging

This repo now includes systemd-oriented runtime packaging for 24/7 hosting.

What it gives you
- trading-bot-web.service: keeps the Flask dashboard/API running with auto-restart.
- trading-bot-cycle.timer: runs the manager + futures + dashboard regeneration cycle every 30 minutes.
- trading-bot-healthcheck.timer: checks /healthz every 5 minutes and restarts the web service if it stops responding.
- flock-based overlap protection for scheduled bot cycles.
- .env-driven config so secrets and DB credentials stay outside git.

Files
- scripts/run_web.sh
- scripts/run_cycle.sh
- scripts/healthcheck.sh
- deploy/systemd/*.template
- deploy/install_systemd.sh

Quick install on a VPS
1. Clone the repo.
2. Create .env from .env.example and fill in DATABASE_URL + API keys.
3. Create the venv and install dependencies:
   ./venv/bin/pip install -r requirements.txt
4. Install the services as root:
   sudo bash deploy/install_systemd.sh /absolute/path/to/trading-bot your-linux-user
5. Verify:
   systemctl status trading-bot-web.service
   systemctl status trading-bot-cycle.timer
   systemctl status trading-bot-healthcheck.timer
   curl -fsS http://127.0.0.1:8008/healthz

Operational notes
- The web service reads APP_HOST / APP_PORT / BUILD_ON_START from .env.
- The cycle runner writes to logs/runtime-cycle.log.
- The cycle runner skips overlapping runs instead of stacking them.
- Templates are rendered with the repo path and run user at install time so the checked-in files stay portable.
- If you already use Hermes cron on the VPS, disable the systemd cycle timer or the Hermes job to avoid double execution.
