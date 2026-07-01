#!/usr/bin/env python3
"""
Notification helper: sends Teams adaptive card and/or email with Approve/Deny links.
Called by Ansible via 'command' module or directly.

Usage:
  python3 notify.py --host myserver --trigger "Disk 90% full" \
    --approve-url https://auto.example.com/approve?token=X&sig=Y \
    --deny-url   https://auto.example.com/deny?token=X&sig=Y \
    --summary "Top 5 files consuming disk:\n1. /var/log/app.log 20GB" \
    [--teams-webhook URL] [--smtp-host HOST --smtp-to user@example.com]
"""

import argparse
import json
import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

TEAMS_WEBHOOK = os.environ.get("TEAMS_WEBHOOK_URL", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "automation@example.com")
SMTP_TO = os.environ.get("SMTP_TO", "")


def send_teams(webhook_url: str, host: str, trigger: str, summary: str, approve_url: str, deny_url: str):
    # Microsoft Teams Adaptive Card via Incoming Webhook
    card = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": "🚨 Automation Approval Required",
                            "weight": "Bolder",
                            "size": "Large",
                            "color": "Attention",
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Host", "value": host},
                                {"title": "Alert", "value": trigger},
                            ],
                        },
                        {
                            "type": "TextBlock",
                            "text": "**Analysis:**",
                            "weight": "Bolder",
                        },
                        {
                            "type": "TextBlock",
                            "text": summary.replace("\n", "\n\n"),
                            "wrap": True,
                            "fontType": "Monospace",
                        },
                        {
                            "type": "TextBlock",
                            "text": "Please approve or deny the automated action:",
                            "wrap": True,
                        },
                    ],
                    "actions": [
                        {
                            "type": "Action.OpenUrl",
                            "title": "✅ Approve",
                            "url": approve_url,
                            "style": "positive",
                        },
                        {
                            "type": "Action.OpenUrl",
                            "title": "❌ Deny",
                            "url": deny_url,
                            "style": "destructive",
                        },
                    ],
                },
            }
        ],
    }
    resp = requests.post(webhook_url, json=card, timeout=30)
    resp.raise_for_status()
    print(f"[Teams] Notification sent: HTTP {resp.status_code}")


def send_email(to: str, host: str, trigger: str, summary: str, approve_url: str, deny_url: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Automation] Approval Required: {trigger} on {host}"
    msg["From"] = SMTP_FROM
    msg["To"] = to

    plain = (
        f"Automation Approval Required\n\n"
        f"Host: {host}\nAlert: {trigger}\n\n"
        f"Analysis:\n{summary}\n\n"
        f"APPROVE: {approve_url}\n"
        f"DENY:    {deny_url}\n"
    )

    html = f"""<html><body style="font-family:sans-serif">
<h2 style="color:#c00">🚨 Automation Approval Required</h2>
<table border="0" cellpadding="6">
  <tr><td><strong>Host</strong></td><td>{host}</td></tr>
  <tr><td><strong>Alert</strong></td><td>{trigger}</td></tr>
</table>
<h3>Analysis</h3>
<pre style="background:#f4f4f4;padding:12px;border-radius:4px">{summary}</pre>
<p>Please choose an action:</p>
<a href="{approve_url}" style="background:#28a745;color:#fff;padding:10px 20px;
   text-decoration:none;border-radius:4px;margin-right:12px">✅ Approve</a>
<a href="{deny_url}" style="background:#dc3545;color:#fff;padding:10px 20px;
   text-decoration:none;border-radius:4px">❌ Deny</a>
<br><br><small>This link expires in 1 hour.</small>
</body></html>"""

    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        if SMTP_USER:
            server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_FROM, [to], msg.as_string())
    print(f"[Email] Notification sent to {to}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--trigger", required=True)
    parser.add_argument("--approve-url", required=True)
    parser.add_argument("--deny-url", required=True)
    parser.add_argument("--summary", default="No summary provided.")
    parser.add_argument("--teams-webhook", default=TEAMS_WEBHOOK)
    parser.add_argument("--smtp-to", default=SMTP_TO)
    args = parser.parse_args()

    sent = False
    errors = []

    if args.teams_webhook:
        try:
            send_teams(args.teams_webhook, args.host, args.trigger, args.summary, args.approve_url, args.deny_url)
            sent = True
        except Exception as e:
            errors.append(f"Teams: {e}")

    if args.smtp_to and SMTP_HOST:
        try:
            send_email(args.smtp_to, args.host, args.trigger, args.summary, args.approve_url, args.deny_url)
            sent = True
        except Exception as e:
            errors.append(f"Email: {e}")

    if not sent:
        print(f"[ERROR] No notification sent. Errors: {errors}", file=sys.stderr)
        sys.exit(1)

    if errors:
        print(f"[WARN] Some channels failed: {errors}")


if __name__ == "__main__":
    main()
