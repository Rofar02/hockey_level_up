#!/usr/bin/env bash
# One-shot setup for a clean Ubuntu server, run once as root right after
# first login. Installs Docker only -- everything runs as root (no
# separate deploy user, no firewall/fail2ban/unattended-upgrades). This is
# the deliberately minimal version for a small-audience deployment where
# login is root + the password Timeweb generates; hardening (key-only SSH,
# a non-root deploy user, UFW, fail2ban, secret rotation) is a later pass,
# not part of this script. See docs/deploy.md for the full runbook this
# fits into -- this script only covers what has to happen before the repo
# is even cloned.
#
# Usage (as root, on the fresh server):
#   curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/deploy/server-setup.sh | bash
# or copy it over and run `bash server-setup.sh` after reviewing it.

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this as root (fresh server, first login)." >&2
  exit 1
fi

echo "==> apt update/upgrade"
apt-get update -y
apt-get upgrade -y

echo "==> Installing Docker Engine + Compose plugin"
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

MEM_KB=$(awk '/MemTotal/ {print $2}' /proc/meminfo)
MEM_MB=$((MEM_KB / 1024))
if [ "$MEM_MB" -le 2200 ]; then
  echo "==> ${MEM_MB}MB RAM detected -- adding a 2GB swapfile (frontend build needs headroom)"
  if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
  fi
fi

cat <<EOF

==> Done. Next steps (see docs/deploy.md):
  1. Point icelevel.ru and www.icelevel.ru DNS A records at this server's IP.
  2. Clone the repo (as root) and continue the runbook from there.
EOF
