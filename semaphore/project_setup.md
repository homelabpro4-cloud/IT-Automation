# Semaphore Project Setup

## 1. Create a Semaphore Project

1. Log in to Semaphore UI.
2. **New Project** → Name: `IT-Automation`
3. Set **Git repository** to this repo URL.

---

## 2. Key Store (Credentials)

Add the following keys under **Key Store**:

| Name | Type | Value |
|---|---|---|
| `linux-ssh-key` | SSH | Private key for Linux hosts |
| `windows-creds` | Login | Domain\user / password |
| `paloalto-creds` | Login | admin / password |
| `vault-password` | Password | Ansible vault password |

---

## 3. Environment Variables

Create an **Environment** named `automation-env` with these variables:

```
SEMAPHORE_TOKEN=<semaphore api token>
SEMAPHORE_URL=http://semaphore:3000
APPROVAL_SERVER_URL=http://semaphore:5050
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/...
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USER=automation@yourdomain.com
SMTP_PASS=<app-password>
SMTP_FROM=automation@yourdomain.com
SMTP_TO=alerts@yourdomain.com
APPROVAL_SECRET=<random-32-char-string>
PUBLIC_URL=https://automation.yourdomain.com
```

---

## 4. Inventory

Create **Inventory** entries (or use `inventory/hosts.yml` from this repo):

| Name | Type |
|---|---|
| `linux-inventory` | File → `inventory/hosts.yml` (linux group) |
| `windows-inventory` | File → `inventory/hosts.yml` (windows group) |
| `paloalto-inventory` | File → `inventory/hosts.yml` (paloalto group) |

---

## 5. Templates (Job Definitions)

Create one template per alert type. Template IDs must match `SEMAPHORE_TEMPLATE_*` env vars in the Zabbix script.

### Template 1 – Disk Alert (ID: 1)
- **Playbook**: `playbooks/disk_alert.yml`
- **Inventory**: dynamic (use `--limit` or `alert_host` extra var)
- **Environment**: `automation-env`

### Template 2 – Service Alert (ID: 2)
- **Playbook**: `playbooks/service_alert.yml`
- **Environment**: `automation-env`

### Template 3 – Zabbix Agent Alert (ID: 3)
- **Playbook**: `playbooks/service_alert.yml`
- **Extra vars**: `alert_service_name=zabbix-agent2`
- **Environment**: `automation-env`

### Template 4 – Palo Alto Alert (ID: 4)
- **Playbook**: `playbooks/paloalto_alert.yml`
- **Inventory**: paloalto-inventory
- **Environment**: `automation-env`

---

## 6. Zabbix Configuration

### Alert Script
1. Copy `zabbix/alertscripts/semaphore_trigger.py` to `/usr/lib/zabbix/alertscripts/`
2. `chmod +x semaphore_trigger.py`
3. Set `SEMAPHORE_URL` and `SEMAPHORE_TOKEN` in `/etc/zabbix/zabbix_server.conf` or as env vars.

### Media Type
1. **Administration → Media Types → Create**
   - Name: `Semaphore Automation`
   - Type: `Script`
   - Script name: `semaphore_trigger.py`
   - Parameters:
     - `{ALERT.SENDTO}` → Semaphore project ID (e.g. `1`)
     - `{ALERT.SUBJECT}`
     - `{ALERT.MESSAGE}`

### Action → Media
2. **Configuration → Actions → Trigger Actions → Create**
   - Conditions: `Trigger severity >= Average` AND `Trigger name contains "disk"` (repeat for service/paloalto)
   - Operations: Send message via `Semaphore Automation`
   - Message format (JSON):
     ```json
     {"host": "{HOST.NAME}", "ip": "{HOST.IP}", "trigger": "{TRIGGER.NAME}", "severity": "{TRIGGER.SEVERITY}"}
     ```

---

## 7. Approval Server (Systemd Service)

```ini
# /etc/systemd/system/approval-server.service
[Unit]
Description=Automation Approval Server
After=network.target

[Service]
User=semaphore
WorkingDirectory=/opt/it-automation
EnvironmentFile=/opt/it-automation/.env
ExecStart=/usr/bin/python3 scripts/approval_server.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now approval-server
```
