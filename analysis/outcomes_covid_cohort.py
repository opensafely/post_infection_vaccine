"""
Outcome registry for the COVID-exposure cohort study
=====================================================
Each entry in OUTCOMES defines one outcome analysis.
The generate_variables() function in variables_covid_cohort.py iterates
over this list and produces the following variables for every outcome:

    tmp_out_date_{name}_gp      First matching GP (SNOMED) event after index date
    tmp_out_date_{name}_apc     First matching APC (ICD-10) admission after index date
    tmp_out_date_{name}_death   Death with outcome as underlying/contributory cause
    out_date_{name}             Earliest of the three sources above
    excl_bin_prior_{name}       Had the outcome in the {prior_days} days before index date

To add a new outcome, add one dictionary to OUTCOMES with the keys below.
To disable an outcome without deleting it, comment out its entry.

Required keys
-------------
name        str       Variable name suffix, e.g. "stroke_all"
snomed      codelist  SNOMED-CT codelist for primary care (clinical_events)
icd10       codelist  ICD-10 codelist for secondary care (apcs) and deaths

Optional keys
-------------
prior_days  int       Lookback window in days for the exclusion criterion (default 365)
"""

from codelists import (
    # Stroke
    stroke_snomed,
    stroke_icd10,
    stroke_isch_snomed,
    stroke_isch_icd10,
    stroke_sahhs_snomed,
    stroke_sahhs_icd10,
    # Acute myocardial infarction
    ami_snomed,
    ami_icd10,
    # Heart failure
    hf_snomed,
    hf_icd10,
    # Venous thromboembolism
    vte_snomed,
    vte_icd10,
    # Angina
    angina_snomed,
    angina_icd10,
    # Other arterial embolism
    other_ae_snomed,
    other_ae_icd10,
)

OUTCOMES = [

    # ── Active outcomes ────────────────────────────────────────────────────────

    {
        "name":       "stroke_all",
        "snomed":     stroke_snomed,
        "icd10":      stroke_icd10,
        "prior_days": 365,
    },
    {
        "name":       "stroke_isch",
        "snomed":     stroke_isch_snomed,
        "icd10":      stroke_isch_icd10,
        "prior_days": 365,
    },

    # ── Commented-out outcomes: uncomment to activate ──────────────────────────

    # {
    #     "name":       "stroke_sahhs",
    #     "snomed":     stroke_sahhs_snomed,
    #     "icd10":      stroke_sahhs_icd10,
    #     "prior_days": 365,
    # },
    # {
    #     "name":       "ami",
    #     "snomed":     ami_snomed,
    #     "icd10":      ami_icd10,
    #     "prior_days": 365,
    # },
    # {
    #     "name":       "hf",
    #     "snomed":     hf_snomed,
    #     "icd10":      hf_icd10,
    #     "prior_days": 365,
    # },
    # {
    #     "name":       "vte",
    #     "snomed":     vte_snomed,
    #     "icd10":      vte_icd10,
    #     "prior_days": 365,
    # },
    # {
    #     "name":       "angina",
    #     "snomed":     angina_snomed,
    #     "icd10":      angina_icd10,
    #     "prior_days": 365,
    # },
    # {
    #     "name":       "other_ae",
    #     "snomed":     other_ae_snomed,
    #     "icd10":      other_ae_icd10,
    #     "prior_days": 365,
    # },

]
