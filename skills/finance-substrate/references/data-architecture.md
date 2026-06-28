# Data Architecture — Finance Substrate

## Document Flow

```
Gmail (automated via GWS CLI)
  gws gmail → scripts/gmail_collector.py
    ├── Thera salary payment emails → salary amounts in USD
    ├── Davivienda extracto PDFs → bank statements
    ├── Skandia/Nu/Nequi/Rappi notifications → certificate alerts
    ├── Compensar PILA confirmations → parafiscales verification
    └── DIAN notifications → filing reminders, RUT copies

DIAN MUISCA (automated via agent-browser)
  agent-browser → scripts/import_certificates.py
    ├── Exogena XLSX → third-party reported data
    ├── E-invoices XLSX → electronic invoice history
    └── RUT PDF → taxpayer registration

Source documents (user provides)
  ~/Dropbox/Declaracion/<year>/
    ├── Certificado Tributario *.pdf     ← Bank/institution tax certificates
    ├── Planillas/Planilla *.pdf         ← Monthly PILA social security slips
    ├── Reporte Informacion Exogena.xlsx ← DIAN exogena (manual download)
    ├── Reporte Facturas Electronicas.xlsx ← DIAN e-invoices (manual download)
    ├── Reporte Salarios.xlsx            ← Salary payment history
    ├── Extractos Davivienda/            ← Bank statement PDFs + consolidated xlsx
    ├── Borrador Declaración*.pdf        ← DIAN draft declaration (for calibration)
    └── MUISCA/                          ← Auto-downloaded from DIAN portal
        ├── reporteExogena<year>.xlsx
        ├── Reporte-Facturas-Electronicas-<year>.xlsx
        └── RUT-Copia.pdf
         ↓
Import scripts parse source documents
  scripts/import_certificates.py --password <CC>
  scripts/import_declaracion.py --year <year>
  scripts/import_planillas.py --year <year>
         ↓
Processed data (local, not in repo)
  ~/.finance-substrate/
    ├── ledger/
    │   ├── transactions.jsonl        ← Bank transactions (deduped, categorized)
    │   ├── accounts.json             ← Account registry
    │   └── rules.json                ← Auto-categorization rules
    ├── tax/
    │   ├── salary-history.jsonl      ← Monthly salary with FX details
    │   ├── certificates.jsonl        ← Parsed institution certificates
    │   ├── exogena.jsonl             ← DIAN third-party reported data
    │   ├── planillas.jsonl           ← Monthly social security payments
    │   └── withholdings.jsonl        ← Retenciones tracking
    ├── fx/
    │   └── trm-history.jsonl         ← USD/COP exchange rate cache
    ├── invoices/
    │   └── received/
    │       └── e-invoices.jsonl      ← DIAN electronic invoices received
    └── dian-session.json             ← MUISCA browser session (SENSITIVE)
         ↓
Tax engine computes
  scripts/tax_projection.py --year <year>
  scripts/optimize_deductions.py
         ↓
Output: Form 210 values
  scripts/fill_form210.py → agent-browser commands for DIAN wizard
```

## Storage Locations

| Location | Contents | Backup | Sensitive? |
|----------|----------|--------|------------|
| `~/Dropbox/Declaracion/<year>/` | Source PDFs, XLSX, certificates | Dropbox sync | Yes (PII in PDFs) |
| `~/Dropbox/Declaracion/<year>/MUISCA/` | Auto-downloaded DIAN exports | Dropbox sync | Yes |
| `~/.finance-substrate/` | Processed JSONL data | **Not backed up** — regenerable from source docs | Yes (parsed PII) |
| `~/.finance-substrate/dian-session.json` | MUISCA auth cookies | **Not backed up** | **Highly sensitive** — contains session tokens |
| `~/.agents/skills/finance-substrate/` | Skill code (installed) | Git repo at broomva/finance-substrate | No PII |

## MUISCA Download Convention

When downloading from DIAN MUISCA via agent-browser, files land in `~/Downloads/`.
After download, move them to `~/Dropbox/Declaracion/<year>/MUISCA/` with clear names:

| DIAN filename | Renamed to |
|--------------|------------|
| `reporteExogena<year>.xlsx` | `reporteExogena<year>.xlsx` |
| `report.xlsx` | `Reporte-Facturas-Electronicas-<year>.xlsx` |
| `<number>.pdf` (RUT) | `RUT-Copia.pdf` |

## Data Regeneration

All processed data in `~/.finance-substrate/` can be regenerated from source documents:
```bash
# Regenerate everything from source PDFs and XLSX
python3 scripts/import_declaracion.py --year 2024
python3 scripts/import_certificates.py --year 2024 --password <CC>
python3 scripts/import_planillas.py --year 2024
python3 scripts/self_heal.py --year 2024
python3 scripts/tax_projection.py --year 2024
```

## Year-by-Year Directory Structure

```
~/Dropbox/Declaracion/
├── 2021/
├── 2022/
├── 2023/
│   ├── Certificado *.pdf
│   ├── international_transfers_2023.csv
│   ├── national_transfers_2023.csv
│   └── Pagos Parafiscales/
├── 2024/
│   ├── Certificado Tributario *.pdf (10 institutions)
│   ├── Planillas/Planilla * 2024.pdf (12 months)
│   ├── Extractos Davivienda/ (12 months + consolidated xlsx)
│   ├── Reporte Informacion Exogena.xlsx
│   ├── Reporte Facturas Electronicas.xlsx
│   ├── Reporte Salarios.xlsx
│   ├── Borrador Declaración de Renta 2024.pdf
│   ├── Comprobante Pago DIAN Renta 2025.pdf
│   └── MUISCA/ (auto-downloaded)
└── 2025/
    └── (in progress)
```

## Security Notes

- **Never commit** `~/.finance-substrate/` contents to git
- **Never commit** source PDFs or XLSX to git
- The DIAN session file (`dian-session.json`) contains auth tokens — delete after use or encrypt
- PDF passwords (CC number) should be prompted at runtime, never stored in scripts
- The skill repo (`broomva/finance-substrate`) contains zero PII — verified by `grep` sweep
