"""Admin CLI for API key provisioning.

Run as:
    python -m geo_mcp.admin mint-key --email alice@example.com [--label "LLM agent"]
    python -m geo_mcp.admin list-keys [--email alice@example.com]
    python -m geo_mcp.admin revoke-key <key-id>

The plaintext key is printed exactly once at mint-time — save it somewhere
safe, the server only stores its hash.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from geo_mcp.auth import list_keys, mint_key, revoke_key
from geo_mcp.data_access.postgis import close_pool


async def _cmd_mint(args: argparse.Namespace) -> int:
    raw, meta = await mint_key(email=args.email, label=args.label)
    print()
    print("  NEW API KEY (shown once — save it now):")
    print(f"    {raw}")
    print()
    print(f"  customer_id:  {meta['customer_id']}")
    print(f"  email:        {meta['email']}")
    print(f"  tier:         {meta['tier']}")
    print(f"  key_id:       {meta['key_id']}")
    print(f"  key_prefix:   {meta['key_prefix']}")
    if meta.get("label"):
        print(f"  label:        {meta['label']}")
    print()
    print("  The server stores sha256(key) + the 12-char prefix above.")
    print("  A lost key cannot be recovered — mint a new one and revoke the old.")
    return 0


async def _cmd_list(args: argparse.Namespace) -> int:
    rows = await list_keys(email=args.email)
    if not rows:
        print("No keys.")
        return 0
    for r in rows:
        status = "revoked" if r["revoked_at"] else "active"
        last = r["last_used_at"].isoformat() if r["last_used_at"] else "never"
        print(
            f"{r['key_prefix']}...  {status:7}  {r['email']:32}  tier={r['tier']:6}  "
            f"created={r['created_at'].isoformat()}  last_used={last}  id={r['id']}  "
            f"label={r['label'] or ''}"
        )
    return 0


async def _cmd_revoke(args: argparse.Namespace) -> int:
    ok = await revoke_key(args.key_id)
    if ok:
        print(f"Revoked {args.key_id}.")
        return 0
    print(f"No active key with id {args.key_id}.", file=sys.stderr)
    return 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="geo_mcp.admin", description="geo-mcp admin CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("mint-key", help="Create a new API key for a customer (by email).")
    m.add_argument("--email", required=True)
    m.add_argument("--label", help="Optional user-friendly name for the key")
    m.set_defaults(run=_cmd_mint)

    ls = sub.add_parser("list-keys", help="List keys, optionally filtered by customer email.")
    ls.add_argument("--email", help="Filter by customer email")
    ls.set_defaults(run=_cmd_list)

    rv = sub.add_parser("revoke-key", help="Revoke an API key by id.")
    rv.add_argument("key_id")
    rv.set_defaults(run=_cmd_revoke)

    return p


def main() -> None:
    args = _build_parser().parse_args()

    async def _run() -> int:
        try:
            return await args.run(args)
        finally:
            await close_pool()

    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
