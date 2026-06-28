# Marine Genomics Databases

Catalog of databases, data portals, and reference collections relevant to ocean genomics and deep-sea biodiversity research.

## Biodiversity & Occurrence Databases

### OBIS — Ocean Biodiversity Information System

| Property | Value |
|----------|-------|
| **URL** | obis.org |
| **Scope** | Global marine species occurrence data |
| **Records** | 100M+ occurrence records, 160,000+ species |
| **eDNA** | 19.8M eDNA-derived records (as of 2024) |
| **API** | REST API: `api.obis.org` |
| **Data standard** | Darwin Core |

```bash
# API query example
curl "https://api.obis.org/v3/occurrence?scientificname=Bathynomus%20giganteus&size=10"
```

**Key features:**
- Standardized occurrence data from 4,000+ datasets
- Quality-controlled with automated flags
- eDNA data integration via UNESCO/IOC partnership
- Feeds into CBD (Convention on Biological Diversity) assessments

### BOLD — Barcode of Life Data System

| Property | Value |
|----------|-------|
| **URL** | boldsystems.org |
| **Scope** | DNA barcode reference library |
| **Records** | 17M+ barcode records, 400K+ species |
| **Primary marker** | CO1 (cytochrome c oxidase subunit 1) |
| **API** | REST API: `v4.boldsystems.org/api` |

```bash
# Identify species from CO1 sequence
curl -X POST "https://v4.boldsystems.org/api/v2/identify" \
  -d '{"sequences": [{"id": "sample1", "sequence": "ATCGATCG..."}]}'
```

**Key features:**
- Gold standard for metabarcoding species identification
- Curated taxonomy with voucher specimen links
- Species-level identification via CO1 barcode gap
- BIN (Barcode Index Number) system for provisional species assignment

### Ocean Census Biodiversity Data Platform

| Property | Value |
|----------|-------|
| **URL** | oceancensus.org |
| **Scope** | New species discovery tracking |
| **Results** | 866 new species (2023-2025), depths 1m-4,990m |
| **Partners** | 800+ scientists, 400+ institutions |
| **Method** | DNA sequencing + high-res imaging + ML |

---

## Genomics & Multi-Omics Databases

### DOO — Deep Ocean Organisms Multi-Omics Platform

| Property | Value |
|----------|-------|
| **URL** | deepoceanomics.org |
| **Developer** | HKUST (Hong Kong University of Science and Technology) |
| **Publication** | Nucleic Acids Research 54(D1):D1031, 2024 |
| **Scope** | Deep-sea multi-omics atlas |

**Data holdings:**
| Data Type | Count |
|-----------|-------|
| Species | 68 (7 phyla) |
| Genomes | 72 |
| Transcriptomes | 950 |
| Metagenomes | 1,112 |
| Single-cell datasets | 15 |
| Fossil records | 1,413 |

**Habitats covered:** Cold seeps, hydrothermal vents, seamounts

**Analytical modules:**
1. **Gene & Genome Module** — structural/functional annotation, ortholog groups
2. **Functional Genomics Module** — co-expression networks, single-cell visualization
3. **Evolutionary & Comparative Module** — pan-gene sets, phylogenetic trees, fossil correlation

### Tara Oceans

| Property | Value |
|----------|-------|
| **URL** | fondationtaraocean.org |
| **Scope** | Global ocean microbiome |
| **Data** | 1.3 TB reads, 97M non-redundant genes, 150,000+ genomes |
| **Stations** | 210 sampling stations worldwide |
| **Depth** | Surface to mesopelagic (1000m) |
| **Access** | European Nucleotide Archive (ENA) |

**Key outputs:**
- Ocean Microbiome Reference Gene Catalog (OM-RGC v2)
- Ocean Gene Atlas: ocean-gene-atlas.org
- Plankton species atlas with environmental correlations

### NCBI GenBank

| Property | Value |
|----------|-------|
| **URL** | ncbi.nlm.nih.gov/genbank |
| **Scope** | All publicly available nucleotide sequences |
| **Records** | 2.5 billion+ sequences |
| **API** | E-utilities REST API |

```python
# Programmatic access via Biopython
from Bio import Entrez
Entrez.email = "user@example.com"

# Search for deep-sea organism sequences
handle = Entrez.esearch(db="nucleotide",
    term="deep-sea[Title] AND CO1[Gene]",
    retmax=100)

# Fetch sequences
handle = Entrez.efetch(db="nucleotide", id="NM_001301717", rettype="fasta")
```

### European Nucleotide Archive (ENA)

