# Environmental DNA (eDNA) Metabarcoding for Marine Biodiversity

## What Is eDNA?

Environmental DNA is genetic material shed by organisms into their surroundings — through skin cells, mucus, feces, gametes, decomposition, and secretions. Every living organism continuously releases DNA into its environment.

In marine contexts, a liter of seawater contains DNA fragments from hundreds of species — fish, invertebrates, microbes, plankton — without any organism needing to be captured or observed.

## The eDNA Revolution in Ocean Science

### Traditional vs. eDNA Survey Methods

| Method | Effort | Cost | Coverage | Invasiveness | Deep-sea Viability |
|--------|--------|------|----------|-------------|-------------------|
| **Trawl surveys** | Months at sea | Very high | Limited area | Destructive | Difficult below 2000m |
| **Visual transects (ROV)** | Days per site | High | Limited visibility | Non-destructive | Good, but slow |
| **Acoustic surveys** | Days | Medium | Large area, fish only | Non-invasive | Good |
| **eDNA sampling** | Hours per site | Low-medium | All taxa in water column | Non-invasive | Excellent to full depth |

### Key Advantages

1. **Non-invasive**: No organisms captured, killed, or disturbed
2. **Comprehensive**: Detects all taxa shedding DNA — from microbes to whales
3. **Depth-independent**: Water samples can be collected at any depth via Niskin bottles or CTD rosettes
4. **Temporal resolution**: Captures diel (day-night) community patterns from a single sampling event
5. **Cost-effective**: One water sample replaces hours of visual survey
6. **Rare species detection**: Can detect species too rare or cryptic for visual surveys

