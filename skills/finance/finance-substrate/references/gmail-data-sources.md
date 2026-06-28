# Gmail Data Sources for Tax & Finance

Reference for extracting tax-relevant data from Gmail using GWS CLI (`gws`).

## Setup

```bash
npx skills add googleworkspace/cli -y -g
gws auth login  # Opens browser for Google OAuth
```

## Source Registry

### Salary Income

| Source | Query | Data extracted | Tax relevance |
|--------|-------|---------------|---------------|
| **Thera** | `from:thera received payment` | USD amount, employer name, payment date | R32 ingresos brutos (salary in USD) |

**Thera email format:**
```
Subject: You just received a payment!
Body: "You received USD XXXX for your contract with <Employer> on Thera."
```

Parser extracts: `USD (\d+)` from body text. Payments may be bi-monthly or monthly depending on contract.

**Known issues:**
- Some payments may show different amounts (bonuses, partial months)
- Employer name may change if contract is renewed
- Email subject is consistent: "You just received a payment!"

### Bank Statements & Certificates

| Source | Query | Key emails |
|--------|-------|------------|
| **Davivienda** | `from:davivienda (extracto OR certificado OR transaccion)` | Monthly extractos (PDF), certificado tributario, transaction alerts |
| **Nu Colombia** | `from:nu.com.co` | Account notifications, rendimientos, certificado anual |
| **Nequi** | `from:nequi` | Transaction confirmations, certificado tributario |
| **RappiPay/RappiCard** | `from:rappipay OR from:rappicard` | Payment notifications, certificado tributario |
| **Banco Falabella** | `from:falabella (certificado OR extracto)` | Certificado tributario, extracto TC |
| **Skandia** | `from:skandia` | Pension fund notifications, extractos, certificado tributario |

**Davivienda extracto format:**
- Subject: `Extractos Portafolio Banco Davivienda YYYYMMDD`
- Usually has PDF attachment with monthly statement
- Sent monthly around the 3rd-5th of the following month

### Social Security

| Source | Query | Data extracted |
|--------|-------|---------------|
| **Compensar** | `from:compensar (planilla OR pago OR parafiscal)` | PILA payment confirmations |

### Tax Authority

| Source | Query | Key emails |
|--------|-------|------------|
| **DIAN** | `from:dian.gov.co` | Firma electrónica, RUT copy, verification codes, exogena notifications |

## GWS CLI Patterns

### Search messages
```bash
gws gmail users messages list --params '{"userId": "me", "q": "from:davivienda extracto after:2025/01/01", "maxResults": 10}'
```

### Get message details
```bash
gws gmail users messages get --params '{"userId": "me", "id": "<MSG_ID>", "format": "metadata"}'
```

### Get message body (full)
```bash
gws gmail users messages get --params '{"userId": "me", "id": "<MSG_ID>", "format": "full"}'
# Body is base64url-encoded in payload.parts[].body.data
```

### Download attachment
```bash
gws gmail users messages attachments get --params '{"userId": "me", "messageId": "<MSG_ID>", "id": "<ATTACHMENT_ID>"}'
# Returns base64url-encoded data in .data field
```

### Paginate all results
```bash
gws gmail users messages list --params '{"userId": "me", "q": "from:thera after:2025/01/01"}' --page-all --page-limit 5
```

## Integration Strategy

### Annual tax preparation workflow

```bash
# 1. Collect all salary payment emails → verify income total
python3 scripts/gmail_collector.py --year 2025 --source thera

# 2. Download bank statements with attachments
python3 scripts/gmail_collector.py --year 2025 --source davivienda --download-attachments

# 3. Collect all sources for completeness check
python3 scripts/gmail_collector.py --year 2025

# 4. Cross-reference Gmail salary total vs salary-history.jsonl
# Compare Gmail payment count × avg amount against ledger total
# Gap: some payments in late Dec may be dated Jan, or format varies

# 5. Download certificates when available (Jan-Mar of following year)
python3 scripts/gmail_collector.py --year 2025 --source skandia --download-attachments
python3 scripts/gmail_collector.py --year 2025 --source davivienda --download-attachments
```

### Automated monthly monitoring

The collector can be run monthly to track:
- New salary payments received
- Bank statement availability
- DIAN notifications requiring action
- Compensar PILA payment confirmations

## GWS CLI for Other Services

Beyond Gmail, GWS CLI can enhance the skill with:

### Google Sheets — Tax tracking spreadsheet
```bash
# Create a spreadsheet for tracking monthly income/expenses
gws sheets spreadsheets create --json '{"properties": {"title": "Tax Tracker 2025"}}'

# Write salary data
gws sheets spreadsheets values update --params '{"spreadsheetId": "...", "range": "A1"}' --json '{"values": [["Month", "USD", "TRM", "COP"]]}'
```

### Google Calendar — Tax deadline reminders
```bash
# Create reminders for filing deadlines
gws calendar events insert --params '{"calendarId": "primary"}' --json '{
  "summary": "DIAN Renta AG 2025 - Fecha límite (CC ...70)",
  "start": {"date": "2026-09-30"},
  "end": {"date": "2026-10-01"},
  "reminders": {"useDefault": false, "overrides": [{"method": "email", "minutes": 10080}]}
}'
```

### Google Drive — Document organization
```bash
# Upload tax documents to Drive for backup
gws drive files create --params '{"name": "Certificado-Davivienda-2025.pdf", "parents": ["<FOLDER_ID>"]}' --upload ./cert.pdf

# Search for tax documents already in Drive
gws drive files list --params '{"q": "name contains '\''certificado'\'' and mimeType='\''application/pdf'\''", "pageSize": 10}'
```
