#!/usr/bin/env bash
# One-shot setup for a clean Ubuntu server, run once as root right after
# first login. Installs Docker, locks down the firewall/SSH, and creates a
# non-root deploy user. See docs/deploy.md for the full runbook this fits
# into -- this script only covers what has to happen before the repo is
# even cloned.
#
# Usage (as root, on the fresh server):
#   curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/deploy/server-setup.sh | bash
# or copy it over and run `bash server-setup.sh` after reviewing it -- for
# a script that hardens SSH and opens a firewall, reading it first before
# piping it into a root shell is the more sensible default.

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this as root (fresh server, first login)." >&2
  exit 1
fi

DEPLOY_USER="${DEPLOY_USER:-icelevel}"

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

echo "==> Creating deploy user '$DEPLOY_USER' (in the docker group, no password login)"
if ! id "$DEPLOY_USER" &>/dev/null; then
  adduser --disabled-password --gecos "" "$DEPLOY_USER"
  usermod -aG docker "$DEPLOY_USER"
  mkdir -p "/home/$DEPLOY_USER/.ssh"
  if [ -f /root/.ssh/authorized_keys ]; then
    cp /root/.ssh/authorized_keys "/home/$DEPLOY_USER/.ssh/authorized_keys"
  fi
  chown -R "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
  chmod 700 "/home/$DEPLOY_USER/.ssh"
  chmod 600 "/home/$DEPLOY_USER/.ssh/authorized_keys" 2>/dev/null || true
fi

echo "==> UFW: deny everything incoming except SSH/HTTP/HTTPS"
apt-get install -y ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> fail2ban (SSH brute-force protection)"
apt-get install -y fail2ban
systemctl enable --now fail2ban

echo "==> unattended-upgrades (security patches applied automatically)"
apt-get install -y unattended-upgrades
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "==> Hardening sshd (key-only, no root login)"
SSHD_CONFIG=/etc/ssh/sshd_config
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' "$SSHD_CONFIG"
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' "$SSHD_CONFIG"
echo "NOT restarting sshd automatically -- confirm '$DEPLOY_USER' can log in with a key FIRST,"
echo "in a separate session, before running: systemctl restart sshd"

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
  1. In a NEW terminal, confirm you can SSH in as '$DEPLOY_USER' with your key.
     Only after that succeeds: systemctl restart sshd
  2. Point icelevel.ru and www.icelevel.ru DNS A records at this server's IP.
  3. Log in as '$DEPLOY_USER', clone the repo, continue the runbook from there.
EOF