| Property | Value |
|----------|-------|
| **URL** | ebi.ac.uk/ena |
| **Scope** | European mirror/complement to GenBank |
| **API** | REST API: `www.ebi.ac.uk/ena/portal/api` |
| **Advantage** | Better metadata for European marine samples, Tara Oceans data home |

---

## Protein & Structure Databases

### AlphaFold Protein Structure Database

| Property | Value |
|----------|-------|
| **URL** | alphafold.ebi.ac.uk |
| **Scope** | Pre-computed AlphaFold2 protein structures |
| **Records** | 200M+ structures (aligned with UniProt 2025_03) |
| **Access** | Web browser, bulk download, API |

```bash
# Download structure by UniProt ID
curl -O https://alphafold.ebi.ac.uk/files/AF-P00520-F1-model_v4.pdb
```

### ESM Metagenomic Atlas

| Property | Value |
|----------|-------|
| **URL** | esmatlas.com |
| **Developer** | Meta FAIR |
| **Scope** | Protein structures predicted from metagenomic sequences |
| **Records** | 617M+ structures |
| **Significance** | 3x larger than all prior structural databases combined |
| **Source** | Environmental metagenomes (ocean, soil, gut, etc.) |

### UniProt

| Property | Value |
|----------|-------|
| **URL** | uniprot.org |
| **Scope** | Curated protein sequence + function database |
| **Records** | 250M+ sequences (TrEMBL) + 570K reviewed (Swiss-Prot) |
| **API** | REST API with rich query language |

```bash
# Search for deep-sea proteins
curl "https://rest.uniprot.org/uniprotkb/search?query=deep-sea+AND+taxonomy_id:2759&format=json&size=25"
```

### PDB — Protein Data Bank

| Property | Value |
|----------|-------|
| **URL** | rcsb.org |
| **Scope** | Experimentally determined 3D structures |
| **Records** | 220,000+ structures |
| **Methods** | X-ray crystallography, cryo-EM, NMR |

### STRING — Protein Interaction Networks

| Property | Value |
|----------|-------|
| **URL** | string-db.org |
| **Scope** | Known and predicted protein-protein interactions |
| **Coverage** | 14,000+ organisms, 67M+ proteins |

---

## Taxonomy & Classification

### SILVA

| Property | Value |
|----------|-------|
| **URL** | silva.de |
| **Scope** | Ribosomal RNA gene database (16S/18S/23S/28S) |
| **Use** | Reference for bacterial/archaeal/eukaryotic taxonomy |
| **QIIME2** | Pre-trained classifiers available |

### UNITE

| Property | Value |
|----------|-------|
| **URL** | unite.ut.ee |
| **Scope** | ITS reference database for fungi |

### WoRMS — World Register of Marine Species

| Property | Value |
|----------|-------|
| **URL** | marinespecies.org |
| **Scope** | Authoritative taxonomic classification for marine species |
| **Records** | 240,000+ accepted species names |
| **API** | REST API: `marinespecies.org/rest` |

---

## Environmental & Climate Data

### Copernicus Marine Service (CMEMS)

| Property | Value |
|----------|-------|
| **URL** | marine.copernicus.eu |
| **Scope** | Ocean observation data (temperature, salinity, currents, biogeochemistry) |
| **API** | Python: `copernicusmarine` package |

### NOAA National Centers for Environmental Information

| Property | Value |
|----------|-------|
| **URL** | ncei.noaa.gov |
| **Scope** | Bathymetry, ocean temperature, hydrothermal vent locations |

### GEBCO — General Bathymetric Chart of the Oceans

| Property | Value |
|----------|-------|
| **URL** | gebco.net |
| **Scope** | Global ocean floor topography |
| **Resolution** | 15 arc-second grid (~450m) |

---

## Data Access Patterns

### For eDNA Species Identification
```
Sequencing → FASTQ → QIIME2 → BLAST against:
  1. BOLD (CO1 barcodes) — first choice for animals
  2. GenBank nt (comprehensive) — fallback
  3. SILVA (16S/18S rRNA) — for microbes/eukaryotes
  4. UNITE (ITS) — for fungi
```

### For Novel Gene Characterization
```
Metagenomic assembly → Gene prediction → Search against:
  1. UniProt (protein function)
  2. AlphaFold DB (pre-computed structures)
  3. ESM Atlas (metagenomic structures)
  4. PDB (experimental structures)
  5. STRING (interaction networks)
```

### For Ecological Context
```
Species list → Cross-reference against:
  1. OBIS (global occurrence, distribution)
  2. WoRMS (authoritative taxonomy)
  3. IUCN Red List (conservation status)
  4. CMEMS (environmental conditions at sampling site)
  5. GEBCO (bathymetry of sampling location)
```
