# Regulatory Access and Navigation

## Table of Contents
- [FDA Expanded Access](#fda-expanded-access)
- [Hospital IRB Navigation](#hospital-irb-navigation)
- [Tissue Access Strategies](#tissue-access-strategies)
- [Data Portability](#data-portability)
- [International Access](#international-access)

---

## FDA Expanded Access

### Individual Patient IND (Form 3926)

The fastest path to experimental drugs outside clinical trials.

**What it is**: An FDA mechanism allowing a single patient to access an investigational drug when:
1. The patient has a serious or life-threatening condition
2. No comparable alternative therapy is available
3. The potential benefit justifies the potential risk
4. Access will not interfere with ongoing clinical trials

**Process**:
1. Identify the experimental drug and its manufacturer/sponsor
2. Physician submits FDA Form 3926 (simplified IND application)
3. FDA reviews and responds — typically within **48 hours** (emergency: 24 hours by phone)
4. Drug manufacturer must also agree to supply the drug
5. Local IRB must approve (this is often the slower step)

**Key insight from reference case**: The FDA was never the bottleneck. Every Form 3926 was approved within 48 hours. Hospital IRBs were the real friction point.

**Form 3926 requirements**:
- Patient diagnosis and treatment history
- Rationale for the specific drug
- Proposed dosing schedule
- Physician's assessment of risk/benefit
- IRB approval (can be concurrent)

**Resources**:
- FDA guidance: https://www.fda.gov/drugs/investigational-new-drug-ind-application/expanded-access
- Reagan-Udall Foundation: https://navigator.reaganudall.org/ (expanded access navigator)

### Emergency IND

For immediately life-threatening situations:
- FDA can authorize by phone within 24 hours
- Written submission (Form 3926) follows within 15 working days
- No prior IRB approval required (must notify IRB within 5 days)

### Right to Try Act (2018)

Alternative to expanded access:
- Patient has exhausted approved options
- Drug has completed Phase I trial
- No FDA application required (direct patient-manufacturer)
- Less regulatory oversight, fewer data collection requirements
- Many manufacturers prefer the Form 3926 route regardless

---

## Hospital IRB Navigation

### The Problem

Hospital IRBs (Institutional Review Boards) operate as independent gatekeepers. Unlike the FDA:
- No standardized timelines
- No standardized criteria for expanded access
- Single members can block access (vetocracy)
- Each hospital has different procedures
- Many IRBs are unfamiliar with expanded access

### Strategies

**1. Choose hospitals with expanded access experience:**
- Major cancer centers (MSKCC, MD Anderson, Dana-Farber) have streamlined processes
- Academic medical centers with active clinical trial programs
- Ask upfront: "What is your IRB's typical turnaround for expanded access?"

**2. Parallel submission:**
- Submit FDA Form 3926 and IRB application simultaneously
- Do not wait for FDA approval before starting IRB process

**3. Use IRB chair direct communication:**
- Request a meeting with the IRB chair to explain the case
- Provide a concise summary: diagnosis, failed treatments, proposed drug, rationale
- Frame as individual patient compassionate use, not research

**4. Escalation path:**
- If IRB blocks: request written reasons
- Consider transferring care to a different institution with faster IRB
- Patient advocacy organizations can sometimes intervene

**5. Central/commercial IRBs:**
- Some expanded access can use commercial IRBs (WCG, Advarra)
- Faster than hospital-specific IRBs
- Confirm with the treating physician and hospital

---

## Tissue Access Strategies

### The FFPE Problem

Standard hospital pathology: biopsy → formalin fixation → paraffin embedding (FFPE). This:
- Preserves tissue morphology for pathology slides
- **Destroys RNA quality** (critical for scRNA-seq and RNA-seq)
- Cross-links proteins (limits proteomics)
- Is the only method most hospital pathology labs support

### What to Request

**Before any biopsy or surgery**, communicate in writing:
1. Request that tissue be split: part FFPE (for clinical pathology), part flash-frozen (for research)
2. Provide cryopreservation instructions and shipping containers
3. Identify the receiving lab (with MTA in place)
4. Confirm with the surgeon AND pathology department (both must agree)

**Cryopreservation protocol (basic)**:
- Tissue placed in cryovial within 30 minutes of excision
- Snap-freeze in liquid nitrogen or isopentane on dry ice
- Store at -80C or liquid nitrogen
- Ship on dry ice with temperature monitoring

### Material Transfer Agreement (MTA)

Required for sending patient tissue between institutions:
- Initiate MTA process weeks before the planned procedure
- Required parties: sending hospital, receiving lab, patient consent
- Many hospitals have standard MTA templates
- Allow 2-4 weeks for processing

### Patient Data Access

Tissue samples are the patient's property. Key rights:
- HIPAA Right of Access: patients can request copies of medical records including pathology
- 21st Century Cures Act: prohibits information blocking
- Direct-to-patient sequencing: services like Tempus, Foundation Medicine can work directly with patients

---

## Data Portability

### Getting Raw Sequencing Data

Clinical sequencing companies (Tempus, Foundation Medicine, etc.) typically provide:
- **Summary report**: Mutations, treatment recommendations (this is default)
- **Raw data (FASTQ/BAM)**: Must be specifically requested

**How to request raw data**:
1. Contact the sequencing company's patient data access team
2. Submit a formal data release request (usually requires patient signature)
3. Specify format: FASTQ (preferred for reanalysis) or BAM
4. Specify delivery: cloud transfer (preferred for large files) or physical media
5. Typical turnaround: 2-4 weeks

### Building a Personal Health Record

Aggregate all data in one place:
- Sequencing reports and raw data
- Imaging (DICOM files from radiology)
- Pathology reports and images
- Lab results (CBC, metabolic panels, tumor markers)
- Treatment records
- Clinical notes

**Tools**: Apple Health Records (for basic labs), patient portal exports, manual aggregation

---

## International Access

### Radioligand Therapy

FAP-targeted radioligand therapy (177Lu-FAPi, 225Ac-FAPi) is more accessible in:
- **Germany**: Multiple centers (University Hospital Heidelberg, LMU Munich)
- **Australia**: Theranostics Australia
- **India**: Several nuclear medicine centers

**Process**:
1. Obtain diagnostic PET scan (68Ga-FAP) to confirm target expression
2. Contact international center with PET images and medical records
3. Arrange travel and accommodation
4. Typical course: 1-3 treatments, 4-8 weeks apart
5. Follow-up imaging and monitoring can be done locally

### Neoantigen Vaccines

- **Germany**: CeGaT (peptide vaccines)
- **US**: Multiple academic centers (MSKCC, Dana-Farber, MD Anderson)
- **Self-manufacture**: OpenVaxx guide (research/educational, not clinical)

### Clinical Trial Search

- ClinicalTrials.gov: https://clinicaltrials.gov/
- WHO ICTRP: https://trialsearch.who.int/
- EU Clinical Trials Register: https://www.clinicaltrialsregister.eu/
- Filter by: cancer type + "expanded access" or "compassionate use"
