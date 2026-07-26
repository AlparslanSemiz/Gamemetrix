#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--apply" ]]; then
  echo "Refusing to change the firewall without --apply." >&2
  exit 2
fi
if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root from a second, verified SSH session." >&2
  exit 2
fi
if [[ -z "${SSH_CONNECTION:-}" ]]; then
  echo "SSH_CONNECTION is missing; refusing to risk remote lockout." >&2
  exit 2
fi

work_dir="$(mktemp -d)"
trap 'rm -rf -- "$work_dir"' EXIT
curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
  https://www.cloudflare.com/ips-v4/ > "$work_dir/ips-v4"
curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
  https://www.cloudflare.com/ips-v6/ > "$work_dir/ips-v6"

python3 - "$work_dir/ips-v4" "$work_dir/ips-v6" <<'PY'
import ipaddress
import pathlib
import sys

for filename in sys.argv[1:]:
    rows = pathlib.Path(filename).read_text(encoding="ascii").splitlines()
    if not rows:
        raise SystemExit(f"Empty Cloudflare range list: {filename}")
    for row in rows:
        ipaddress.ip_network(row.strip(), strict=True)
PY

install -d -m 700 /var/backups/gamemetrix
ufw show added > "/var/backups/gamemetrix/ufw-added-$(date -u +%Y%m%dT%H%M%SZ).rules"

ufw limit OpenSSH
while IFS= read -r cidr; do
  ufw allow proto tcp from "$cidr" to any port 80 comment "Cloudflare HTTP"
  ufw allow proto tcp from "$cidr" to any port 443 comment "Cloudflare HTTPS"
done < <(cat "$work_dir/ips-v4" "$work_dir/ips-v6")

# Remove only broad web rules. Source-specific Cloudflare rules remain.
while ufw status | grep -Eq '^80/tcp[[:space:]]+ALLOW IN[[:space:]]+Anywhere'; do
  ufw --force delete allow 80/tcp
done
while ufw status | grep -Eq '^443/tcp[[:space:]]+ALLOW IN[[:space:]]+Anywhere'; do
  ufw --force delete allow 443/tcp
done

ufw default deny incoming
ufw default allow outgoing
ufw --force enable
ufw status verbose
