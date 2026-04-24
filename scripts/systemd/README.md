# systemd units for geo-mcp

Units that run ops tasks on a schedule, installed system-wide (so they
survive a reboot).

## Nightly meta-schema backup

Dumps `meta.customers` / `meta.api_keys` / `meta.usage_log` to
`/data/backups/meta-*.sql.gz` every night at 03:17 UTC, keeps the last
30, prunes older.

Before installing, edit `geo-mcp-backup.service` and replace the
`CHANGEME` user/group + the `/opt/geo-mcp` paths with whatever matches
your host (e.g. `User=rob` + `WorkingDirectory=/home/rob/geo-mcp`).

```sh
sudo cp scripts/systemd/geo-mcp-backup.service /etc/systemd/system/
sudo cp scripts/systemd/geo-mcp-backup.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now geo-mcp-backup.timer

# Check it's armed:
systemctl list-timers geo-mcp-backup.timer

# Run once manually (sanity):
sudo systemctl start geo-mcp-backup.service
journalctl -u geo-mcp-backup.service -n 50
```

The service runs as the configured user against the host's `pg_dump`
(which talks to the Docker-hosted PostgreSQL on `127.0.0.1:5432` using
the credentials in `.env`). No sudo needed once the unit is installed.

## Restore drill

No timer — run ad-hoc after any schema migration or when a recovery
path needs verifying:

```sh
./scripts/restore-drill.sh
```

Creates `geo_restore_drill` scratch database, pg_restores the most
recent backup, asserts row counts on the three core tables, drops the
scratch database. Fails loudly if the backup looks suspicious.

## Offsite backup

`scripts/backup.sh` also `rclone`-syncs the local backup directory to
an S3-compatible remote if one is configured (env `GEO_MCP_OFFSITE_REMOTE`,
default `r2`). Silently skipped when no rclone remote is set up, so
the local backup path works standalone.

Typical setup: a Cloudflare R2 bucket + a read/write API token, added
to `rclone.conf` under the `r2` remote name. See `scripts/backup.sh`
for the exact env variables used.
