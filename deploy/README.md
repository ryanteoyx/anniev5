# Deploying Annie on an Oracle Cloud Always Free VM

Annie runs as a normal long-lived Streamlit server, so it needs a real VM rather than a
serverless host. This folder sets one up on Ubuntu 24.04 (Ampere/ARM, Always Free shape).

| File | Purpose |
|------|---------|
| `setup.sh` | One-time (re-runnable) setup: packages, app user, code, venv, service, HTTPS proxy, firewall |
| `annie.service` | systemd unit that keeps Streamlit running on `127.0.0.1:8501` and restarts it if it stops |

## Layout on the VM

- Code: `/opt/annie/app` (a clone of this repo's `ui-polish` branch)
- Python env: `/opt/annie/venv`
- Data: `/opt/annie/app/annie_v4.db` and `/opt/annie/app/storage/` — on the VM's disk, so they survive restarts
- Email intake (optional): put the `EMAIL_*` settings in `/opt/annie/app/.env`, then `sudo systemctl restart annie`

Caddy terminates HTTPS on ports 80/443 and proxies to Streamlit (websockets included).
A free `<ip-with-dashes>.sslip.io` hostname points at the VM's IP, so no domain is needed.

## First deploy

On the VM (as the default `ubuntu` user):

```bash
curl -fsSL https://raw.githubusercontent.com/ryanteoyx/anniev5/ui-polish/deploy/setup.sh -o setup.sh
bash setup.sh 129-146-10-20.sslip.io                     # public, no login
bash setup.sh 129-146-10-20.sslip.io admin '<bcrypt>'    # behind a browser login
```

Generate the bcrypt hash on the VM with `caddy hash-password`.

## Updating after you push changes

Re-run the same `setup.sh` command: it pulls the latest `ui-polish`, reinstalls requirements
and restarts the service.

## Useful commands

```bash
sudo systemctl status annie        # is it running?
sudo journalctl -u annie -f        # live app logs
sudo systemctl restart annie       # restart the app
```

## Oracle notes

- The VCN's security list must allow inbound TCP 80 and 443 (only 22 is open by default).
- Oracle may reclaim Always Free instances that stay idle for 7 days (low CPU, network and
  memory use). Upgrading the account to Pay As You Go removes that rule; Always Free resources
  stay free.
