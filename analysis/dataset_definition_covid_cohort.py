from ehrql import (
    claim_permissions,
    create_dataset,
)

# Bring table definitions from the TPP backend
from ehrql.tables.tpp import (
    patients,
)

claim_permissions("sgss_covid_all_tests", "occupation_on_covid_vaccine_record")

# Create dataset

def generate_dataset(study_start, study_end_exp, study_end_out):
    dataset = create_dataset()

    # Broad population: any patient with a non-null date of birth.
    # The study-specific inclusion and exclusion criteria are captured as
    # boolean variables (inex_*, excl_*) and applied in the downstream
    # R cleaning script, mirroring the approach used in the original project.
    dataset.define_population(
        patients.date_of_birth.is_not_null()
    )

    # Configure dummy data
    dataset.configure_dummy_data(population_size=5000)

    # Import variables function
    from variables_covid_cohort import generate_variables

    variables = generate_variables(study_start, study_end_exp, study_end_out)

    # Assign each variable to the dataset
    for var_name, var_value in variables.items():
        setattr(dataset, var_name, var_value)

    return dataset
