# Cloudflare Tunnel setup for geo-mcp

Exposes the local MCP server at `https://geomcp.dev` via a persistent
outbound connection to Cloudflare. No inbound ports opened on your
router, no public IP leak, TLS + DDoS handled at the edge.

## One-time setup

The binary ships in `~/.local/bin/cloudflared` after running
`scripts/cloudflared/install-binary.sh` (or downloading it manually).

### 1. Authenticate cloudflared with your Cloudflare account

```bash
cloudflared tunnel login
```

Opens a Cloudflare URL in your browser; you pick `geomcp.dev` from the
list. Writes `~/.cloudflared/cert.pem` — tied to your CF account, do
not commit it.

### 2. Create the tunnel

```bash
cloudflared tunnel create geo-mcp
```

Prints a UUID and writes `~/.cloudflared/<UUID>.json` (the tunnel's
credentials). Keep this file safe — anyone with it can route traffic
into your blackbird.

### 3. Route DNS at the apex

```bash
cloudflared tunnel route dns geo-mcp geomcp.dev
```

Creates a CNAME record in Cloudflare DNS pointing `geomcp.dev` at
`<UUID>.cfargotunnel.com`. Cloudflare's CNAME flattening makes this
work at the apex (regular DNS forbids CNAMEs on the apex).

### 4. Install the config + credentials system-wide

```bash
sudo mkdir -p /etc/cloudflared
# Copy the sample and fill in <TUNNEL_ID> with the UUID from step 2:
sudo cp scripts/cloudflared/config.yml /etc/cloudflared/config.yml
sudo $EDITOR /etc/cloudflared/config.yml   # replace both <TUNNEL_ID> placeholders
sudo cp ~/.cloudflared/<UUID>.json /etc/cloudflared/
sudo chmod 600 /etc/cloudflared/*.json
```

### 5. Install and start the systemd service

Before installing, edit the sample unit and replace `CHANGEME` with
your Linux user (e.g. `rob`):

```bash
sudo $EDITOR scripts/cloudflared/cloudflared.service   # replace CHANGEME
sudo cp scripts/cloudflared/cloudflared.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cloudflared
```

Check it's up:

```bash
systemctl status cloudflared
journalctl -u cloudflared -n 30 --no-pager
```

### 6. Smoke-test from outside Tailscale

From a laptop not on your Tailnet, or your phone on mobile data:

```bash
curl -sS https://geomcp.dev/health
```

Expected: `{"status":"ok","postgres":true,"tools":21,"meta_rows":{...}}`.

## Operating notes

- **Restart the MCP server, not cloudflared.** `cloudflared` stays up
  independently of the Python process; when you restart `geo-mcp`,
  cloudflared will reconnect to the origin as soon as 127.0.0.1:8000
  is responding again.
- **cloudflared auto-updates binaries itself** if run under systemd —
  the service downloads new versions on a timer.
- **To stop exposing the server**: `sudo systemctl stop cloudflared`.
  The tunnel closes; `geomcp.dev` becomes unreachable from outside;
  nothing else on blackbird is affected.
