#!/usr/bin/env python3
"""Fetch UK finance listings from Trackr's API, diff against previous state, email new ones."""

import json
import os
import sys
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
    return {"listings": {}, "last_run": None}


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


def find_new(current, previous_keys):
    return [item for item in current if listing_key(item) not in previous_keys]


def format_email(new_listings, watchlist_slugs):
    priority = [l for l in new_listings if l["companyId"] in watchlist_slugs]
    other = [l for l in new_listings if l["companyId"] not in watchlist_slugs]

    lines = [f"{len(new_listings)} new listings on Trackr — {date.today().isoformat()}\n"]

    def fmt(l):
        company = l.get("company", {}).get("name", l["companyId"])
        closing = l.get("closingDate")
        if closing:
            deadline = closing[:10]
        elif l.get("rolling"):
            deadline = "Rolling"
        else:
            deadline = "?"
        line = f"- {company} — {l['name']} | Deadline: {deadline} | {l.get('type', '')}"
        if l.get("url"):
            line += f"\n  {l['url']}"
        return line

    if priority:
        lines.append(f"=== WATCHLIST ({len(priority)}) ===\n")
        lines.extend(fmt(l) for l in priority)
        lines.append("")

    if other:
        lines.append(f"=== Other ({len(other)}) ===\n")
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
    previous_keys = set(state.get("listings", {}).keys())
    watchlist = set(config.get("watchlist", []))

    current_keys = {}
    all_current = []

    for scan in config["scans"]:
        label = f"{scan['region']} {scan['industry']} {scan['type']} {scan['season']}"
        print(f"Fetching {label}...")
        try:
            listings = fetch_listings(
                scan["region"], scan["industry"], scan["season"], scan["type"]
            )
            print(f"  {len(listings)} listings")
            all_current.extend(listings)
            for item in listings:
                current_keys[listing_key(item)] = {
                    "company": item.get("company", {}).get("name", item["companyId"]),
                    "programme": item["name"],
                    "type": item["type"],
                    "closingDate": item.get("closingDate"),
                }
        except Exception as e:
            print(f"  Error: {e}")

    # filter out expired
    today = date.today().isoformat()
    new_open = [
        l
        for l in find_new(all_current, previous_keys)
        if not l.get("closingDate") or l["closingDate"][:10] >= today
    ]

    print(f"\nTotal: {len(current_keys)} | Known: {len(previous_keys)} | New: {len(new_open)}")

    state["listings"] = current_keys
    save_state(state)

    if not previous_keys:
        print("First run — baseline saved, no notification sent")
    elif new_open:
        body = format_email(new_open, watchlist)
        subject = f"Trackr: {len(new_open)} new listing{'s' if len(new_open) != 1 else ''}"
        send_email(subject, body, config)
    else:
        print("No new listings")


if __name__ == "__main__":
    main()
