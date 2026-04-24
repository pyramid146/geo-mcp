# Contributing to geo-mcp

Thanks for looking at this. geo-mcp is maintained as a one-person
project around a commercial product, so the bar for contributions is:

1. **Open an issue first.** Even for small changes. It's much faster
   to align on "is this a good idea / what should it look like" in an
   issue than to review a PR nobody asked for. Use the issue
   templates (`.github/ISSUE_TEMPLATE/`) — they filter most of the
   "what information do you need?" round-trip.

2. **Match the existing style.** The code has strong conventions
   (tool responses are dicts, errors are `{"error": ..., "message": ...}`,
   every response carries `attribution`, coverage caveats surface as
   `verdict: "coverage_gap"` rather than silent nulls). Mirror them.

3. **Tests come with the code.** Every tool has at least one test
   exercising the happy path and one edge case. Ingest scripts + SQL
   migrations don't need tests but do need a verifying command you
   ran and the output it produced.

4. **Commits are conventional-ish.** Prefixes we use:
   `feat`, `fix`, `refactor`, `docs`, `ops`, `security`, `perf`, `test`,
   `chore`. Subject line under ~72 chars; body explains *why*.

## Setting up locally

See [DEVELOPMENT.md](./DEVELOPMENT.md). You need Docker + Python 3.12
+ PostGIS + about 60 GB of free disk after ingest. Running the full
ingest chain is a multi-hour job.

Many datasets aren't needed for most changes — just load the ones
your change touches.

## What I'm NOT looking for

- PRs against markdown-only product copy without a prior issue. The
  README + landing page are deliberately hand-tuned.
- Dependency upgrades for their own sake.
- New tools without a clear user question they answer. The bar is
  "an agent can do X that it couldn't do before" — "we have data Y
  so we should expose it" isn't enough.

## Security issues

Don't file a public issue. Email
[cairo.pyramids@protonmail.com](mailto:cairo.pyramids@protonmail.com)
with details. Response within 72 hours.
