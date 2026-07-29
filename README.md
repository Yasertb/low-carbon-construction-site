# Low-Carbon Construction Site Dashboard — Version 2.3

This Streamlit package supports a Level 5 apprenticeship learning activity on one focused aspect of net-zero innovation: **decarbonising construction-site plant and temporary power**.

## Version 2.3 improvements

- Long categorical results are displayed in compact wrapping cards rather than oversized `st.metric` values, so the wording is shown in full.
- Carbon, energy supply, site compatibility, local environmental performance, delivery risk and cost remain separate decision dimensions.
- The method tab now shows the exact energy, carbon and indicative-cost equations used by the Python model.
- The electric-energy charts now compare **Required demand** with **Actual supply**.
- Unserved energy is no longer stacked as if it were a supply source.
- When energy is insufficient, the actual-supply bar remains below demand and the shortfall is labelled in red.
- A numerical table under each energy chart reports demand, actual supply and shortfall.
- The chart code independently checks that:
  - actual plant supply = plant demand − plant energy unserved;
  - actual temporary-power supply = temporary-power demand − temporary energy unserved.

## Decision structure

The app does not assign one overall `Suitable` label. It presents evidence in this order:

1. **Carbon performance** — total carbon, reduction from conventional diesel and result completeness.
2. **Energy supply status** — whether all plant and temporary-power demand is supplied and whether diesel backup is used.
3. **Site compatibility** — fit with community, noise and infrastructure conditions.
4. **Local environmental performance** — relative point-of-use exhaust NOx, exhaust PM and noise indicators.
5. **Delivery risk** — energy-related programme risk from charging, grid limits, backup dependence or unmet demand.
6. **Indicative cost** — total teaching cost and difference from the conventional-diesel baseline.

A carbon result is marked **incomplete** when required energy is unmet or batteries cannot be reliably restored for repeated daily operation.

## App structure

- A: Select the site
- B: Site and energy conditions
- C: Test net-zero options
- D: Results and decision
- E: How to use the app
- F: Method and calculation boundaries

## Run locally

```powershell
cd "C:\tools\low_carbon_construction_streamlit_v2_3_complete"
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The app normally opens at:

```text
http://localhost:8501
```

## Model verification

The package includes:

- `data/verification_tests_v2_3.csv`
- `data/modified_urban_example_results_v2_3.csv`
- `data/all_16_default_scenarios_v2_3.csv`

The verification checks independently recalculate supply balances, operational carbon, expanded energy carbon, energy cost and total cost for the modified urban-site example.

## Update the existing GitHub/Streamlit app

Replace the existing repository contents with this package. At minimum replace:

- `app.py`
- `model.py`
- `README.md`
- `CHANGELOG.md`
- the complete `data` folder
- the updated source workbook

Streamlit Community Cloud should redeploy the existing public app after the commit.

## Important modelling boundary

Included:

- diesel used by plant and generators;
- grid electricity;
- machine and site-battery energy balances;
- charging and storage losses;
- grid-power constraints;
- planned and additional charging;
- diesel backup;
- plant charging downtime;
- unserved plant and temporary-power demand;
- required off-shift recharge;
- operational and expanded energy carbon;
- indicative energy and equipment-hire cost.

Excluded:

- manufacture and end-of-life of machines and batteries;
- construction-material embodied carbon;
- detailed safety assessment;
- measured noise and air-pollution exposure;
- mechanical breakdown, maintenance and refuelling delays;
- labour, grid-connection installation, finance, overheads and other project costs not explicitly included.

This is an educational decision-support tool. It supports professional judgement; it does not replace project-specific engineering assessment.