## The eDNA Metabarcoding Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1: FIELD SAMPLING                                         │
│                                                                  │
│  Collect seawater (1-5 L per sample)                            │
│  ├── Surface: Niskin bottles from vessel                         │
│  ├── Midwater: CTD rosette at target depth                       │
│  ├── Deep-sea: ROV-mounted samplers (to 6000m+)                 │
│  └── Automated: Large-volume eDNA samplers (filter in situ)     │
│                                                                  │
│  Controls: field blanks (opened/closed), cooler blanks           │
│  Storage: ice or -20°C within 24h, or preserve in ethanol        │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 2: FILTRATION                                              │
│                                                                  │
│  Filter water through 0.2-0.45 μm membrane                      │
│  ├── Captures DNA fragments adsorbed to particles                │
│  ├── Typical: Sterivex or polycarbonate membrane                 │
│  └── Storage: -80°C or in preservation buffer (ATL, Longmire)   │
│                                                                  │
│  Critical: Avoid cross-contamination (dedicated equipment)       │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 3: DNA EXTRACTION                                          │
│                                                                  │
│  Break filter membrane → lyse cells → isolate DNA                │
│  ├── Kits: DNeasy Blood & Tissue, PowerWater, MoBio PowerSoil   │
│  ├── Yield: typically 1-100 ng DNA per liter of seawater         │
│  └── QC: NanoDrop (260/280 ratio), Qubit fluorometry             │
│                                                                  │
│  Extraction blanks mandatory for contamination detection          │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 4: PCR AMPLIFICATION                                       │
│                                                                  │
│  Amplify target marker gene using universal primers:              │
│                                                                  │
│  ┌─────────┬──────────────────┬────────────────────────────┐    │
│  │ Marker  │ Target taxa      │ Primer set                  │    │
│  ├─────────┼──────────────────┼────────────────────────────┤    │
│  │ CO1     │ Metazoa (animals)│ mlCOIintF / jgHCO2198      │    │
│  │ 12S     │ Vertebrates      │ MiFish-U-F / MiFish-U-R    │    │
│  │ 16S     │ Bacteria/Archaea │ 515F / 806R                │    │
│  │ 18S     │ Eukaryotes       │ Uni18SF / Uni18SR          │    │
│  │ ITS     │ Fungi            │ ITS1-F / ITS2              │    │
│  └─────────┴──────────────────┴────────────────────────────┘    │
│                                                                  │
│  Indexed PCR: unique barcode per sample for multiplexing         │
│  Technical replicates: 3+ per sample (detect stochasticity)      │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 5: SEQUENCING                                              │
│                                                                  │
│  Illumina MiSeq/NovaSeq (most common for metabarcoding):        │
│  ├── Paired-end 2×250 bp or 2×300 bp                            │
│  ├── ~10-25 million reads per run                                │
│  └── Demultiplex by index barcode                                │
│                                                                  │
│  Oxford Nanopore MinION (emerging, field-deployable):            │
│  ├── Full-length amplicons in single read                        │
│  ├── Real-time species detection at sea                          │
│  └── Basecalling via Dorado (runs on Apple Silicon)              │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 6: BIOINFORMATICS                                          │
│                                                                  │
│  QIIME2 pipeline (standard):                                     │
│  1. Import FASTQ → QIIME2 artifacts                              │
│  2. Quality filter (DADA2 or Deblur)                             │
│     → Denoise → Amplicon Sequence Variants (ASVs)                │
│  3. Chimera detection and removal (UCHIME)                       │
│  4. Taxonomy assignment:                                         │
│     ├── Naive Bayes classifier (sklearn in QIIME2)               │
│     ├── BLAST against reference DB                               │
│     └── Sequence similarity threshold: 97% (OTU) or exact (ASV) │
│  5. Reference databases:                                         │
│     ├── BOLD (Barcode of Life) — CO1 barcodes                    │
│     ├── GenBank/NCBI nt — comprehensive                          │
│     ├── SILVA — 16S/18S rRNA                                     │
│     └── UNITE — ITS (fungi)                                      │
│  6. Diversity analysis:                                          │
│     ├── Alpha diversity (Shannon, Simpson, Chao1)                │
│     ├── Beta diversity (Bray-Curtis, UniFrac)                    │
│     └── Ordination (PCoA, NMDS)                                  │
│                                                                  │
│  Alternative: Kraken2 (k-mer based, faster but less standard)    │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 7: SPECIES INVENTORY + ECOLOGICAL ANALYSIS                 │
│                                                                  │
│  Output: taxa count table (species × samples matrix)             │
│  ├── Species presence/absence per sample location                │
│  ├── Relative abundance estimates (with PCR bias caveats)        │
│  ├── Community composition across depths, sites, seasons         │
│  ├── Detection of rare/cryptic species                           │
│  └── Upload to OBIS (Ocean Biodiversity Information System)      │
│                                                                  │
│  Novel species: CO1 divergence >3% from nearest reference        │
│  → triggers formal taxonomic description workflow                │
└─────────────────────────────────────────────────────────────────┘
```

## Deep-Sea eDNA: Unique Challenges

### Physical Challenges
- **Extreme pressure**: 100-600 atm at abyssal depths — sample containers must withstand pressure changes
- **Temperature gradients**: 1-4°C ambient vs. 350°C+ near hydrothermal vents
- **DNA degradation**: Cold, dark, high-pressure environments slow degradation but UV at surface accelerates it
- **Transport distance**: eDNA can persist days-weeks in cold deep water — spatial resolution is lower

### Biological Challenges
- **Reference database gaps**: >80% of deep-sea species lack CO1 barcodes in BOLD/GenBank
- **Novel phyla**: Some deep-sea lineages have no close relatives in databases
- **PCR primer bias**: Universal primers may miss divergent taxa
- **Biomass distribution**: Abyssal plains have extremely low biomass — need large-volume sampling

### Emerging Solutions
- **Shotgun metagenomics**: Skip PCR entirely — sequence everything, classify computationally
- **Long-read metabarcoding**: Nanopore full-length CO1 improves species discrimination
- **In-situ sampling**: Autonomous underwater vehicles (AUVs) with integrated DNA samplers
- **Real-time sequencing at sea**: MinION on research vessels for immediate species detection

## Key Marine eDNA Programs

### Ocean Census (2023-present)
- **Mission**: Discover 100,000 new marine species by 2030
- **Partners**: Nippon Foundation + Nekton Foundation
- **Results (2025)**: 866 new species (depths 1m-4,990m)
- **Technology**: DNA sequencing + high-resolution imaging + machine learning
- **Data**: Open-access Biodiversity Data Platform
- **URL**: oceancensus.org

### NOAA eDNA Program
- **Scope**: U.S. national marine eDNA monitoring
- **Focus**: Fisheries management, invasive species, endangered species detection
- **Integration**: NOAA Ocean Exploration program with deep-sea focus

### BOEM (Bureau of Ocean Energy Management)
- **Purpose**: eDNA for environmental impact assessment near offshore energy sites
- **Partnership**: Smithsonian NMNH genetic reference library from museum collections
- **Innovation**: Building comprehensive marine invertebrate barcode library

### Tara Oceans (2009-2013, ongoing analysis)
- **Scale**: 35,000 water samples, 210 ocean stations, 1.3 TB sequence data
- **Output**: 97 million non-redundant genes, 150,000+ genomes
- **Impact**: Discovered thousands of new plankton species, mapped ocean microbiome

## Quantitative Considerations

### Detection Limits
- **Fish eDNA**: Detectable at ~1-100 copies/L, degrades within 1-14 days
- **Invertebrate eDNA**: More persistent, detectable at lower concentrations
- **Microbial DNA**: Ubiquitous, >10^6 cells/mL in surface seawater
- **Detection probability**: Increases with sample volume, replicates, and primer sensitivity

### Abundance Estimation Caveats
- PCR amplification introduces bias (different species amplify at different rates)
- eDNA concentration ≠ biomass (varies by shedding rate, degradation rate, water mixing)
- Presence/absence is reliable; relative abundance requires calibration
- Quantitative PCR (qPCR) with species-specific primers for abundance of known species

## Sources

- Thomsen PF, Willerslev E. "Environmental DNA — An emerging tool in conservation for monitoring past and present biodiversity." Biological Conservation 183:4-18, 2015.
- Deiner K, et al. "Environmental DNA metabarcoding: Transforming how we survey animal and plant communities." Molecular Ecology 26:5872-5895, 2017.
- Ocean Census. "How the Census Works." oceancensus.org, 2025.
- Andruszkiewicz EA, et al. "Biomonitoring of marine vertebrates in Monterey Bay using eDNA metabarcoding." PLoS ONE 12:e0176343, 2017.
- Sunagawa S, et al. "Structure and function of the global ocean microbiome." Science 348:1261359, 2015.
- OBIS (Ocean Biodiversity Information System). "eDNA Data Services." obis.org, 2024.
