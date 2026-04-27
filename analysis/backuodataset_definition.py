from ehrql import (
   # case,
    create_dataset,
    # days,
    # when,
    # minimum_of,
    # maximum_of,
    claim_permissions
)

from ehrql.tables.tpp import (
  patients,
  practice_registrations, 
  medications,
  vaccinations, 
  clinical_events, 
#   ons_deaths,
#   addresses,
)
# import codelists
from analysis import codelists

# Event-level frame of positive COVID tests in primary care
covid_positive = clinical_events.where(
    clinical_events.ctv3_code.is_in(codelists.covid_primary_care_positive_test)
)

dataset = create_dataset()
dataset.configure_dummy_data(population_size=1000)

index_date = "2020-03-31"

has_registration = practice_registrations.for_patient_on(
    index_date
).exists_for_patient()

dataset.define_population(has_registration)

dataset.sex = patients.sex





# COVID summaries (one value per patient)
dataset.add_event_table(
    "covid_positive",
    covid_date = covid_positive.date
)


