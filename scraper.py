#!/usr/bin/env python3
"""Fetch listings from Trackr's API, notify when applications open."""

import itertools
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).parent
STATE_FILE = ROOT / "state.json"
CONFIG_FILE = ROOT / "config.yaml"


def load_config():
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"notified": {}, "last_run": None}


def save_state(state):
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def fetch_listings(region, industry, season, listing_type):
    resp = requests.get(
        "https://api.the-trackr.com/programmes",
        params={
            "region": region,
            "industry": industry,
            "season": season,
            "type": listing_type,
        },
        headers={
            "Accept": "application/json",
            "Origin": "https://app.the-trackr.com",
            "Referer": "https://app.the-trackr.com/",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def listing_key(item):
    return f"{item['companyId']}|{item['name']}|{item['type']}"


def is_open(item, today):
    """Application is open: opening date has passed and closing date hasn't."""
    opening = item.get("openingDate")
    closing = item.get("closingDate")
    if not opening:
        return False
    if opening[:10] > today:
        return False
    if closing and closing[:10] < today:
        return False
    return True


def format_email(listings, watchlist_slugs):
    lines = [f"{len(listings)} applications just opened — {date.today().isoformat()}\n"]

    def fmt(l):
        company = (l.get("company") or {}).get("name", l["companyId"])
        closing = l.get("closingDate")
        deadline = closing[:10] if closing else ("Rolling" if l.get("rolling") else "?")
        star = " *" if l["companyId"] in watchlist_slugs else ""
        line = f"- {company}{star} — {l['name']} | Closes: {deadline}"
        if l.get("url"):
            line += f"\n  {l['url']}"
        return line

    priority = [l for l in listings if l["companyId"] in watchlist_slugs]
    other = [l for l in listings if l["companyId"] not in watchlist_slugs]

    if priority:
        lines.append(f"WATCHLIST ({len(priority)})\n")
        lines.extend(fmt(l) for l in priority)
        lines.append("")
    if other:
        lines.append(f"OTHER ({len(other)})\n")
        lines.extend(fmt(l) for l in other)

    return "\n".join(lines)


def send_email(subject, body, config):
    api_key = os.environ.get("RESEND_API_KEY")
    to_email = os.environ.get("NOTIFY_EMAIL", config.get("email"))

    if not api_key or not to_email:
        print("RESEND_API_KEY or NOTIFY_EMAIL not set — printing instead:\n")
        print(body)
        return False

    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "from": "Trackr Scanner <onboarding@resend.dev>",
            "to": [to_email],
            "subject": subject,
            "text": body,
        },
        timeout=10,
    )
    if resp.ok:
        print(f"Email sent to {to_email}")
        return True
    print(f"Email failed ({resp.status_code}): {resp.text}")
    print(body)
    return False


def main():
    config = load_config()
    state = load_state()
    already_notified = set(state.get("notified", {}).keys())
    watchlist = set(config.get("watchlist", []))

    today = date.today().isoformat()
    all_listings = []

    regions = config.get("regions", ["UK"])
    industries = config.get("industries", ["Finance"])
    seasons = config.get("seasons", ["2026"])
    types = config.get("types", ["summer-internships"])

    for region, industry, season, typ in itertools.product(regions, industries, seasons, types):
        label = f"{region} {industry} {typ} {season}"
        print(f"Fetching {label}...")
        try:
            listings = fetch_listings(region, industry, season, typ)
            print(f"  {len(listings)} listings")
            all_listings.extend(listings)
        except Exception as e:
            print(f"  Error: {e}")

    # find listings that are currently open and we haven't notified about
    newly_open = [
        l for l in all_listings
        if is_open(l, today) and listing_key(l) not in already_notified
    ]

    print(f"\nTotal: {len(all_listings)} | Already notified: {len(already_notified)} | Newly open: {len(newly_open)}")

    # mark these as notified
    notified = state.get("notified", {})
    for l in newly_open:
        notified[listing_key(l)] = {
            "company": (l.get("company") or {}).get("name", l["companyId"]),
            "programme": l["name"],
            "notified_on": today,
        }
    state["notified"] = notified
    save_state(state)

    if not already_notified:
        print("First run — baseline saved, no notification sent")
    elif newly_open:
        body = format_email(newly_open, watchlist)
        subject = f"Trackr: {len(newly_open)} application{'s' if len(newly_open) != 1 else ''} opened"
        send_email(subject, body, config)
    else:
        print("No new openings")


if __name__ == "__main__":
    main()
