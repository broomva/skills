# DIAN MUISCA Browser Automation Reference

Technical reference for automating access to the DIAN MUISCA portal using `agent-browser`.

## Portal Architecture

| Layer | Technology | URL Pattern |
|-------|-----------|-------------|
| Login SPA | Custom JS (WSO2-style OAuth) | `muisca.dian.gov.co/WebIdentidadLogin/` |
| Auth callback | REST STS | `/IdentidadRest_LoginFiltro/api/sts/v1/auth/callback` |
| Portal | JavaServer Faces (JSF) | `muisca.dian.gov.co/WebArquitectura/DefLogin.faces` |
| Session | JSESSIONID cookie + JSF ViewState | Server-side state saving |

## Login Flow

The login URL encodes an OAuth-like request as base64 JSON in the `ideRequest` parameter:
```json
{
  "clientId": "Wo0aKAlB7vRP_16frPI1x9ZphBEa",
  "redirect_uri": "http://muisca.dian.gov.co/IdentidadRest_LoginFiltro/api/sts/v1/auth/callback?redirect_uri=...",
  "params": {"tipoUsuario": "muisca"}
}
```

On successful auth, the SPA redirects through the STS callback to the JSF portal at `DefLogin.faces`.

Error code `10001` in the `ideRequest` = invalid credentials.

## Working Login Sequence (agent-browser)

```bash
# 1. Open MUISCA — auto-redirects to WebIdentidadLogin SPA
agent-browser open "https://muisca.dian.gov.co/"
agent-browser wait --load networkidle
agent-browser wait 2000

# 2. Open document type dropdown (must click to expand, not use select)
agent-browser snapshot -i
agent-browser click @e8          # listbox ref
agent-browser snapshot -i        # Re-snapshot to see options

# 3. Select "Cédula de ciudadanía" by clicking the option directly
# IMPORTANT: Do NOT use `select` command — it resets other form fields
agent-browser click @e17         # "Cédula de ciudadanía" option ref
agent-browser wait 1000          # Wait for field enable animation

# 4. Fill credentials
agent-browser fill @e9 "<CC_NUMBER>"
agent-browser fill @e10 '<PASSWORD>'   # Single quotes for special chars (!@#)

# 5. Accept terms
agent-browser check @e15         # "Acepto el tratamiento de datos personales"

# 6. Submit
agent-browser click @e12         # "Ingresar" button

# 7. Wait for redirect to JSF portal
agent-browser wait --url "**/DefLogin.faces"

# 8. Save session for reuse
agent-browser state save dian-auth.json
```

## Known Issues

### `select` resets form fields
The `agent-browser select` command on the document type listbox triggers a form reset
in the SPA, clearing other fields. **Always use `click` on the option element directly.**

### Special characters in password
Passwords with `!`, `$`, or backticks cause shell expansion issues.
- Use **single quotes** around the password in `fill` command
- If that fails, use JS eval with `--stdin`:
  ```bash
  agent-browser eval --stdin <<'EOF'
  const input = document.querySelector('input[type="password"]');
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  setter.call(input, 'password_here');
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
  EOF
  ```
- **Note**: JS-set values may not trigger SPA framework bindings. Prefer `fill`.

### Password expiration
DIAN passwords expire periodically. If `codigo_error: 10001` appears, verify
credentials manually at `muisca.dian.gov.co` before debugging automation.

### Angular SPA login workaround
The login SPA uses Angular with `ngModel` bindings. Playwright's `fill` sets the DOM value
and shows `ng-reflect-model` correctly, but the Angular form validation doesn't trigger
submission reliably via programmatic click. **Recommended workflow**:
1. Open headed browser: `agent-browser --headed --session dian open "https://muisca.dian.gov.co/"`
2. Log in manually in the visible browser window
3. Save session: `agent-browser --session dian state save ~/.finance-substrate/dian-session.json`
4. All subsequent operations are fully automated

## Post-Login Navigation

Dashboard URL: `https://muisca.dian.gov.co/WebDashboard/DefDashboard.faces`

| Service | URL | Data |
|---------|-----|------|
| Dashboard | `/WebDashboard/DefDashboard.faces` | Main portal with all links |
| RUT copy | Click "Obtener copia RUT" Submit button | Downloads PDF automatically |
| Filed documents | `/WebDiligenciamiento/DefConsDocumentos.faces` | Tax returns |
| Payment receipts | `/WebDiligenciamiento/DefConsultaYPagoRecibos.faces` | Payment history |
| Form filing | `/WebDiligenciamiento/DefDiligenciamientoFormularios.faces` | Fill tax forms |
| Exogena | Click "Consultar información Exógena" Submit | XLSX download after year select |
| E-invoices | Click "Consulta Facturas electrónicas" Submit | XLSX download after year select |

## Tested Download Sequences (Validated March 2026)

### Exogena (reporteExogena{year}.xlsx)
```bash
# From dashboard — click the Submit button next to "Consultar información Exógena"
agent-browser snapshot -i
agent-browser click @e18                    # Submit button for exogena
agent-browser wait 3000
agent-browser snapshot -i -C                # Find Aceptar in terms dialog
agent-browser click @e20                    # "Aceptar" (Submit in dialog)
agent-browser wait 3000
agent-browser snapshot -i                   # Find year combobox
agent-browser select @e24 "2024"            # Select year
agent-browser wait 500
agent-browser click @e25                    # Submit next to year → triggers XLSX download
# File appears in ~/Downloads/reporteExogena2024.xlsx
```

