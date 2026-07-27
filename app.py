
from __future__ import annotations

import math

import pandas as pd
import plotly.express as px
import streamlit as st

from model import calculate_all_presets, calculate_scenarios, load_tables

st.set_page_config(
    page_title="Low-Carbon Construction Site",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

tables = load_tables()
sites = tables["sites"]
strategies = tables["strategies"]
factors = tables["factors"]
plant_specs = tables["plant_specs"]
tableau_reference = tables["tableau_wide"]

SHORT_NAMES = {
    "S1": "Conventional diesel",
    "S2": "Efficient diesel",
    "S3": "Grid electric",
    "S4": "Electric + smart power",
}

QUALITY_BADGES = {
    "Official 2026 UK factor": "Official factor",
    "Manufacturer specification": "Manufacturer specification",
    "Teaching assumption": "Teaching assumption",
}

st.title("Planning a Low-Carbon Construction Site")
st.caption(
    "Interactive Level 5 teaching prototype: electric plant, smart temporary power "
    "and cleaner-air co-benefits"
)

st.info(
    "Workplace challenge: recommend a plant and temporary-power strategy that reduces "
    "construction-site carbon without compromising safety, productivity, cost or programme delivery."
)

tab_dashboard, tab_method, tab_data, tab_teaching, tab_full = st.tabs(
    [
        "Interactive dashboard",
        "Method and calculations",
        "Data and sources",
        "Teaching activity",
        "All 16 preset scenarios",
    ]
)

# =====================================================================
# DASHBOARD TAB
# =====================================================================
with tab_dashboard:
    with st.sidebar:
        st.header("Scenario controls")

        selected_context = st.selectbox(
            "Construction-site context",
            sites["Site_Context"].tolist(),
            index=0,
        )
        preset = sites.loc[sites["Site_Context"] == selected_context].iloc[0].to_dict()

        st.caption(preset["Context_Note"])

        working_days = st.number_input(
            "Working days",
            min_value=1,
            max_value=365,
            value=int(preset["Working_Days"]),
            step=1,
        )
        shift_hours = st.slider(
            "Shift length (hours/day)",
            min_value=4.0,
            max_value=12.0,
            value=float(preset["Shift_Hours"]),
            step=0.5,
        )
        idle_percent_ui = st.slider(
            "Plant idling (%)",
            min_value=0,
            max_value=50,
            value=int(round(float(preset["Idle_Percent"]) * 100)),
            step=1,
        )
        temporary_power = st.slider(
            "Temporary site power (kWh/day)",
            min_value=0.0,
            max_value=100.0,
            value=float(preset["Temporary_Power_kWh_per_day"]),
            step=1.0,
        )

        st.subheader("Carbon and price inputs")

        grid_carbon = st.number_input(
            "Grid carbon factor (kgCO₂e/kWh)",
            min_value=0.0,
            max_value=1.0,
            value=float(preset["Grid_Carbon_kgCO2e_per_kWh"]),
            step=0.005,
            format="%.5f",
        )
        diesel_price = st.number_input(
            "Diesel price (£/litre)",
            min_value=0.0,
            max_value=5.0,
            value=float(preset["Diesel_Price_GBP_per_L"]),
            step=0.05,
            format="%.2f",
        )
        electricity_price = st.number_input(
            "Electricity price (£/kWh)",
            min_value=0.0,
            max_value=2.0,
            value=float(preset["Electricity_Price_GBP_per_kWh"]),
            step=0.01,
            format="%.2f",
        )

        carbon_boundary = st.radio(
            "Carbon boundary shown in the main chart",
            [
                "Operational carbon",
                "Expanded energy carbon",
            ],
            help=(
                "Operational carbon includes diesel combustion and grid electricity generation. "
                "Expanded energy carbon also includes upstream diesel, electricity transmission/"
                "distribution and upstream electricity emissions."
            ),
        )

        st.divider()
        st.caption(
            "The preset data come from the same workbook prepared for Tableau. "
            "Cost, fuel-rate, productivity and downtime values are teaching assumptions."
        )

    editable_site = {
        **preset,
        "Working_Days": working_days,
        "Shift_Hours": shift_hours,
        "Idle_Percent": idle_percent_ui / 100.0,
        "Temporary_Power_kWh_per_day": temporary_power,
        "Grid_Carbon_kgCO2e_per_kWh": grid_carbon,
        "Diesel_Price_GBP_per_L": diesel_price,
        "Electricity_Price_GBP_per_kWh": electricity_price,
    }

    results = calculate_scenarios(
        editable_site,
        strategies,
        factors,
        plant_specs,
    )
    results["Short_Name"] = results["Strategy_ID"].map(SHORT_NAMES)

    if carbon_boundary == "Operational carbon":
        carbon_field = "Operational_CO2e_kg"
        reduction_field = "Operational_Reduction_vs_Baseline"
        carbon_title = "Operational carbon"
    else:
        carbon_field = "Expanded_Energy_CO2e_kg"
        reduction_field = "Expanded_Reduction_vs_Baseline"
        carbon_title = "Expanded energy carbon"

    best = results.sort_values([carbon_field, "Total_Cost_GBP"]).iloc[0]

    st.subheader(f"{selected_context}: scenario results")

    if str(preset["Grid_Availability"]).lower() == "limited":
        st.warning(
            "This preset has limited grid access. Electric options remain visible so apprentices "
            "can decide whether charging logistics, battery storage or a backup plan make them practical."
        )

    k1, k2, k3, k4 = st.columns(4)
    k1.metric(
        f"Lowest calculated {carbon_title.lower()}",
        f"{best[carbon_field]:,.0f} kgCO₂e",
        SHORT_NAMES[best["Strategy_ID"]],
    )
    k2.metric(
        "Reduction from baseline",
        f"{best[reduction_field]:.0%}",
    )
    k3.metric(
        "Indicative total cost",
        f"£{best['Total_Cost_GBP']:,.0f}",
    )
    k4.metric(
        "Assumed downtime for this option",
        f"{best['Expected_Downtime_h_per_day']:.1f} h/day",
    )

    st.info(
        "The lowest-carbon option is not automatically the recommended option. "
        "Apprentices must also consider grid access, safety, cost, productivity "
        "and programme risk."
    )

    col_a, col_b = st.columns(2)

    with col_a:
        fig_carbon = px.bar(
            results,
            x="Short_Name",
            y=carbon_field,
            text_auto=".0f",
            labels={
                "Short_Name": "Strategy",
                carbon_field: f"{carbon_title} (kgCO₂e)",
            },
            title=f"{carbon_title} by strategy",
        )
        fig_carbon.update_layout(showlegend=False)
        st.plotly_chart(fig_carbon, use_container_width=True)

    with col_b:
        fig_cost = px.bar(
            results,
            x="Short_Name",
            y="Total_Cost_GBP",
            text_auto=".0f",
            labels={
                "Short_Name": "Strategy",
                "Total_Cost_GBP": "Indicative total cost (£)",
            },
            title="Indicative total cost by strategy",
        )
        fig_cost.update_layout(showlegend=False)
        st.plotly_chart(fig_cost, use_container_width=True)

    fig_tradeoff = px.scatter(
        results,
        x="Total_Cost_GBP",
        y=carbon_field,
        size="Productivity_Index",
        text="Short_Name",
        hover_name="Strategy",
        hover_data={
            "Expected_Downtime_h_per_day": ":.2f",
            "Air_Quality_Benefit_Index": ":.0f",
            "Noise_Benefit_Index": ":.0f",
        },
        labels={
            "Total_Cost_GBP": "Indicative total cost (£)",
            carbon_field: f"{carbon_title} (kgCO₂e)",
            "Productivity_Index": "Productivity index",
        },
        title="Carbon–cost–productivity trade-off",
    )
    fig_tradeoff.update_traces(textposition="top center")
    st.plotly_chart(fig_tradeoff, use_container_width=True)

    st.subheader("Compare construction and community effects")

    co_left, co_right = st.columns(2)

    with co_left:
        benefit_long = results[
            ["Short_Name", "Air_Quality_Benefit_Index", "Noise_Benefit_Index"]
        ].melt(
            id_vars="Short_Name",
            var_name="Benefit",
            value_name="Index",
        )
        benefit_long["Benefit"] = benefit_long["Benefit"].replace({
            "Air_Quality_Benefit_Index": "Cleaner-air benefit",
            "Noise_Benefit_Index": "Noise benefit",
        })
        fig_benefits = px.bar(
            benefit_long,
            x="Short_Name",
            y="Index",
            color="Benefit",
            barmode="group",
            labels={"Short_Name": "Strategy", "Index": "Relative benefit index (0–100)"},
            title="Cleaner-air and noise co-benefits",
        )
        st.plotly_chart(fig_benefits, use_container_width=True)

    with co_right:
        fig_downtime = px.bar(
            results,
            x="Short_Name",
            y="Expected_Downtime_h_per_day",
            text_auto=".2f",
            labels={
                "Short_Name": "Strategy",
                "Expected_Downtime_h_per_day": "Assumed downtime (h/day)",
            },
            title="Assumed downtime by strategy",
        )
        fig_downtime.update_layout(showlegend=False)
        st.plotly_chart(fig_downtime, use_container_width=True)

    st.subheader("Investigate one strategy")

    selected_strategy = st.selectbox(
        "Strategy for closer review",
        results["Strategy"].tolist(),
    )
    detail = results.loc[results["Strategy"] == selected_strategy].iloc[0]

    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Operational carbon", f"{detail['Operational_CO2e_kg']:,.0f} kgCO₂e")
    d2.metric("Expanded energy carbon", f"{detail['Expanded_Energy_CO2e_kg']:,.0f} kgCO₂e")
    d3.metric("Air-quality benefit", f"{detail['Air_Quality_Benefit_Index']:.0f}/100")
    d4.metric("Battery charges/day", f"{detail['Battery_Charges_per_Day']:.0f}")

    st.write("**Main practical risk:**", detail["Key_Risk"])
    st.write("**Teaching note:**", detail["Teaching_Note"])
    st.write("**Data-quality note:**", detail["Data_Quality_Note"])

    with st.expander("View or download the current scenario results"):
        display = results[
            [
                "Strategy",
                "Operational_CO2e_kg",
                "Expanded_Energy_CO2e_kg",
                "Operational_Reduction_vs_Baseline",
                "Expanded_Reduction_vs_Baseline",
                "Total_Cost_GBP",
                "Productivity_Index",
                "Expected_Downtime_h_per_day",
                "Air_Quality_Benefit_Index",
                "Noise_Benefit_Index",
            ]
        ].copy()

        display["Operational_Reduction_vs_Baseline"] *= 100
        display["Expanded_Reduction_vs_Baseline"] *= 100

        display = display.rename(columns={
            "Operational_CO2e_kg": "Operational CO₂e (kg)",
            "Expanded_Energy_CO2e_kg": "Expanded energy CO₂e (kg)",
            "Operational_Reduction_vs_Baseline": "Operational reduction (%)",
            "Expanded_Reduction_vs_Baseline": "Expanded reduction (%)",
            "Total_Cost_GBP": "Indicative total cost (£)",
            "Productivity_Index": "Productivity index",
            "Expected_Downtime_h_per_day": "Assumed downtime (h/day)",
            "Air_Quality_Benefit_Index": "Cleaner-air benefit (0–100)",
            "Noise_Benefit_Index": "Noise benefit (0–100)",
        })

        st.dataframe(display, use_container_width=True, hide_index=True)
        st.download_button(
            "Download current results",
            results.to_csv(index=False).encode("utf-8"),
            file_name="current_low_carbon_site_results.csv",
            mime="text/csv",
        )

    st.warning(
        "The dashboard supports professional judgement. It does not replace safety checks, "
        "technical specification, site planning or engineering responsibility."
    )

# =====================================================================
# METHOD TAB
# =====================================================================
with tab_method:
    st.header("Method and calculation boundaries")

    st.markdown(
        """
The dashboard applies the same calculation structure used in the Tableau workbook.

### Operational carbon

**Diesel plant and generators**

`Diesel CO₂e = total diesel used × diesel direct-emission factor`

**Electric plant and temporary grid power**

`Electric CO₂e = total grid electricity × effective grid-carbon factor`

The effective grid factor can be reduced in the smart-charging teaching scenario to represent
charging during lower-carbon periods. This is an assumption that apprentices should question.

### Expanded energy carbon

The expanded boundary adds:

- diesel well-to-tank emissions;
- electricity transmission and distribution;
- upstream electricity-generation emissions.

### Cost

`Total indicative cost = energy cost + plant hire cost + temporary-power-system cost`

### Carbon reduction

`Reduction = 1 − selected strategy carbon ÷ conventional-diesel baseline carbon`
"""
    )

    st.subheader("Included and excluded effects")

    boundary_table = pd.DataFrame(
        [
            ["Diesel combustion", "Included", "Operational and expanded"],
            ["Grid electricity generation", "Included", "Operational and expanded"],
            ["Diesel well-to-tank", "Included", "Expanded only"],
            ["Electricity transmission/distribution", "Included", "Expanded only"],
            ["Electricity well-to-tank", "Included", "Expanded only"],
            ["Plant and battery manufacture", "Excluded", "Future whole-life extension"],
            ["Plant end of life", "Excluded", "Future whole-life extension"],
            ["Construction dust exposure", "Excluded", "Requires separate assessment"],
            ["Detailed noise modelling", "Excluded", "Relative index only"],
        ],
        columns=["Effect", "Status", "Boundary / comment"],
    )
    st.dataframe(boundary_table, use_container_width=True, hide_index=True)

    st.subheader("Why show two carbon boundaries?")
    st.write(
        "The comparison helps apprentices understand that a result depends on the chosen "
        "system boundary. A machine may have zero exhaust emissions at the point of use "
        "without being zero carbon."
    )

    st.subheader("Data-quality approach")
    st.markdown(
        """
- **Official published factors** are used for UK diesel and electricity emissions.
- **Manufacturer specifications** support battery capacity, runtime and charging assumptions.
- **Teaching assumptions** are used for fuel rate, hire cost, productivity, downtime and smart charging.
- Apprentices are expected to identify which assumptions require project or supplier verification.
"""
    )

# =====================================================================
# DATA TAB
# =====================================================================
with tab_data:
    st.header("Data, sources and quality")

    st.subheader("Emission factors")
    st.dataframe(
        factors,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Primary_Source_URL": st.column_config.LinkColumn("Primary source"),
        },
    )

    st.subheader("Plant specifications")
    st.dataframe(
        plant_specs,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Source_URL": st.column_config.LinkColumn("Source"),
        },
    )

    st.subheader("Site presets")
    st.dataframe(sites, use_container_width=True, hide_index=True)

    st.subheader("Strategy assumptions")
    st.dataframe(strategies, use_container_width=True, hide_index=True)

    st.download_button(
        "Download the original Tableau source workbook",
        data=open("ARU_low_carbon_construction_tableau_data.xlsx", "rb").read(),
        file_name="ARU_low_carbon_construction_tableau_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.caption(
        "The original workbook is included so users can inspect the exact assumptions, "
        "calculated scenarios and source notes used to build this app."
    )

