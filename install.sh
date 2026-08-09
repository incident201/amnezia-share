#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo ./install.sh" >&2
  exit 1
fi

if command -v apt-get >/dev/null 2>&1; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y qrencode openssh-client curl iproute2
elif command -v pacman >/dev/null 2>&1; then
  pacman -S --needed --noconfirm qrencode openssh curl iproute2
else
  echo "Install qrencode, OpenSSH client (ssh-keygen), curl and iproute2 manually." >&2
fi

install -m 0755 ./amnezia-share /usr/local/bin/amnezia-share

echo
echo "Installed: /usr/local/bin/amnezia-share"
echo "Run read-only diagnostics first:"
echo "  amnezia-share doctor"
