# Estatuto Tributario — Reference for Form 210 Calculations

Legal basis for every calculation in the finance-substrate tax engine.
Año gravable 2024. UVT = $47,065 COP (Resolución DIAN 000187 de 2023, Art. 868 ET).

## R33 — Ingresos No Constitutivos de Renta (INCR)

| Component | ET Article | Rule | Rate |
|-----------|-----------|------|------|
| Pension obligatoria | Art. 55 | All mandatory pension contributions are INCR | 16% of IBC |
| Salud obligatoria | Art. 56 (Ley 1819/2016 Art. 14) | All mandatory health contributions are INCR | 12.5% of IBC |
| FSP (Solidaridad + Subsistencia) | Ley 100/1993 Art. 25 | Mandatory FSP contributions are INCR | 1% of IBC (if IBC ≥ 4 SMLMV) |
| ARL | Art. 107 ET | **NOT INCR** — deductible as cost/expense | 0.522% (Nivel I) |
| Voluntary pension aportes | Art. 126-1 | Contributions to voluntary funds are **renta exenta** (not INCR) | Up to 30% income / 3,800 UVT |

### IBC for Independents
- **IBC = 40% of gross monthly income** (excluding IVA)
- Legal basis: Decreto 1273 de 2018 (operational), originally Art. 135 Ley 1753/2015
- Floor: 1 SMLMV ($1,300,000). Ceiling: 25 SMLMV ($32,500,000)

### CRITICAL: ARL is NOT INCR
ARL contributions are deductible as a business expense (Art. 107 ET), not as INCR under Arts. 55-56.

## R35 — AFC + Voluntary Pension (Rentas Exentas)

| Component | ET Article | Limit |
|-----------|-----------|-------|
| AFC (Ahorro Fomento Construcción) | Art. 126-4 | Combined with voluntary pension |
| Voluntary pension contributions | Art. 126-1 (Ley 2010/2019 Art. 31) | Combined with AFC |
| **Combined cap** | Art. 126-1 + 126-4 | **30% of annual income OR 3,800 UVT ($178,847,000)**, whichever is LOWER |

### Permanence requirement (Art. 126-1, 126-4)
- Funds must remain for **minimum 10 years**, OR be used for housing, OR withdrawn at pension age/death/disability
- Non-compliant withdrawal: retroactive taxation + retención

## R36 — 25% Renta Exenta

| Rule | ET Article | Limit |
|------|-----------|-------|
| 25% of labor income is exempt | Art. 206 Numeral 10 (modified by **Ley 2277/2022 Art. 2**) | **790 UVT annually ($37,181,350)** |

### Post-reform change (Ley 2277/2022)
- **Before**: 240 UVT/month = 2,880 UVT/year
- **After (AG 2023+)**: 790 UVT/year (flat annual cap)

### For independents (Art. 206 Parágrafo 5)
- Can claim 25% if income qualifies as rentas de trabajo (honorarios)
- **Cannot claim both** 25% exemption AND actual cost deductions

## R41 — Global Limitation

| Rule | ET Article | Limit |
|------|-----------|-------|
| Total exentas + deducciones cap | **Art. 336 Numeral 3 (Ley 2277/2022 Art. 7)** | **40% of renta líquida OR 1,340 UVT ($63,067,100)**, whichever is LOWER |

### CRITICAL: Ley 2277/2022 Change
- **Before reform**: 5,040 UVT ($237,207,600)
- **After reform (AG 2023+)**: **1,340 UVT ($63,067,100)**
- This is the single most impactful change for high-income earners

### Dependientes (Art. 336 Parágrafo, Ley 2277)
- **72 UVT per dependent** ($3,388,680) × max 4 dependents = 288 UVT ($13,554,720)
- This is **ADDITIONAL** to the 1,340 UVT cap — not subject to it

## R39 — Deducciones Imputables

| Deduction | ET Article | Limit |
|-----------|-----------|-------|
| Medicina prepagada | Art. 387 | 16 UVT/month ($752,960) = 192 UVT/year ($9,036,480) |
| GMF (4x1000) | Art. 115 | 50% of GMF paid is deductible. No causal requirement |
| E-invoice 1% | Art. 336 Numeral 5 (Ley 2277/2022) | 1% of purchases with factura electrónica, cap 240 UVT ($11,295,600) |
| Intereses vivienda | Art. 119 | Up to 1,200 UVT/year |
| Dependientes | Art. 387 | 10% of gross income, cap 32 UVT/month |

### E-invoice 1% conditions (Art. 336 Num. 5)
- Purchase must NOT be claimed as cost, deduction, or other benefit
- Factura must be validated by DIAN
- Payment via debit/credit card or electronic means
- IVA is included in the 1% base (Concepto DIAN 379/2024)

## R58 — Rentas de Capital

| Component | ET Article | Treatment |
|-----------|-----------|-----------|
| Rendimientos financieros | Arts. 38, 40-1, 41 | 50.88% is INCR (componente inflacionario AG 2024, Decreto 771/2025) |
| Voluntary pension retiros (compliant) | Art. 126-1 | Renta exenta (10+ years, housing, pension age) |
| Voluntary pension retiros (non-compliant) | Art. 126-1 | Taxable + 7% retención (contributions post Jan 2017) |
| RAIS voluntary retiros (non-compliant) | Art. 55 inciso 3 | Taxable + 35% retención |

### Componente inflacionario AG 2024
- **50.88%** of rendimientos is INCR (Decreto 771 de 2025)
- Only 49.12% is taxable
- Applies to personas naturales not obligated to keep accounting books

## R121 — Tax Brackets (Art. 241 ET)

| Range (UVT) | Rate | Base tax (UVT) |
|-------------|------|---------------|
| 0 – 1,090 | 0% | 0 |
| 1,090 – 1,700 | 19% | 0 |
| 1,700 – 4,100 | 28% | 115.9 |
| 4,100 – 8,670 | 33% | 787.9 |
| 8,670 – 18,970 | 35% | 2,296 |
| 18,970 – 31,000 | 37% | 5,901 |
| > 31,000 | 39% | 10,352 |

## R130/R133 — Anticipo de Renta (Arts. 807-811 ET)

| Declaration year | Rate |
|------------------|------|
| 1st year | 25% |
| 2nd year | 50% |
| 3rd+ year | 75% |

**Formula**: Anticipo = (Impuesto neto × Rate) − Retenciones del año
If negative, anticipo = 0.

Two methods (taxpayer chooses):
- **Method A**: Apply rate to current year's net tax
- **Method B**: Apply rate to average of two preceding years' net tax

## R132 — Retenciones

| Source | Rate | ET Article |
|--------|------|-----------|
| Rendimientos CDT | 4% | Art. 395 |
| Rendimientos cuentas ahorro | 7% (above 0.055 UVT/day threshold) | Art. 395 |
| Voluntary pension non-compliant withdrawal | 7% | Art. 126-1 |
| RAIS voluntary non-compliant withdrawal | 35% | Art. 55 |

## Sources

- [Estatuto Tributario](https://estatuto.co/)
- [Ley 2277 de 2022 — Reforma tributaria](https://normograma.dian.gov.co/dian/compilacion/docs/ley_2277_2022.htm)
- [Decreto 771/2025 — Componente inflacionario AG 2024](https://normograma.dian.gov.co/dian/compilacion/docs/decreto_0771_2025.htm)
- [Decreto 1273/2018 — IBC independientes](https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=87624)
- [DIAN UVT 2024 — Resolución 000187/2023](https://incp.org.co/la-uvt-para-2024-sera-de-47-065/)
