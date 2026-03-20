# Trackr Scanner

Daily scan of [app.the-trackr.com](https://app.the-trackr.com/uk-finance/) for new UK finance openings. Runs on GitHub Actions, emails you when new listings appear. Watchlist companies get highlighted at the top.

## Setup

1. Fork/clone this repo
2. Sign up at [resend.com](https://resend.com) (free — 100 emails/day)
3. Add repo secrets:
   - `RESEND_API_KEY` — from Resend dashboard
   - `NOTIFY_EMAIL` — your email address
4. Edit `config.yaml` to adjust scans and watchlist
5. Run the workflow manually once to establish baseline (no email sent on first run)

## How it works

The scraper hits Trackr's public API, diffs against `state.json`, and emails you any listings it hasn't seen before. State is committed back to the repo after each run.

Scans default to UK Finance across summer internships, spring weeks, off-cycle, and events. Edit `config.yaml` to change regions, industries, or seasons.

## Config

```yaml
scans:          # API queries to run (region, industry, season, type)
watchlist:      # company slugs to highlight in notifications
email:          # fallback if NOTIFY_EMAIL secret isn't set
```

Valid values: region (`UK`, `NA`, `EU`), industry (`Finance`, `Technology`, `Law`), type (`summer-internships`, `spring-weeks`, `off-cycle-internships`, `events`).