# =====================================================================
# TEACHING TAB
# =====================================================================
with tab_teaching:
    st.header("Level 5 apprentice teaching activity")

    st.subheader("Workplace task")
    st.info(
        "Recommend a practical plant and temporary-power strategy for the selected construction "
        "site. Reduce carbon without compromising safety, productivity, cost or programme delivery."
    )

    teaching_cols = st.columns(2)

    with teaching_cols[0]:
        st.markdown(
            """
### What apprentices do

1. Select a site context.
2. Compare diesel, efficient diesel, grid-electric and smart-power strategies.
3. Test idling, shift length, temporary power, electricity carbon and price assumptions.
4. Report the expected carbon reduction and indicative cost.
5. Identify one charging, safety, productivity or programme risk.
6. Explain cleaner-air and noise co-benefits.
7. Present a recommended strategy and a backup plan.
"""
        )

    with teaching_cols[1]:
        st.markdown(
            """
### Why the activity is designed this way

- It links university learning to an authentic workplace decision.
- It requires application, analysis, evaluation and justified judgement.
- It develops critical use of digital information rather than passive software use.
- It allows apprentices with different workplace experience to learn from one another.
- It combines technical carbon analysis with cost, programme, communication and risk.
"""
        )

    st.subheader("Evidence of learning")
    st.markdown(
        """
An apprentice demonstrates learning when they can:

- distinguish zero exhaust emissions from zero operational carbon;
- explain how the system boundary changes the result;
- use the dashboard to compare alternatives;
- identify weak or assumed data;
- justify a site-specific recommendation;
- communicate limitations and a practical backup plan.
"""
    )

    st.subheader("Suggested group roles")
    role_df = pd.DataFrame(
        [
            ["Site manager", "Productivity, programme, logistics and safety"],
            ["Sustainability adviser", "Carbon boundary, assumptions and evidence"],
            ["Commercial representative", "Indicative cost and procurement"],
            ["Community/client representative", "Noise, local air quality and acceptance"],
        ],
        columns=["Role", "Main perspective"],
    )
    st.dataframe(role_df, use_container_width=True, hide_index=True)

    st.subheader("Teaching alignment")
    st.markdown(
        """
**Level 5 learning:** application, analysis, evaluation and justified professional judgement.

**PSF 2023 dimensions used in the session:** planning learning, teaching and supporting learning,
assessment and feedback, suitable digital resources, inclusive participation and evidence-informed practice.

**Engineering outcomes:** sustainability, digital practice, risk, communication, professional judgement
and awareness of environmental and societal effects.

The session is aligned with selected dimensions and outcomes; it does not claim that one activity
covers every PSF or programme-accreditation requirement.
"""
    )

    st.subheader("Discussion prompts")
    st.markdown(
        """
- Is the lowest-carbon strategy always the best construction decision?
- What evidence is missing before using these results on a real project?
- When could efficient diesel be more practical than immediate electrification?
- How does limited grid access change the recommendation?
- What is the difference between a cleaner local environment and full whole-life net zero?
"""
    )

# =====================================================================
# ALL SCENARIOS TAB
# =====================================================================
with tab_full:
    st.header("All 16 preset context–strategy combinations")

    all_dynamic = calculate_all_presets(tables)
    all_dynamic["Short_Name"] = all_dynamic["Strategy_ID"].map(SHORT_NAMES)

    st.write(
        "This table is recalculated directly from the site presets, strategy assumptions, "
        "emission factors and plant specifications used in the original Tableau workbook."
    )

    st.dataframe(
        all_dynamic,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download all recalculated preset scenarios",
        all_dynamic.to_csv(index=False).encode("utf-8"),
        file_name="all_16_low_carbon_construction_scenarios.csv",
        mime="text/csv",
    )

    with st.expander("Compare with the original Tableau-wide results"):
        st.dataframe(
            tableau_reference,
            use_container_width=True,
            hide_index=True,
        )
        st.download_button(
            "Download original Tableau-wide table",
            tableau_reference.to_csv(index=False).encode("utf-8"),
            file_name="original_tableau_wide.csv",
            mime="text/csv",
        )

st.caption(
    "Educational prototype prepared for a Level 5 civil engineering apprenticeship session. "
    "Public or fictional teaching data only."
)