### E-Invoices (report.xlsx)
```bash
# From dashboard — click Submit next to "Consulta Facturas electrónicas"
agent-browser click @e17                    # Submit for e-invoices
agent-browser wait 5000                     # Terms dialog loads
agent-browser snapshot -i -C
agent-browser click @e18                    # "Aceptar" in terms dialog
agent-browser wait 3000
agent-browser snapshot -i                   # Year combobox appears
agent-browser select @e21 "2024"
agent-browser wait 500
agent-browser click @e22                    # Submit → triggers XLSX download
# File appears in ~/Downloads/report.xlsx
```

### RUT (PDF)
```bash
# From dashboard — click Submit next to "Obtener copia RUT"
agent-browser click @e9                     # Submit for RUT
agent-browser wait 8000                     # PDF downloads automatically
# File appears in ~/Downloads/<numero>.pdf
```

### Notes on JSF dialog flow
All data downloads follow the same pattern:
1. Click Submit button on dashboard → terms dialog opens as modal overlay
2. Click "Aceptar" (Submit inside dialog) → year selector appears
3. Select year from combobox → click Submit → file downloads
4. Dialog closes, back to dashboard

Ref numbers (`@eN`) change between sessions — always `snapshot -i` before interacting.

## Form 210 — Declaración de Renta Filing

### Creating a Draft
```bash
# From dashboard — click "Presentar Declaración de Renta"
agent-browser snapshot -i
agent-browser click @e26                    # "Presentar Declaración de Renta" link

# On the "Declaraciones presentadas" page — click sidebar icon 2
agent-browser eval 'document.querySelectorAll(".step-counter")[1]?.click() || document.querySelectorAll(".stepper-item")[1]?.click()'
# Or navigate directly:
agent-browser open "https://muisca.dian.gov.co/WebDilIngresoFormRenta210/#/ingreso/crearFormulario"
agent-browser wait 3000

# Select year and create
agent-browser snapshot -i
agent-browser select @e6 "2024"             # Year dropdown
agent-browser wait 1000
agent-browser click @e4                     # "Crear" button
agent-browser wait 8000

# NOTE: If year already has "Inicial", DIAN returns error:
# "Ya ha presentado una declaración... debe diligenciar una corrección"
# In that case, select a different year or use "Corrección" mode
```

### Answering Preliminary Questions
```bash
# Step 0: Residency question
agent-browser snapshot -i
agent-browser click @e7                     # ">183 días" = tax resident
agent-browser wait 2000
agent-browser find text "Siguiente" click   # Confirm resident status

# Step 1: Datos Declarante (pre-filled from RUT)
agent-browser snapshot -i
agent-browser select @e16 "2 - Masculino"   # Casilla 286: Género
agent-browser select @e18 "0010 - ASALARIADOS"  # Casilla 24: Actividad
agent-browser click @e19                    # "Siguiente"
agent-browser wait 3000
```

### Navigating Wizard Steps
The Form 210 has 15 steps. Navigate between them by clicking the step counters:
```bash
# Jump to step N (0-indexed)
agent-browser eval 'document.querySelectorAll(".step-counter")[N].click()'
agent-browser wait 3000
agent-browser snapshot -i                   # Get field refs for this step
```

### Filling Casillas
```bash
# After snapshot, find the textbox for a casilla and fill it
# Example: Step 2, casilla 297 (e-invoice value)
agent-browser fill @e10 "32602363"          # Casilla 297
agent-browser press Tab                     # Trigger auto-compute of casilla 28

# Example: Step 3, casilla 29 (patrimonio bruto)
agent-browser fill @eNN "254417000"         # Replace @eNN with actual ref

# DIAN auto-computes derived casillas (disabled fields)
# Only fill editable casillas — skip computed ones
```

### Using the Filler Script
```bash
# Generate fill commands from the tax projection
python3 scripts/fill_form210.py --year 2024 --dry-run    # Preview
python3 scripts/fill_form210.py --year 2024 > /tmp/fill.sh  # Script

# The script outputs agent-browser commands with placeholder refs
# Replace <REF_casilla_NNN> with actual @eN refs after each snapshot
```

### Saving, Signing, and Submitting
```bash
# Save draft (floppy icon in top-right)
agent-browser click @e4                     # Save icon (ref varies)
# NOTE: Save may fail if mandatory fields in current section are empty

# After all 14 steps are filled:
# Step 15: Firmar → requires electronic signature (manual)
# Then: Presentar → confirms submission
# Then: Pagar → payment via PSE or receipt
```

### Key Behaviors
- DIAN rounds all values to nearest thousand ($000)
- Some casillas auto-compute when you Tab out of related fields
- The "Siguiente" button validates the current step before advancing
- Clicking step counters directly skips validation (useful for jumping ahead)
- Draft auto-saves when navigating between steps (not guaranteed)
- For corrections: the form pre-fills with values from the Inicial filing

## Security Measures

| Measure | Present? | Impact |
|---------|---------|--------|
| CAPTCHA on login | No | Login is automatable |
| CAPTCHA on public queries | Yes (RUT status) | Blocks unauthenticated scraping |
| Virtual keyboard | Yes (optional) | Not blocking — DOM fill bypasses it |
| 2FA/verification code | On sensitive ops only | Email/SMS code, 15 min validity |
| Session timeout | ~15-30 min inactivity | Re-login needed |
| F5 BigIP load balancer | Yes | Potential connection throttling |

## Legal Considerations

- **Accessing your own account** with automation is defensible under Colombia's
  habeas data rights (Art. 15 Constitution, Ley 1581/2012)
- **Ley 1273/2009 Art. 269A**: Criminalizes "unauthorized" access — your own credentials
  on your own account = authorized
- DIAN ToU don't explicitly prohibit automation
- **Best practice**: reasonable request rates, no CAPTCHA bypassing, own account only
