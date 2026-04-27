from dataset_definition_covid_cohort import generate_dataset

from ehrql import claim_permissions

from datetime import date

claim_permissions("sgss_covid_all_tests", "occupation_on_covid_vaccine_record")

# Study dates ------------------------------------------------------------------

# Start of the positive-test eligibility window.
# Only individuals whose FIRST infection falls on or after this date are included.
# UK COVID-19 vaccination programme (2020-12-08)
study_start = date(2020, 12, 8)

# End of mass testing (2022-04-01)
# Positive tests recorded after this date are not considered.
study_end_exp = date(2022, 4, 1)

# Administrative end of follow-up.
# Outcomes, death, and deregistration recorded after this date are censored.
# check the date of last update
study_end_out = date(2024, 12, 31)

# Create dataset ---------------------------------------------------------------

dataset = generate_dataset(study_start, study_end_exp, study_end_out)
