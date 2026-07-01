#!/usr/bin/env python3
"""
Zabbix alert script: triggers a Semaphore CI/CD job based on alert type.

Place this file in Zabbix's AlertScripts directory (default: /usr/lib/zabbix/alertscripts/).
Configure a Zabbix Media Type (Script) with parameters:
  {ALERT.SENDTO}   -> semaphore project ID (e.g. "1")
  {ALERT.SUBJECT}  -> alert subject (used to detect alert type)
  {ALERT.MESSAGE}  -> JSON payload: {"host": "...", "ip": "...", "trigger": "...", "severity": "..."}
"""

import sys
import json
import os
import requests
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler("/tmp/semaphore_trigger.log"), logging.StreamHandler()],
)
log = logging.getLogger(__name__)

SEMAPHORE_URL = os.environ.get("SEMAPHORE_URL", "http://semaphore:3000")
SEMAPHORE_TOKEN = os.environ.get("SEMAPHORE_TOKEN", "")

# Map alert keywords to Semaphore template IDs
# Set these IDs after importing templates into Semaphore
TEMPLATE_MAP = {
    "disk": int(os.environ.get("SEMAPHORE_TEMPLATE_DISK", "1")),
    "service": int(os.environ.get("SEMAPHORE_TEMPLATE_SERVICE", "2")),
    "zabbix agent": int(os.environ.get("SEMAPHORE_TEMPLATE_AGENT", "3")),
    "paloalto": int(os.environ.get("SEMAPHORE_TEMPLATE_PALOALTO", "4")),
}


def detect_alert_type(subject: str) -> str:
    subject_lower = subject.lower()
    for keyword in TEMPLATE_MAP:
        if keyword in subject_lower:
            return keyword
    return "service"


def trigger_semaphore_job(project_id: int, template_id: int, extra_vars: dict) -> dict:
    headers = {
        "Authorization": f"Bearer {SEMAPHORE_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "template_id": template_id,
        "debug": False,
        "dry_run": False,
        "environment": json.dumps(extra_vars),
    }
    url = f"{SEMAPHORE_URL}/api/v1/project/{project_id}/tasks"
    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def main():
    if len(sys.argv) < 4:
        log.error("Usage: semaphore_trigger.py <project_id> <subject> <message_json>")
        sys.exit(1)

    project_id_str, subject, message_raw = sys.argv[1], sys.argv[2], sys.argv[3]

    try:
        project_id = int(project_id_str)
    except ValueError:
        log.error("project_id must be an integer, got: %s", project_id_str)
        sys.exit(1)

    try:
        alert_data = json.loads(message_raw)
    except json.JSONDecodeError:
        # Fall back: treat raw string as trigger name
        alert_data = {"trigger": message_raw, "host": "unknown", "ip": "unknown", "severity": "average"}

    alert_type = detect_alert_type(subject)
    template_id = TEMPLATE_MAP[alert_type]

    extra_vars = {
        "alert_host": alert_data.get("host", "unknown"),
        "alert_ip": alert_data.get("ip", "unknown"),
        "alert_trigger": alert_data.get("trigger", subject),
        "alert_severity": alert_data.get("severity", "average"),
        "alert_type": alert_type,
        "zabbix_subject": subject,
    }

    log.info(
        "Triggering Semaphore job: project=%s template=%s host=%s type=%s",
        project_id, template_id, extra_vars["alert_host"], alert_type,
    )

    result = trigger_semaphore_job(project_id, template_id, extra_vars)
    log.info("Semaphore task created: %s", result)


if __name__ == "__main__":
    main()
