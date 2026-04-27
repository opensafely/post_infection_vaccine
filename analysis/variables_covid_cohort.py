from ehrql import (
    days,
    case,
    when,
    minimum_of,
)

# Bring table definitions from the TPP backend
from ehrql.tables.tpp import (
    patients,
    practice_registrations,
    addresses,
    occupation_on_covid_vaccine_record,
    sgss_covid_all_tests,
    ethnicity_from_sus,
    apcs,
    clinical_events,
    ons_deaths,
)

# Codelists from codelists.py
from codelists import *

# Helper functions from variable_helper_functions.py
from variable_helper_functions import (
    ever_matching_event_clinical_ctv3_before,
    last_matching_event_clinical_ctv3_before,
    last_matching_event_clinical_snomed_before,
    last_matching_med_dmd_before,
    last_matching_event_apc_before,
    matching_death_before,
    filter_codes_by_category,
    get_latest_ethnicity,
)

# Outcome registry — edit outcomes_covid_cohort.py to add / remove outcomes
from outcomes_covid_cohort import OUTCOMES


# ── Outcome factory function ───────────────────────────────────────────────────

def build_outcome_variables(outcome, exp_date_covid, study_end_out):
    """
    Generate all ehrQL variables for a single outcome.

    For each outcome in OUTCOMES this produces five variables:
        tmp_out_date_{name}_gp      First GP event (SNOMED) after the index date
        tmp_out_date_{name}_apc     First APC admission (ICD-10) after the index date
        tmp_out_date_{name}_death   Death with outcome as the cause
        out_date_{name}             Earliest of the three sources
        excl_bin_prior_{name}       Had the outcome in the prior-days window before index

    Parameters
    ----------
    outcome        : dict from OUTCOMES (keys: name, snomed, icd10, prior_days)
    exp_date_covid : ehrQL Series[date] — patient-specific index date
    study_end_out  : date               — administrative end of follow-up
    """
    name       = outcome["name"]
    snomed     = outcome["snomed"]
    icd10      = outcome["icd10"]
    prior_days = outcome.get("prior_days", 365)

    # First matching GP (SNOMED) event strictly after the index date
    tmp_gp = (
        clinical_events
        .where(clinical_events.snomedct_code.is_in(snomed))
        .where(clinical_events.date.is_after(exp_date_covid))
        .where(clinical_events.date.is_on_or_before(study_end_out))
        .sort_by(clinical_events.date)
        .first_for_patient()
        .date
    )

    # First matching APC (ICD-10) admission strictly after the index date
    tmp_apc = (
        apcs
        .where(apcs.all_diagnoses.contains_any_of(icd10))
        .where(apcs.admission_date.is_after(exp_date_covid))
        .where(apcs.admission_date.is_on_or_before(study_end_out))
        .sort_by(apcs.admission_date)
        .first_for_patient()
        .admission_date
    )

    # Death with this outcome as underlying or contributory cause
    tmp_death = case(
        when(
            ons_deaths.cause_of_death_is_in(icd10) &
            ons_deaths.date.is_after(exp_date_covid) &
            ons_deaths.date.is_on_or_before(study_end_out)
        ).then(ons_deaths.date)
    )

    # Earliest event date across all sources
    out_date = minimum_of(tmp_gp, tmp_apc, tmp_death)

    # Exclusion flag: had the outcome in the prior_days window before the index date.
    # The upper bound is strictly before exp_date_covid so that a same-day record
    # is not treated as a pre-existing event.
    excl = (
        (
            clinical_events
            .where(clinical_events.snomedct_code.is_in(snomed))
            .where(clinical_events.date.is_on_or_after(exp_date_covid - days(prior_days)))
            .where(clinical_events.date.is_before(exp_date_covid))
            .exists_for_patient()
        ) | (
            apcs
            .where(apcs.all_diagnoses.contains_any_of(icd10))
            .where(apcs.admission_date.is_on_or_after(exp_date_covid - days(prior_days)))
            .where(apcs.admission_date.is_before(exp_date_covid))
            .exists_for_patient()
        ) | (
            ons_deaths.cause_of_death_is_in(icd10) &
            ons_deaths.date.is_on_or_after(exp_date_covid - days(prior_days)) &
            ons_deaths.date.is_before(exp_date_covid)
        )
    )

    return {
        f"tmp_out_date_{name}_gp":    tmp_gp,
        f"tmp_out_date_{name}_apc":   tmp_apc,
        f"tmp_out_date_{name}_death": tmp_death,
        f"out_date_{name}":           out_date,
        f"excl_bin_prior_{name}":     excl,
    }


# ── Main variables function ────────────────────────────────────────────────────

def generate_variables(study_start, study_end_exp, study_end_out):

    ## Exposure: index date (first EVER positive COVID-19 test) -------------------
    # Each query finds the patient's first EVER positive COVID record from that
    # source with NO date restriction.  The study-window eligibility check is
    # applied separately as an inclusion criterion (inex_bin_first_covid_in_window)
    # so that a patient whose very first infection pre-dates the study window is
    # correctly excluded rather than re-indexed on a later re-infection.

    tmp_exp_date_covid_sgss = (
        sgss_covid_all_tests
        .where(sgss_covid_all_tests.is_positive)
        .sort_by(sgss_covid_all_tests.specimen_taken_date)
        .first_for_patient()
        .specimen_taken_date
    )

    tmp_exp_date_covid_gp = (
        clinical_events
        .where(
            clinical_events.ctv3_code.is_in(
                covid_primary_care_code +
                covid_primary_care_positive_test +
                covid_primary_care_sequalae
            )
        )
        .sort_by(clinical_events.date)
        .first_for_patient()
        .date
    )

    tmp_exp_date_covid_apc = (
        apcs
        .where(
            (apcs.primary_diagnosis.is_in(covid_codes)) |
            (apcs.secondary_diagnosis.is_in(covid_codes))
        )
        .sort_by(apcs.admission_date)
        .first_for_patient()
        .admission_date
    )

    # Index date: earliest first-ever positive date across all three sources
    exp_date_covid = minimum_of(
        tmp_exp_date_covid_sgss,
        tmp_exp_date_covid_gp,
        tmp_exp_date_covid_apc,
    )

    ## Inclusion criteria ----------------------------------------------------------

    ### First infection falls within the study window [study_start, study_end_exp].
    ### Patients whose first EVER infection pre-dates study_start are excluded;
    ### their later records would represent re-infections, not index events.
    inex_bin_first_covid_in_window = (
        exp_date_covid.is_on_or_between(study_start, study_end_exp)
    )

    ### Registered for a minimum of 6 months prior to the index date
    inex_bin_6m_reg = (
        practice_registrations
        .spanning(exp_date_covid - days(180), exp_date_covid)
        .exists_for_patient()
    )

    ### Alive on the index date
    inex_bin_alive = (
        (patients.date_of_death.is_null() | patients.date_of_death.is_after(exp_date_covid)) &
        (ons_deaths.date.is_null() | ons_deaths.date.is_after(exp_date_covid))
    )

    ## Censoring criteria ----------------------------------------------------------

    ### Deregistration: first practice end date on or after the index date
    cens_date_dereg = (
        practice_registrations
        .where(practice_registrations.end_date.is_not_null())
        .where(practice_registrations.end_date.is_on_or_after(exp_date_covid))
        .sort_by(practice_registrations.end_date)
        .first_for_patient()
        .end_date
    )

    ### Death
    cens_date_death = ons_deaths.date

    ### Second infection (re-infection)
    # The earliest positive COVID record from any source that falls at least
    # 90 days after the index date.  The 90-day gap excludes residual PCR
    # positivity from the original episode so that only genuine re-infections
    # trigger censoring.  Follow-up is censored at this date because a second
    # distinct infection represents a new exposure episode and any subsequent
    # outcome cannot be attributed solely to the first infection.

    tmp_cens_date_reinfection_sgss = (
        sgss_covid_all_tests
        .where(sgss_covid_all_tests.is_positive)
        .where(sgss_covid_all_tests.specimen_taken_date.is_on_or_after(exp_date_covid + days(90)))
        .sort_by(sgss_covid_all_tests.specimen_taken_date)
        .first_for_patient()
        .specimen_taken_date
    )

    tmp_cens_date_reinfection_gp = (
        clinical_events
        .where(
            clinical_events.ctv3_code.is_in(
                covid_primary_care_code +
                covid_primary_care_positive_test +
                covid_primary_care_sequalae
            )
        )
        .where(clinical_events.date.is_on_or_after(exp_date_covid + days(90)))
        .sort_by(clinical_events.date)
        .first_for_patient()
        .date
    )

    tmp_cens_date_reinfection_apc = (
        apcs
        .where(
            (apcs.primary_diagnosis.is_in(covid_codes)) |
            (apcs.secondary_diagnosis.is_in(covid_codes))
        )
        .where(apcs.admission_date.is_on_or_after(exp_date_covid + days(90)))
        .sort_by(apcs.admission_date)
        .first_for_patient()
        .admission_date
    )

    cens_date_reinfection = minimum_of(
        tmp_cens_date_reinfection_sgss,
        tmp_cens_date_reinfection_gp,
        tmp_cens_date_reinfection_apc,
    )

    ## Quality assurance ----------------------------------------------------------

    qa_bin_prostate_cancer = (
        last_matching_event_clinical_snomed_before(
            prostate_cancer_snomed, exp_date_covid
        ).exists_for_patient() |
        last_matching_event_apc_before(
            prostate_cancer_icd10, exp_date_covid
        ).exists_for_patient()
    )

    qa_bin_pregnancy = (
        last_matching_event_clinical_snomed_before(
            pregnancy_snomed, exp_date_covid
        ).exists_for_patient()
    )

    qa_num_birth_year = patients.date_of_birth.year

    qa_bin_hrtcocp = (
        last_matching_med_dmd_before(
            cocp_dmd + hrt_dmd, exp_date_covid
        ).exists_for_patient()
    )

    ## Strata ---------------------------------------------------------------------

    strat_cat_region = (
        practice_registrations
        .for_patient_on(exp_date_covid)
        .practice_nuts1_region_name
    )

    ## Core covariates — all measured at the index date ---------------------------

    cov_num_age = patients.age_on(exp_date_covid)

    cov_cat_sex = patients.sex

    cov_cat_ethnicity = get_latest_ethnicity(exp_date_covid, ethnicity_snomed, grouping=6)

    cov_cat_imd = case(
        when(
            (addresses.for_patient_on(exp_date_covid).imd_rounded >= 0) &
            (addresses.for_patient_on(exp_date_covid).imd_rounded < int(32844 * 1 / 5))
        ).then("1 (most deprived)"),
        when(addresses.for_patient_on(exp_date_covid).imd_rounded < int(32844 * 2 / 5)).then("2"),
        when(addresses.for_patient_on(exp_date_covid).imd_rounded < int(32844 * 3 / 5)).then("3"),
        when(addresses.for_patient_on(exp_date_covid).imd_rounded < int(32844 * 4 / 5)).then("4"),
        when(addresses.for_patient_on(exp_date_covid).imd_rounded < int(32844 * 5 / 5)).then("5 (least deprived)"),
        otherwise="unknown",
    )

    tmp_most_recent_smoking_cat = (
        last_matching_event_clinical_ctv3_before(smoking_clear, exp_date_covid)
        .ctv3_code.to_category(smoking_clear)
    )
    tmp_ever_smoked = (
        ever_matching_event_clinical_ctv3_before(
            filter_codes_by_category(smoking_clear, include=["S", "E"]),
            exp_date_covid,
        ).exists_for_patient()
    )
    cov_cat_smoking = case(
        when(tmp_most_recent_smoking_cat == "S").then("S"),
        when(
            (tmp_most_recent_smoking_cat == "E") |
            ((tmp_most_recent_smoking_cat == "N") & (tmp_ever_smoked == True))
        ).then("E"),
        when(
            (tmp_most_recent_smoking_cat == "N") & (tmp_ever_smoked == False)
        ).then("N"),
        otherwise="M",
    )

    cov_bin_carehome = (
        addresses.for_patient_on(exp_date_covid).care_home_is_potential_match |
        addresses.for_patient_on(exp_date_covid).care_home_requires_nursing |
        addresses.for_patient_on(exp_date_covid).care_home_does_not_require_nursing
    )

    cov_bin_hcworker = (
        occupation_on_covid_vaccine_record
        .where(occupation_on_covid_vaccine_record.is_healthcare_worker == True)
        .exists_for_patient()
    )

    cov_bin_dementia = (
        last_matching_event_clinical_snomed_before(dementia_snomed, exp_date_covid).exists_for_patient() |
        last_matching_event_apc_before(dementia_icd10, exp_date_covid).exists_for_patient()
    )

    cov_bin_liver_disease = (
        last_matching_event_clinical_snomed_before(liver_disease_snomed, exp_date_covid).exists_for_patient() |
        last_matching_event_apc_before(liver_disease_icd10, exp_date_covid).exists_for_patient()
    )

    cov_bin_ckd = (
        last_matching_event_clinical_snomed_before(ckd_snomed, exp_date_covid).exists_for_patient() |
        last_matching_event_apc_before(ckd_icd10, exp_date_covid).exists_for_patient()
    )

    cov_bin_cancer = (
        last_matching_event_clinical_snomed_before(cancer_snomed, exp_date_covid).exists_for_patient() |
        last_matching_event_apc_before(cancer_icd10, exp_date_covid).exists_for_patient()
    )

    cov_bin_hypertension = (
        last_matching_event_clinical_snomed_before(hypertension_snomed, exp_date_covid).exists_for_patient() |
        last_matching_med_dmd_before(hypertension_drugs_dmd, exp_date_covid).exists_for_patient() |
        last_matching_event_apc_before(hypertension_icd10, exp_date_covid).exists_for_patient()
    )

    cov_bin_diabetes = (
        last_matching_event_clinical_snomed_before(diabetes_snomed, exp_date_covid).exists_for_patient() |
        last_matching_med_dmd_before(diabetes_drugs_dmd, exp_date_covid).exists_for_patient() |
        last_matching_event_apc_before(diabetes_icd10, exp_date_covid).exists_for_patient()
    )

    cov_bin_obesity = (
        last_matching_event_clinical_snomed_before(obesity_snomed, exp_date_covid).exists_for_patient() |
        last_matching_event_apc_before(obesity_icd10, exp_date_covid).exists_for_patient()
    )

    cov_bin_copd = (
        last_matching_event_clinical_ctv3_before(copd_ctv3, exp_date_covid).exists_for_patient() |
        last_matching_event_apc_before(copd_icd10, exp_date_covid).exists_for_patient()
    )

    cov_bin_ami = (
        last_matching_event_clinical_snomed_before(ami_snomed, exp_date_covid).exists_for_patient() |
        last_matching_event_apc_before(ami_icd10 + ami_prior_icd10, exp_date_covid).exists_for_patient()
    )

    cov_bin_depression = (
        last_matching_event_clinical_snomed_before(depression_snomed, exp_date_covid).exists_for_patient() |
        last_matching_event_apc_before(depression_icd10, exp_date_covid).exists_for_patient()
    )

    ## Project-specific covariates ------------------------------------------------

    cov_bin_stroke_all = (
        last_matching_event_clinical_snomed_before(stroke_snomed, exp_date_covid).exists_for_patient() |
        last_matching_event_apc_before(stroke_icd10, exp_date_covid).exists_for_patient()
    )

    cov_bin_vte = (
        last_matching_event_clinical_snomed_before(vte_snomed, exp_date_covid).exists_for_patient() |
        last_matching_event_apc_before(vte_icd10, exp_date_covid).exists_for_patient()
    )

    cov_bin_hf = (
        last_matching_event_clinical_snomed_before(hf_snomed, exp_date_covid).exists_for_patient() |
        last_matching_event_apc_before(hf_icd10, exp_date_covid).exists_for_patient()
    )

    cov_bin_angina = (
        last_matching_event_clinical_snomed_before(angina_snomed, exp_date_covid).exists_for_patient() |
        last_matching_event_apc_before(angina_icd10, exp_date_covid).exists_for_patient()
    )

    cov_bin_other_ae = (
        last_matching_event_clinical_snomed_before(other_ae_snomed, exp_date_covid).exists_for_patient() |
        last_matching_event_apc_before(other_ae_icd10, exp_date_covid).exists_for_patient()
    )

    cov_bin_lipidmed     = last_matching_med_dmd_before(lipid_lowering_dmd,  exp_date_covid).exists_for_patient()
    cov_bin_antiplatelet = last_matching_med_dmd_before(antiplatelet_dmd,    exp_date_covid).exists_for_patient()
    cov_bin_anticoagulant = last_matching_med_dmd_before(anticoagulant_dmd,  exp_date_covid).exists_for_patient()
    cov_bin_cocp         = last_matching_med_dmd_before(cocp_dmd,            exp_date_covid).exists_for_patient()
    cov_bin_hrt          = last_matching_med_dmd_before(hrt_dmd,             exp_date_covid).exists_for_patient()

    ## COVID-19 severity subgroup -------------------------------------------------

    tmp_sub_date_covidhospital = (
        apcs
        .where(apcs.primary_diagnosis.is_in(covid_codes))
        .where(apcs.admission_date.is_on_or_after(exp_date_covid))
        .sort_by(apcs.admission_date)
        .first_for_patient()
        .admission_date
    )

    sub_cat_covidhospital = case(
        when(
            exp_date_covid.is_not_null() &
            tmp_sub_date_covidhospital.is_not_null() &
            ((tmp_sub_date_covidhospital - exp_date_covid).days >= 0) &
            ((tmp_sub_date_covidhospital - exp_date_covid).days < 29)
        ).then("hospitalised"),
        when(exp_date_covid.is_not_null()).then("non_hospitalised"),
        when(exp_date_covid.is_null()).then("no_infection"),
    )

    ## Assemble the variable dictionary -------------------------------------------

    dynamic_variables = dict(
        ### Exposure / index date (component dates kept for Venn diagrams)
        exp_date_covid             = exp_date_covid,
        tmp_exp_date_covid_sgss    = tmp_exp_date_covid_sgss,
        tmp_exp_date_covid_gp      = tmp_exp_date_covid_gp,
        tmp_exp_date_covid_apc     = tmp_exp_date_covid_apc,
        ### Inclusion criteria
        inex_bin_first_covid_in_window = inex_bin_first_covid_in_window,
        inex_bin_6m_reg                = inex_bin_6m_reg,
        inex_bin_alive                 = inex_bin_alive,
        ### Censoring
        cens_date_dereg               = cens_date_dereg,
        cens_date_death               = cens_date_death,
        cens_date_reinfection         = cens_date_reinfection,
        tmp_cens_date_reinfection_sgss = tmp_cens_date_reinfection_sgss,
        tmp_cens_date_reinfection_gp   = tmp_cens_date_reinfection_gp,
        tmp_cens_date_reinfection_apc  = tmp_cens_date_reinfection_apc,
        ### Quality assurance
        qa_bin_prostate_cancer     = qa_bin_prostate_cancer,
        qa_bin_pregnancy           = qa_bin_pregnancy,
        qa_num_birth_year          = qa_num_birth_year,
        qa_bin_hrtcocp             = qa_bin_hrtcocp,
        ### Strata
        strat_cat_region           = strat_cat_region,
        ### Core covariates
        cov_num_age                = cov_num_age,
        cov_cat_sex                = cov_cat_sex,
        cov_cat_ethnicity          = cov_cat_ethnicity,
        cov_cat_imd                = cov_cat_imd,
        cov_cat_smoking            = cov_cat_smoking,
        cov_bin_carehome           = cov_bin_carehome,
        cov_bin_hcworker           = cov_bin_hcworker,
        cov_bin_dementia           = cov_bin_dementia,
        cov_bin_liver_disease      = cov_bin_liver_disease,
        cov_bin_ckd                = cov_bin_ckd,
        cov_bin_cancer             = cov_bin_cancer,
        cov_bin_hypertension       = cov_bin_hypertension,
        cov_bin_diabetes           = cov_bin_diabetes,
        cov_bin_obesity            = cov_bin_obesity,
        cov_bin_copd               = cov_bin_copd,
        cov_bin_ami                = cov_bin_ami,
        cov_bin_depression         = cov_bin_depression,
        ### Project-specific covariates
        cov_bin_stroke_all         = cov_bin_stroke_all,
        cov_bin_vte                = cov_bin_vte,
        cov_bin_hf                 = cov_bin_hf,
        cov_bin_angina             = cov_bin_angina,
        cov_bin_other_ae           = cov_bin_other_ae,
        cov_bin_lipidmed           = cov_bin_lipidmed,
        cov_bin_antiplatelet       = cov_bin_antiplatelet,
        cov_bin_anticoagulant      = cov_bin_anticoagulant,
        cov_bin_cocp               = cov_bin_cocp,
        cov_bin_hrt                = cov_bin_hrt,
        ### COVID severity subgroup
        sub_cat_covidhospital      = sub_cat_covidhospital,
    )

    ## Dynamic outcome variables — generated from OUTCOMES registry ---------------
    # For each active outcome in outcomes_covid_cohort.py, five variables are added:
    #   tmp_out_date_{name}_gp / _apc / _death  (source-level dates)
    #   out_date_{name}                          (earliest date across sources)
    #   excl_bin_prior_{name}                    (prior-outcome exclusion flag)

    for outcome in OUTCOMES:
        outcome_vars = build_outcome_variables(outcome, exp_date_covid, study_end_out)
        dynamic_variables.update(outcome_vars)

    return dynamic_variables
