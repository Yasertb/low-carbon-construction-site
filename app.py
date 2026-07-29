from __future__ import annotations

from pathlib import Path
import html

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from model import (
    build_custom_strategy,
    calculate_scenarios,
    default_value,
    load_tables,
)

st.set_page_config(
    page_title="Low-Carbon Construction Site",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

BASE_DIR = Path(__file__).resolve().parent
tables = load_tables()
sites = tables["sites"]
strategies = tables["strategies"]
factors = tables["factors"]
plant_specs = tables["plant_specs"]
defaults = tables["energy_defaults"]

ENERGY_STATUS_ORDER = [
    "All demand supplied",
    "All demand supplied using diesel backup",
    "Daily demand supplied; recharge cycle incomplete",
    "Demand partly unmet",
    "Demand cannot be supplied",
]

HELP = {
    "working_days": "Total number of working days included in the comparison.",
    "shift": "Number of hours the plant is required each working day.",
    "idling": "Time when the machine is running but is not doing useful work.",
    "planned_charge": "Time available for charging during planned breaks or stops without delaying the work.",
    "temporary_power": "Electricity required for site cabins, lighting, tools and other temporary equipment.",
    "diesel_rate": "Fuel used by the conventional diesel machine during one hour of active work.",
    "diesel_idle_fraction": "Fuel used while idling as a share of the active-work fuel rate.",
    "generator_rate": "Diesel required to produce one kWh of temporary electricity.",
    "backup": "Allows a diesel generator to provide energy when the electric system cannot meet demand.",
    "electric_rate": "Electricity used by the electric machine during one hour of active work.",
    "battery_capacity": "Maximum energy stored in the electric plant battery.",
    "usable_battery": "Share of the battery capacity available for normal operation.",
    "charger_power": "Maximum rate at which the charger can supply electricity before the site grid limit is applied.",
    "charging_eff": "Share of charger electricity that reaches the machine battery after charging losses.",
    "bess": "A temporary battery-energy-storage system that can support plant charging and site power.",
    "bess_capacity": "Maximum energy stored in the temporary site battery system.",
    "bess_eff": "Share of electricity returned after battery-storage losses.",
    "overnight": "Whether batteries can be recharged on site between working shifts.",
    "break_charge": "Whether planned breaks can be used for charging without creating downtime.",
    "grid": "The public electricity network used to supply the site and charge electric equipment.",
    "grid_power": "Maximum electrical power available from the site connection at one time.",
    "grid_share": "Share of temporary site-power demand supplied directly from the grid.",
    "smart": "Moves charging to periods when electricity is available, cheaper or lower in carbon.",
    "low_carbon_share": "Share of charging that can be moved to lower-carbon electricity periods.",
    "grid_factor": "Carbon emitted for each kWh of grid electricity used.",
    "diesel_factor": "Carbon emitted from using one litre of diesel.",
    "downtime": "Time when the plant cannot work because it is charging, lacks energy or has no available power supply.",
    "energy_status": "Whether the strategy supplies all plant and temporary-power demand, and whether diesel backup is required.",
    "site_compatibility": "How well the strategy matches local noise, community and infrastructure conditions.",
    "delivery_risk": "Energy-related risk to programme delivery from grid limits, charging, backup dependence or unmet demand.",
}

st.markdown(
    """
    <style>
    .decision-card {
        border: 1px solid rgba(49, 51, 63, 0.20);
        border-radius: 0.65rem;
        padding: 0.9rem 1rem;
        min-height: 7.2rem;
        background: rgba(248, 250, 252, 0.72);
        margin-bottom: 0.5rem;
    }
    .decision-card-title {
        font-size: 0.82rem;
        line-height: 1.25;
        color: rgba(49, 51, 63, 0.72);
        margin-bottom: 0.45rem;
        font-weight: 600;
    }
    .decision-card-value {
        font-size: 1.12rem;
        line-height: 1.35;
        color: rgb(31, 41, 55);
        font-weight: 650;
        overflow-wrap: anywhere;
        word-break: normal;
    }
    .decision-card-note {
        margin-top: 0.45rem;
        font-size: 0.78rem;
        line-height: 1.3;
        color: rgba(49, 51, 63, 0.68);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

PLOTLY_CONFIG = {
    "displayModeBar": False,
    "responsive": True,
}


def make_plot_mobile_friendly(
    fig: go.Figure,
    *,
    height: int = 520,
    legend: bool = True,
    tick_angle: int | None = -20,
) -> go.Figure:
    """Use a full-width, mobile-readable Plotly layout without changing data."""
    layout_updates = {
        "autosize": True,
        "height": height,
        "margin": {"l": 48, "r": 16, "t": 115 if legend else 78, "b": 105},
        "title": {"x": 0.0, "xanchor": "left", "font": {"size": 18}},
        "hoverlabel": {"font": {"size": 12}},
    }
    if legend:
        layout_updates["legend"] = {
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0.0,
            "title": {"text": ""},
            "font": {"size": 10},
        }
    else:
        layout_updates["showlegend"] = False

    fig.update_layout(**layout_updates)
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
    if tick_angle is not None:
        fig.update_xaxes(tickangle=tick_angle)
    return fig


def show_plot(fig: go.Figure) -> None:
    st.plotly_chart(
        fig,
        use_container_width=True,
        config=PLOTLY_CONFIG,
    )


def decision_card(title: str, value: object, note: str | None = None) -> None:
    """Render a compact wrapping card for categorical decision evidence."""
    title_html = html.escape(str(title))
    value_html = html.escape(str(value))
    note_html = (
        f'<div class="decision-card-note">{html.escape(str(note))}</div>'
        if note
        else ""
    )

    # Keep the HTML on one continuous, non-indented line. Markdown interprets
    # four or more leading spaces as a code block, which can expose closing
    # tags such as </div> in the visible dashboard.
    card_html = (
        '<div class="decision-card">'
        f'<div class="decision-card-title">{title_html}</div>'
        f'<div class="decision-card-value">{value_html}</div>'
        f'{note_html}'
        '</div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)



def build_demand_supply_chart(
    data: pd.DataFrame,
    *,
    components: dict[str, str],
    demand_field: str,
    unserved_field: str,
    title: str,
    y_axis_title: str,
) -> tuple[go.Figure, pd.DataFrame]:
    """Compare required demand with actual supplied energy.

    The required-demand bar is shown beside a stacked actual-supply bar. Unserved
    energy is deliberately excluded from the supply stack, so any shortfall remains
    visible rather than being presented as if it were an energy source.
    """
    chart_data = data.copy()
    component_fields = list(components)
    chart_data["Actual_Supply_kWh_per_day"] = chart_data[component_fields].sum(axis=1)
    chart_data["Calculated_Shortfall_kWh_per_day"] = (
        chart_data[demand_field] - chart_data["Actual_Supply_kWh_per_day"]
    ).clip(lower=0.0)

    if not (
        chart_data["Calculated_Shortfall_kWh_per_day"]
        .sub(chart_data[unserved_field])
        .abs()
        .le(1e-6)
        .all()
    ):
        raise ValueError(
            f"Energy-balance check failed for {title}: actual supply does not equal demand minus unserved energy."
        )

    strategy_names = chart_data["Short_Name"].astype(str).tolist()
    demand_x = [strategy_names, ["Required demand"] * len(chart_data)]
    supply_x = [strategy_names, ["Actual supply"] * len(chart_data)]

    fig = go.Figure()
    fig.add_bar(
        x=demand_x,
        y=chart_data[demand_field],
        name="Required demand",
        marker_color="#A9B4C0",
        hovertemplate="Required demand: %{y:.2f} kWh/day<extra></extra>",
    )
    for field, label in components.items():
        # Do not show irrelevant zero-valued components in the legend.
        # This reduces clutter on mobile without changing any calculation.
        if chart_data[field].abs().sum() <= 1e-9:
            continue
        fig.add_bar(
            x=supply_x,
            y=chart_data[field],
            name=label,
            hovertemplate=label + ": %{y:.2f} kWh/day<extra></extra>",
        )

    max_demand = max(float(chart_data[demand_field].max()), 1.0)
    shortfall_text = [
        f"Shortfall {value:.2f} kWh/day" if value > 0.01 else ""
        for value in chart_data["Calculated_Shortfall_kWh_per_day"]
    ]
    fig.add_scatter(
        x=supply_x,
        y=chart_data["Actual_Supply_kWh_per_day"] + max_demand * 0.045,
        mode="text",
        text=shortfall_text,
        textfont={"color": "#B42318", "size": 12},
        showlegend=False,
        hoverinfo="skip",
    )
    fig.update_layout(
        barmode="stack",
        title=None,
        xaxis_title=None,
        yaxis_title=y_axis_title,
    )
    fig.update_yaxes(rangemode="tozero")
    make_plot_mobile_friendly(fig, height=590, legend=True, tick_angle=-20)
    fig.update_layout(
        margin={"l": 48, "r": 16, "t": 105, "b": 105},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.01,
            "xanchor": "left",
            "x": 0.0,
            "title": {"text": ""},
            "font": {"size": 10},
        },
    )

    summary = chart_data[
        ["Short_Name", demand_field, "Actual_Supply_kWh_per_day", "Calculated_Shortfall_kWh_per_day"]
    ].rename(
        columns={
            "Short_Name": "Strategy",
            demand_field: "Required demand (kWh/day)",
            "Actual_Supply_kWh_per_day": "Actual supply (kWh/day)",
            "Calculated_Shortfall_kWh_per_day": "Shortfall (kWh/day)",
        }
    )
    return fig, summary


def metric_value(value: float, suffix: str = "", decimals: int = 1) -> str:
    return f"{value:,.{decimals}f}{suffix}"


def bool_value(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "on"}


def default_map() -> dict[str, float]:
    return {
        row["Parameter"]: float(row["Value"])
        for _, row in defaults.iterrows()
    }


DEFAULTS = default_map()


def selected_preset() -> dict[str, object]:
    name = st.session_state.get("selected_context", sites.iloc[0]["Site_Context"])
    return sites.loc[sites["Site_Context"] == name].iloc[0].to_dict()


def load_preset() -> None:
    p = selected_preset()
    st.session_state.update(
        {
            "working_days": int(p["Working_Days"]),
            "shift_hours": float(p["Shift_Hours"]),
            "idle_percent_ui": int(round(float(p["Idle_Percent"]) * 100)),
            "planned_charging_hours": float(p["Planned_Charging_Hours"]),
            "temporary_power": float(p["Temporary_Power_kWh_per_day"]),
            "grid_availability": str(p["Grid_Availability"]),
            "max_grid_power": float(p["Max_Grid_Power_kW"]),
            "overnight_charging": bool_value(p["Overnight_Charging_Available"]),
            "charging_during_breaks": bool_value(p["Charging_During_Breaks"]),
            "battery_storage_available": bool_value(p["Battery_Storage_Available"]),
            "diesel_backup_available": bool_value(p["Diesel_Backup_Available"]),
            "grid_temp_share_ui": int(round(float(p["Grid_Temporary_Power_Share"]) * 100)),
            "smart_charging_available": bool_value(p["Smart_Charging_Available"]),
            "lower_carbon_share_ui": int(round(float(p["Lower_Carbon_Charging_Share"]) * 100)),
            "grid_factor": float(p["Grid_Carbon_kgCO2e_per_kWh"]),
            "diesel_price": float(p["Diesel_Price_GBP_per_L"]),
            "electricity_price": float(p["Electricity_Price_GBP_per_kWh"]),
            "machine_battery": DEFAULTS["Machine_Battery_Capacity_kWh"],
            "machine_usable_ui": int(round(DEFAULTS["Machine_Usable_Battery_Fraction"] * 100)),
            "charger_power": DEFAULTS["Charger_Power_kW"],
            "charging_eff_ui": int(round(DEFAULTS["Charging_Efficiency"] * 100)),
            "bess_capacity": DEFAULTS["BESS_Capacity_kWh"],
            "bess_usable_ui": int(round(DEFAULTS["BESS_Usable_Fraction"] * 100)),
            "bess_eff_ui": int(round(DEFAULTS["BESS_Roundtrip_Efficiency"] * 100)),
            "lower_carbon_multiplier_ui": int(round(DEFAULTS["Lower_Carbon_Grid_Multiplier"] * 100)),
            "diesel_plant_rate": 3.20,
            "diesel_idle_fraction_ui": 35,
            "generator_rate": 0.30,
            "efficient_generator_rate": 0.24,
            "electric_rate": 3.33,
            "include_custom": False,
            "custom_reduce_idling": True,
            "custom_electric": True,
            "custom_grid_temp": True,
            "custom_bess": False,
            "custom_smart": False,
            "custom_backup": bool_value(p["Diesel_Backup_Available"]),
        }
    )


if "selected_context" not in st.session_state:
    st.session_state["selected_context"] = sites.iloc[0]["Site_Context"]
    load_preset()

st.title("Planning a Low-Carbon Construction Site")
st.subheader("Electric plant, battery storage, smart charging and cleaner temporary power")
st.caption(
    "Use the dashboard to compare carbon performance, energy supply, local environmental effects, delivery risk and indicative cost."
)
st.info(
    "Carbon reduction is the main net-zero objective. A credible recommendation must also supply the required energy, "
    "fit the site, manage local exhaust and noise, control delivery risk and consider indicative cost."
)

section_a, section_b, section_c, section_d, section_e, section_f = st.tabs(
    [
        "A · Select the site",
        "B · Site and energy conditions",
        "C · Test net-zero options",
        "D · Results and decision",
        "E · How to use the app",
        "F · Method and calculation boundaries",
    ]
)

# =====================================================================
# SECTION A
# =====================================================================
with section_a:
    st.header("A — Select the construction site")
    left, right = st.columns([1, 1.35])

    with left:
        st.selectbox(
            "Construction-site context",
            sites["Site_Context"].tolist(),
            key="selected_context",
            on_change=load_preset,
            help="Loads suitable starting values for a realistic workplace situation.",
        )
        st.button("Reset to site default values", on_click=load_preset, use_container_width=True)

    p = selected_preset()
    with right:
        with st.container(border=True):
            st.subheader(str(p["Site_Context"]))
            c1, c2, c3 = st.columns(3)
            c1.metric("Grid", str(p["Grid_Availability"]))
            c2.metric("Noise sensitivity", str(p["Noise_Sensitivity"]))
            c3.metric("Community sensitivity", str(p["Community_Sensitivity"]))
            st.write("**Main challenge:**", p["Main_Challenge"])
            st.write(p["Context_Note"])

    st.markdown(
        "**Learning question:** Which plant and temporary-power strategy can reduce carbon "
        "while remaining practical for this particular site?"
    )

# =====================================================================
# SECTION B
# =====================================================================
with section_b:
    st.header("B — Site and energy conditions")
    st.caption("Default values are provided so apprentices can begin quickly and then test alternatives.")

    with st.container(border=True):
        st.subheader("B1 · Work programme")
        b1, b2, b3, b4, b5 = st.columns(5)
        with b1:
            st.number_input(
                "Working days",
                min_value=1,
                max_value=365,
                step=1,
                key="working_days",
                help=HELP["working_days"],
            )
        with b2:
            st.slider(
                "Shift length (hours/day)",
                4.0,
                12.0,
                step=0.5,
                key="shift_hours",
                help=HELP["shift"],
            )
        with b3:
            st.slider(
                "Plant idling (%)",
                0,
                50,
                step=1,
                key="idle_percent_ui",
                help=HELP["idling"],
            )
        with b4:
            st.number_input(
                "Planned charging time (h/day)",
                min_value=0.0,
                max_value=8.0,
                step=0.25,
                key="planned_charging_hours",
                help=HELP["planned_charge"],
            )
        with b5:
            st.number_input(
                "Temporary site power (kWh/day)",
                min_value=0.0,
                max_value=500.0,
                step=1.0,
                key="temporary_power",
                help=HELP["temporary_power"],
            )

    diesel_col, electric_col = st.columns(2)

    with diesel_col:
        with st.container(border=True):
            st.subheader("B2 · Diesel plant and generator")
            st.number_input(
                "Diesel plant fuel use (L/active hour)",
                min_value=0.1,
                max_value=20.0,
                step=0.1,
                key="diesel_plant_rate",
                help=HELP["diesel_rate"],
            )
            st.slider(
                "Idling fuel rate (% of active rate)",
                0,
                100,
                step=1,
                key="diesel_idle_fraction_ui",
                help=HELP["diesel_idle_fraction"],
            )
            st.number_input(
                "Conventional generator fuel use (L/kWh)",
                min_value=0.05,
                max_value=1.0,
                step=0.01,
                key="generator_rate",
                help=HELP["generator_rate"],
            )
            st.number_input(
                "Efficient generator fuel use (L/kWh)",
                min_value=0.05,
                max_value=1.0,
                step=0.01,
                key="efficient_generator_rate",
                help="Lower fuel rate used for the efficient-diesel transition strategy.",
            )
            st.toggle(
                "Diesel backup available",
                key="diesel_backup_available",
                help=HELP["backup"],
            )

    with electric_col:
        with st.container(border=True):
            st.subheader("B3 · Electric plant, battery and charging")
            e1, e2 = st.columns(2)
            with e1:
                st.number_input(
                    "Electric plant energy use (kWh/active hour)",
                    min_value=0.1,
                    max_value=30.0,
                    step=0.1,
                    key="electric_rate",
                    help=HELP["electric_rate"],
                )
                st.number_input(
                    "Machine battery capacity (kWh)",
                    min_value=1.0,
                    max_value=500.0,
                    step=1.0,
                    key="machine_battery",
                    help=HELP["battery_capacity"],
                )
                st.slider(
                    "Usable machine battery (%)",
                    50,
                    100,
                    step=1,
                    key="machine_usable_ui",
                    help=HELP["usable_battery"],
                )
                st.number_input(
                    "Charger power (kW)",
                    min_value=1.0,
                    max_value=350.0,
                    step=1.0,
                    key="charger_power",
                    help=HELP["charger_power"],
                )
                st.slider(
                    "Charging efficiency (%)",
                    50,
                    100,
                    step=1,
                    key="charging_eff_ui",
                    help=HELP["charging_eff"],
                )
            with e2:
                st.toggle(
                    "Battery storage available",
                    key="battery_storage_available",
                    help=HELP["bess"],
                )
                st.number_input(
                    "Site battery-storage capacity (kWh)",
                    min_value=0.0,
                    max_value=1000.0,
                    step=5.0,
                    key="bess_capacity",
                    help=HELP["bess_capacity"],
                    disabled=not st.session_state.battery_storage_available,
                )
                st.slider(
                    "Usable site battery (%)",
                    50,
                    100,
                    step=1,
                    key="bess_usable_ui",
                    help="Share of the site battery capacity available for normal use.",
                    disabled=not st.session_state.battery_storage_available,
                )
                st.slider(
                    "Battery-storage efficiency (%)",
                    50,
                    100,
                    step=1,
                    key="bess_eff_ui",
                    help=HELP["bess_eff"],
                    disabled=not st.session_state.battery_storage_available,
                )
                st.toggle(
                    "Overnight charging available",
                    key="overnight_charging",
                    help=HELP["overnight"],
                )
                st.toggle(
                    "Charging during breaks",
                    key="charging_during_breaks",
                    help=HELP["break_charge"],
                )

    with st.container(border=True):
        st.subheader("B4 · Grid and temporary power")
        g1, g2, g3, g4 = st.columns(4)
        with g1:
            st.selectbox(
                "Grid availability",
                ["Available", "Limited", "Unavailable"],
                key="grid_availability",
                help=HELP["grid"],
            )
        with g2:
            st.number_input(
                "Maximum grid power (kW)",
                min_value=0.0,
                max_value=1000.0,
                step=1.0,
                key="max_grid_power",
                help=HELP["grid_power"],
            )
        with g3:
            st.slider(
                "Temporary power supplied by grid (%)",
                0,
                100,
                step=5,
                key="grid_temp_share_ui",
                help=HELP["grid_share"],
            )
        with g4:
            st.toggle(
                "Smart charging available",
                key="smart_charging_available",
                help=HELP["smart"],
            )
            st.slider(
                "Charging in lower-carbon periods (%)",
                0,
                100,
                step=5,
                key="lower_carbon_share_ui",
                help=HELP["low_carbon_share"],
                disabled=not st.session_state.smart_charging_available,
            )

    with st.expander("B5 · Advanced carbon and cost settings"):
        st.caption(
            "Published carbon factors are provided as defaults. Prices and hire rates are teaching assumptions."
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            st.number_input(
                "Grid carbon factor (kgCO₂e/kWh)",
                min_value=0.0,
                max_value=1.0,
                step=0.001,
                format="%.5f",
                key="grid_factor",
                help=HELP["grid_factor"],
            )
        with c2:
            st.number_input(
                "Diesel price (£/litre)",
                min_value=0.0,
                max_value=5.0,
                step=0.05,
                format="%.2f",
                key="diesel_price",
                help="Indicative price used for the teaching cost comparison.",
            )
        with c3:
            st.number_input(
                "Electricity price (£/kWh)",
                min_value=0.0,
                max_value=2.0,
                step=0.01,
                format="%.2f",
                key="electricity_price",
                help="Indicative price used for the teaching cost comparison.",
            )
        st.slider(
            "Lower-carbon charging factor (% of normal grid factor)",
            20,
            100,
            step=5,
            key="lower_carbon_multiplier_ui",
            help="A teaching assumption for electricity used during lower-carbon charging periods.",
        )

# Apply user inputs to copies of standard strategies.
strategy_inputs = strategies.copy()
strategy_inputs.loc[strategy_inputs["Strategy_ID"] == "S1", "Plant_Diesel_L_per_active_h"] = st.session_state.diesel_plant_rate
strategy_inputs.loc[strategy_inputs["Strategy_ID"] == "S1", "Diesel_Idle_Fuel_Fraction"] = st.session_state.diesel_idle_fraction_ui / 100
strategy_inputs.loc[strategy_inputs["Strategy_ID"] == "S1", "Generator_Diesel_L_per_kWh"] = st.session_state.generator_rate
strategy_inputs.loc[strategy_inputs["Strategy_ID"] == "S2", "Generator_Diesel_L_per_kWh"] = st.session_state.efficient_generator_rate
strategy_inputs.loc[strategy_inputs["Strategy_ID"].isin(["S3", "S4"]), "Plant_Electricity_kWh_per_active_h"] = st.session_state.electric_rate

site_inputs = {
    **selected_preset(),
    "Working_Days": st.session_state.working_days,
    "Shift_Hours": st.session_state.shift_hours,
    "Idle_Percent": st.session_state.idle_percent_ui / 100,
    "Planned_Charging_Hours": st.session_state.planned_charging_hours,
    "Temporary_Power_kWh_per_day": st.session_state.temporary_power,
    "Grid_Availability": st.session_state.grid_availability,
    "Max_Grid_Power_kW": st.session_state.max_grid_power,
    "Overnight_Charging_Available": st.session_state.overnight_charging,
    "Charging_During_Breaks": st.session_state.charging_during_breaks,
    "Battery_Storage_Available": st.session_state.battery_storage_available,
    "Diesel_Backup_Available": st.session_state.diesel_backup_available,
    "Grid_Temporary_Power_Share": st.session_state.grid_temp_share_ui / 100,
    "Smart_Charging_Available": st.session_state.smart_charging_available,
    "Lower_Carbon_Charging_Share": st.session_state.lower_carbon_share_ui / 100,
    "Grid_Carbon_kgCO2e_per_kWh": st.session_state.grid_factor,
    "Diesel_Price_GBP_per_L": st.session_state.diesel_price,
    "Electricity_Price_GBP_per_kWh": st.session_state.electricity_price,
    "Machine_Battery_Capacity_kWh": st.session_state.machine_battery,
    "Machine_Usable_Battery_Fraction": st.session_state.machine_usable_ui / 100,
    "Charger_Power_kW": st.session_state.charger_power,
    "Charging_Efficiency": st.session_state.charging_eff_ui / 100,
    "BESS_Capacity_kWh": st.session_state.bess_capacity,
    "BESS_Usable_Fraction": st.session_state.bess_usable_ui / 100,
    "BESS_Roundtrip_Efficiency": st.session_state.bess_eff_ui / 100,
    "Lower_Carbon_Grid_Multiplier": st.session_state.lower_carbon_multiplier_ui / 100,
}

# =====================================================================
# SECTION C
# =====================================================================
with section_c:
    st.header("C — Test the net-zero options")
    st.write(
        "The four standard strategies are connected packages within one aspect of net-zero innovation: "
        "decarbonising construction-site plant and temporary power."
    )

    strategy_rows = [strategies.iloc[i] for i in range(4)]
    top_left, top_right = st.columns(2)
    bottom_left, bottom_right = st.columns(2)
    for card_container, row in zip(
        [top_left, top_right, bottom_left, bottom_right], strategy_rows
    ):
        with card_container:
            with st.container(border=True):
                st.subheader(f"{row['Strategy_ID']} · {row['Short_Name']}")
                st.write(row["Description"])
                st.caption(f"Main risk: {row['Key_Risk']}")

    with st.expander("Build your own site-energy strategy"):
        st.toggle(
            "Include a custom strategy in the comparison",
            key="include_custom",
            help="Adds a fifth option based on the switches below.",
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            st.toggle("Reduce idling", key="custom_reduce_idling", help=HELP["idling"])
            st.toggle("Use electric plant", key="custom_electric", help="Replaces the diesel plant with battery-electric plant.")
        with c2:
            st.toggle("Use grid temporary power", key="custom_grid_temp", help="Uses grid electricity for site cabins, lighting and tools where possible.")
            st.toggle("Add battery storage", key="custom_bess", help=HELP["bess"])
        with c3:
            st.toggle("Use smart charging", key="custom_smart", help=HELP["smart"])
            st.toggle("Allow diesel backup", key="custom_backup", help=HELP["backup"])

        if st.session_state.include_custom:
            st.success("The custom package will appear in Section D with the four standard strategies.")

custom_strategy = None
if st.session_state.include_custom:
    custom_strategy = build_custom_strategy(
        use_electric_plant=st.session_state.custom_electric,
        reduce_idling=st.session_state.custom_reduce_idling,
        use_grid_temporary_power=st.session_state.custom_grid_temp,
        use_bess=st.session_state.custom_bess,
        use_smart_charging=st.session_state.custom_smart,
        allow_diesel_backup=st.session_state.custom_backup,
        defaults=defaults,
    )

results = calculate_scenarios(
    site_inputs,
    strategy_inputs,
    factors,
    defaults,
    custom_strategy=custom_strategy,
)

# =====================================================================
# SECTION D
# =====================================================================
with section_d:
    st.header("D — Compare results and make a decision")
    st.caption(
        "The app does not produce one overall suitability score. It presents separate evidence so the apprentice must make and defend the recommendation."
    )

    boundary = st.radio(
        "Carbon boundary",
        ["Operational carbon", "Expanded energy carbon"],
        horizontal=True,
        help=(
            "Operational carbon includes direct diesel and grid electricity. "
            "Expanded energy carbon also includes upstream diesel, electricity transmission "
            "and upstream electricity emissions."
        ),
    )
    if boundary == "Operational carbon":
        carbon_field = "Operational_CO2e_kg"
        reduction_field = "Operational_Reduction_vs_Baseline"
        carbon_label_field = "Operational_Carbon_Performance"
    else:
        carbon_field = "Expanded_Energy_CO2e_kg"
        reduction_field = "Expanded_Reduction_vs_Baseline"
        carbon_label_field = "Expanded_Carbon_Performance"

    complete_results = results[results["Carbon_Result_Valid"]].copy()
    raw_lowest = results.sort_values(carbon_field).iloc[0]
    lowest_complete = (
        complete_results.sort_values(carbon_field).iloc[0]
        if not complete_results.empty
        else raw_lowest
    )

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric(
        "Lowest complete carbon result",
        f"{lowest_complete[carbon_field]:,.0f} kgCO₂e",
        str(lowest_complete["Short_Name"]),
        help="Only strategies supplying the full required energy are eligible for this headline comparison.",
    )
    k2.metric(
        "Carbon reduction from baseline",
        f"{lowest_complete[reduction_field]:.0%}",
        str(lowest_complete[carbon_label_field]),
    )
    k3.metric("Indicative total cost", f"£{lowest_complete['Total_Cost_GBP']:,.0f}")
    k4.metric("Energy not supplied", f"{lowest_complete['Energy_Unserved_kWh_per_day']:.1f} kWh/day")
    k5.metric(
        "Cost difference from diesel baseline",
        f"£{lowest_complete['Cost_Difference_vs_Baseline_GBP']:+,.0f}",
    )

    st.markdown("#### Decision evidence for the lowest complete-carbon strategy")
    d1, d2, d3, d4 = st.columns(4)
    with d1:
        decision_card("Energy supply status", lowest_complete["Energy_Supply_Status"])
    with d2:
        decision_card("Site compatibility", lowest_complete["Site_Compatibility"])
    with d3:
        decision_card(
            "Local environmental performance",
            lowest_complete["Local_Environmental_Performance"],
        )
    with d4:
        decision_card("Delivery risk", lowest_complete["Delivery_Risk"])

    if not bool(raw_lowest["Carbon_Result_Valid"]):
        st.warning(
            f"The numerically lowest carbon bar is **{raw_lowest['Short_Name']}**, but its carbon result is incomplete. "
            f"{raw_lowest['Carbon_Validity_Note']} "
            f"The lowest complete carbon result is **{lowest_complete['Short_Name']}**."
        )
    else:
        st.info(
            "Carbon performance is presented first because this is a net-zero decision. Energy supply, site compatibility, "
            "local environmental effects, delivery risk and cost must then be checked before making the recommendation."
        )

    # Full-width charts are used deliberately. Two side-by-side Plotly charts
    # become too narrow on phones, especially when a legend is present.
    carbon_plot_data = results.copy()
    carbon_plot_data["Carbon status"] = carbon_plot_data[
        "Carbon_Comparison_Status"
    ].replace(
        {
            "Complete result": "Complete",
            "Incomplete – recharge cycle unresolved": "Incomplete recharge",
            "Incomplete - recharge cycle unresolved": "Incomplete recharge",
            "Incomplete – energy not supplied": "Incomplete supply",
            "Incomplete - energy not supplied": "Incomplete supply",
        }
    )
    fig_carbon = px.bar(
        carbon_plot_data,
        x="Short_Name",
        y=carbon_field,
        color="Carbon status",
        text_auto=".0f",
        hover_data={
            "Energy_Unserved_kWh_per_day": ":.1f",
            reduction_field: ":.0%",
        },
        labels={
            "Short_Name": "Strategy",
            carbon_field: "Carbon (kgCO₂e)",
            "Carbon status": "Carbon-result status",
        },
        title=f"{boundary} by strategy",
    )
    make_plot_mobile_friendly(fig_carbon, height=520, legend=True, tick_angle=-25)
    show_plot(fig_carbon)
    st.caption(
        "An incomplete result is not a valid low-carbon comparison because required energy is unmet or the repeated recharge cycle is unresolved."
    )

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
    make_plot_mobile_friendly(fig_cost, height=500, legend=False, tick_angle=-25)
    show_plot(fig_cost)

    tradeoff_data = results.copy()
    tradeoff_data["Energy supply"] = tradeoff_data["Energy_Supply_Status"].replace(
        {
            "All demand supplied": "Full supply",
            "All demand supplied using diesel backup": "Full supply + diesel backup",
            "Daily demand supplied; recharge cycle incomplete": "Recharge cycle incomplete",
            "Demand partly unmet": "Partial shortfall",
            "Demand cannot be supplied": "Demand not supplied",
        }
    )
    tradeoff = px.scatter(
        tradeoff_data,
        x="Total_Cost_GBP",
        y=carbon_field,
        size="Productivity_Index",
        color="Energy supply",
        text="Short_Name",
        hover_name="Strategy",
        hover_data={
            reduction_field: ":.0%",
            "Site_Compatibility": True,
            "Delivery_Risk": True,
            "Calculated_Downtime_h_per_day": ":.2f",
            "Energy_Unserved_kWh_per_day": ":.1f",
        },
        labels={
            "Total_Cost_GBP": "Indicative total cost (£)",
            carbon_field: "Carbon (kgCO₂e)",
            "Energy supply": "Energy supply status",
        },
        title="Carbon–cost–productivity trade-off (colour = energy supply)",
    )
    tradeoff.update_traces(textposition="top center", cliponaxis=False)
    make_plot_mobile_friendly(tradeoff, height=570, legend=True, tick_angle=0)
    show_plot(tradeoff)

    electric_rows = results[results["Uses_Electric_Plant"]].copy()
    if not electric_rows.empty:
        st.subheader("Electric-energy balance")
        st.caption(
            "Each strategy has two columns: required demand and actual supplied energy. "
            "Only real energy sources are stacked in the actual-supply column. If supply is insufficient, "
            "the bar remains below demand and the shortfall is shown in red. Equal-height columns mean that demand is fully supplied."
        )

        plant_balance, plant_summary = build_demand_supply_chart(
            electric_rows,
            components={
                "Machine_Battery_Supply_kWh_per_day": "Machine battery",
                "Planned_Charge_Supply_kWh_per_day": "Planned break charging",
                "Additional_Charging_Supply_kWh_per_day": "Additional charging during work",
                "BESS_to_Plant_kWh_per_day": "Site battery to plant",
                "Backup_to_Plant_kWh_per_day": "Diesel backup to plant",
            },
            demand_field="Plant_Energy_Demand_kWh_per_day",
            unserved_field="Plant_Energy_Unserved_kWh_per_day",
            title="Electric-plant demand versus actual supply",
            y_axis_title="Plant energy (kWh/day)",
        )
        st.markdown("#### Electric-plant demand versus actual supply")
        show_plot(plant_balance)
        st.caption(
            "This comparison asks whether the electric machine receives enough energy to complete its working shift."
        )
        st.dataframe(
            plant_summary.style.format(
                {
                    "Required demand (kWh/day)": "{:.2f}",
                    "Actual supply (kWh/day)": "{:.2f}",
                    "Shortfall (kWh/day)": "{:.2f}",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

        temporary_balance, temporary_summary = build_demand_supply_chart(
            electric_rows,
            components={
                "Direct_Grid_Temporary_kWh_per_day": "Direct grid supply",
                "BESS_to_Temporary_kWh_per_day": "Site battery supply",
                "Backup_to_Temporary_kWh_per_day": "Diesel-generator backup",
            },
            demand_field="Temporary_Power_Demand_kWh_per_day",
            unserved_field="Temporary_Energy_Unserved_kWh_per_day",
            title="Temporary-power demand versus actual supply",
            y_axis_title="Temporary power (kWh/day)",
        )
        st.markdown("#### Temporary-power demand versus actual supply")
        show_plot(temporary_balance)
        st.caption(
            "This comparison asks whether cabins, lighting, tools and temporary equipment receive the required energy."
        )
        st.dataframe(
            temporary_summary.style.format(
                {
                    "Required demand (kWh/day)": "{:.2f}",
                    "Actual supply (kWh/day)": "{:.2f}",
                    "Shortfall (kWh/day)": "{:.2f}",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

        electric_downtime = electric_rows[
            ["Short_Name", "Calculated_Downtime_h_per_day"]
        ].copy()
        if electric_downtime["Calculated_Downtime_h_per_day"].max() > 0.001:
            fig_down = px.bar(
                electric_downtime,
                x="Short_Name",
                y="Calculated_Downtime_h_per_day",
                text_auto=".2f",
                labels={
                    "Short_Name": "Electric strategy",
                    "Calculated_Downtime_h_per_day": "Plant charging downtime (h/day)",
                },
                title="Calculated plant charging downtime",
            )
            make_plot_mobile_friendly(fig_down, height=470, legend=False, tick_angle=-20)
            show_plot(fig_down)
        else:
            st.info(
                "No same-shift plant charging downtime is calculated. This does not prove that all temporary-power "
                "demand is supplied or that overnight recharging is adequate."
            )

        cobenefit = results[
            ["Short_Name", "Exhaust_NOx_Index", "Exhaust_PM_Index", "Noise_Index"]
        ].melt(
            id_vars="Short_Name",
            var_name="Indicator",
            value_name="Relative index",
        )
        cobenefit["Indicator"] = cobenefit["Indicator"].replace(
            {
                "Exhaust_NOx_Index": "Exhaust NOx",
                "Exhaust_PM_Index": "Exhaust PM",
                "Noise_Index": "Noise",
            }
        )
        fig_cobenefit = px.bar(
            cobenefit,
            x="Short_Name",
            y="Relative index",
            color="Indicator",
            barmode="group",
            title="Relative exhaust and noise indicators",
            labels={"Short_Name": "Strategy"},
        )
        make_plot_mobile_friendly(fig_cobenefit, height=540, legend=True, tick_angle=-25)
        show_plot(fig_cobenefit)
        st.caption(
            "Lower index = lower point-of-use exhaust or noise impact. These are comparative teaching indicators, "
            "not measured exposure or acoustic results."
        )

    st.subheader("Decision evidence")
    st.caption(
        "Carbon is shown first. The other dimensions explain whether the carbon reduction represents a complete, site-compatible and deliverable strategy."
    )

    for _, row in results.iterrows():
        with st.expander(
            f"{row['Short_Name']} — {row[carbon_label_field]} | {row['Energy_Supply_Status']}"
        ):
            if not bool(row["Carbon_Result_Valid"]):
                st.warning(row["Carbon_Validity_Note"])
            else:
                st.success(row["Carbon_Validity_Note"])

            a, b, c, d = st.columns(4)
            a.metric("Carbon", f"{row[carbon_field]:,.0f} kgCO₂e")
            b.metric("Reduction from diesel baseline", f"{row[reduction_field]:.0%}")
            c.metric("Indicative cost", f"£{row['Total_Cost_GBP']:,.0f}")
            d.metric("Cost difference from baseline", f"£{row['Cost_Difference_vs_Baseline_GBP']:+,.0f}")

            q1, q2, q3 = st.columns(3)
            with q1:
                decision_card("Carbon performance", row[carbon_label_field])
            with q2:
                decision_card("Energy supply status", row["Energy_Supply_Status"])
            with q3:
                decision_card("Site compatibility", row["Site_Compatibility"])

            q4, q5 = st.columns(2)
            with q4:
                decision_card(
                    "Local environmental performance",
                    row["Local_Environmental_Performance"],
                )
            with q5:
                decision_card("Delivery risk", row["Delivery_Risk"])

            st.write("**Energy evidence:**", row["Energy_Supply_Note"])
            st.write("**Site evidence:**", row["Site_Compatibility_Note"])
            st.write("**Local environmental evidence:**", row["Local_Environmental_Note"])
            st.write("**Delivery evidence:**", row["Delivery_Risk_Note"])
            st.write("**Key implementation condition:**", row["Key_Implementation_Condition"])

            if bool(row["Uses_Electric_Plant"]):
                t1, t2, t3, t4 = st.columns(4)
                t1.metric("Plant demand", f"{row['Plant_Energy_Demand_kWh_per_day']:.1f} kWh/day")
                t2.metric("Machine battery supply", f"{row['Machine_Battery_Supply_kWh_per_day']:.1f} kWh/day")
                t3.metric("Plant charging downtime", f"{row['Calculated_Downtime_h_per_day']:.2f} h/day")
                t4.metric("Energy not supplied", f"{row['Energy_Unserved_kWh_per_day']:.1f} kWh/day")
                t5, t6, t7, t8 = st.columns(4)
                t5.metric("Temporary power from grid", f"{row['Direct_Grid_Temporary_kWh_per_day']:.1f} kWh/day")
                t6.metric("Site battery used", f"{row['BESS_Energy_Used_kWh_per_day']:.1f} kWh/day")
                t7.metric("Diesel backup share", f"{row['Backup_Energy_Share']:.0%}")
                t8.metric("Required overnight recharge", f"{row['Required_Overnight_Recharge_h']:.1f} h")
                st.caption(
                    f"Battery-equivalent plant demand: {row['Battery_Equivalent_Cycles_per_day']:.1f} cycles/day. "
                    f"Effective charger power: {row['Effective_Charger_Power_kW']:.1f} kW."
                )
            else:
                t1, t2, t3, t4 = st.columns(4)
                t1.metric("Plant diesel", f"{row['Plant_Diesel_L_per_day']:.1f} L/day")
                t2.metric("Generator diesel", f"{row['Temporary_Power_Diesel_L_per_day']:.1f} L/day")
                t3.metric("Idling time", f"{row['Idle_Hours_per_day']:.1f} h/day")
                t4.metric("Productivity index", f"{row['Productivity_Index']:.0f}")
                st.caption(
                    "Battery cycles, charging downtime and overnight recharge are not applicable to a diesel strategy. "
                    "The model does not calculate mechanical breakdown, maintenance or refuelling delays."
                )

    evidence_records = []
    for _, row in results.iterrows():
        evidence_records.append(
            {
                "Strategy": row["Short_Name"],
                "Carbon (kgCO₂e)": round(float(row[carbon_field]), 1),
                "Carbon reduction": f"{row[reduction_field]:.0%}",
                "Carbon performance": row[carbon_label_field],
                "Carbon result": row["Carbon_Comparison_Status"],
                "Energy supply": row["Energy_Supply_Status"],
                "Site compatibility": row["Site_Compatibility"],
                "Local environment": row["Local_Environmental_Performance"],
                "Delivery risk": row["Delivery_Risk"],
                "Indicative cost (£)": round(float(row["Total_Cost_GBP"]), 0),
                "Cost vs baseline (£)": round(float(row["Cost_Difference_vs_Baseline_GBP"]), 0),
                "Key condition": row["Key_Implementation_Condition"],
            }
        )
    st.dataframe(pd.DataFrame(evidence_records), use_container_width=True, hide_index=True)

    st.subheader("Apprentice recommendation")
    st.write(
        "Use the evidence to recommend a strategy. Give carbon reduction first, then confirm complete energy supply and explain site, local-environment, delivery and cost trade-offs."
    )
    r1, r2 = st.columns(2)
    with r1:
        st.text_input("My recommended strategy is", placeholder="Choose a strategy after reviewing all decision evidence")
        st.text_area(
            "Main carbon and energy evidence",
            placeholder="Carbon reduction, carbon-result completeness and energy-supply evidence",
        )
    with r2:
        st.text_area(
            "Main site or delivery risk",
            placeholder="Site compatibility, local exhaust/noise, grid, charging, downtime or programme risk",
        )
        st.text_area(
            "Required implementation condition",
            placeholder="What must be confirmed or provided before using this strategy?",
        )

    st.download_button(
        "Download current scenario results",
        results.to_csv(index=False).encode("utf-8"),
        file_name="low_carbon_site_results_v2_2.csv",
        mime="text/csv",
    )

# =====================================================================
# SECTION E
# =====================================================================
with section_e:
    st.header("E — How to use the app")

    st.subheader("Quick-start workflow")
    st.markdown(
        """
1. **Select a site context** in Section A and load the teaching defaults.
2. **Review the site and energy assumptions** in Section B. Change only the variables relevant to the decision.
3. **Review the strategy packages** in Section C and optionally build a custom strategy.
4. In Section D, begin with **carbon performance and carbon-result completeness**.
5. Confirm **energy supply**, then examine **site compatibility**, **local environmental performance**, **delivery risk** and **indicative cost**.
6. Record and defend an apprentice recommendation. The app does not select one overall best option.
"""
    )
    st.warning(
        "A very low carbon value is not a valid result when required plant or temporary-power energy is left unserved."
    )

    st.subheader("The five decision dimensions")
    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("**1 · Carbon performance**")
            st.write(
                "Shows total carbon, percentage reduction from conventional diesel and whether the result represents the complete required energy service."
            )
        with st.container(border=True):
            st.markdown("**2 · Energy supply status**")
            st.write(
                "Shows whether all plant and temporary-power demand is supplied and whether diesel backup is required."
            )
        with st.container(border=True):
            st.markdown("**3 · Local environmental performance**")
            st.write(
                "Compares relative point-of-use exhaust NOx, exhaust PM and noise indicators. Lower indices are better."
            )
    with c2:
        with st.container(border=True):
            st.markdown("**4 · Site compatibility and delivery risk**")
            st.write(
                "Separates the fit with community, noise and infrastructure conditions from energy-related programme risk."
            )
        with st.container(border=True):
            st.markdown("**5 · Indicative cost**")
            st.write(
                "Shows total teaching cost and the difference from conventional diesel. The cheapest option is not automatically preferred."
            )

    st.subheader("How to interpret the charts")
    st.markdown(
        """
- **Carbon chart:** compares calculated emissions. Bars marked incomplete should not be treated as valid low-carbon solutions.
- **Cost chart:** compares indicative fuel, electricity, plant-hire and power-system costs.
- **Trade-off chart:** places cost against carbon; bubble size represents productivity and colour represents energy supply status.
- **Electric-plant demand versus actual supply:** the demand column is shown beside a stacked supply column. A shorter supply column and red label show an energy shortfall.
- **Temporary-power demand versus actual supply:** uses the same demand-versus-supply design for cabins, lighting, tools and temporary equipment.
- **Plant charging downtime:** appears only when extra during-shift charging interrupts plant operation.
- **Relative exhaust and noise indicators:** lower values indicate lower point-of-use impacts; they are not measured exposure or acoustic results.
"""
    )

    st.subheader("Key definitions")
    glossary = pd.DataFrame(
        [
            ["Idling", "The machine is running but is not doing useful work."],
            ["Grid", "The public electricity network used to power the site and charge equipment."],
            ["Plant charging downtime", "Time when electric plant must stop for additional charging during the shift."],
            ["Machine battery", "The battery installed in or allocated to the electric construction plant."],
            ["Site battery", "A separate temporary battery system supporting plant charging or site power."],
            ["Temporary site power", "Energy used for cabins, lighting, tools and temporary equipment."],
            ["Smart charging", "Moving charging to periods with available, cheaper or lower-carbon electricity."],
            ["Incomplete carbon result", "A carbon result calculated while some required energy demand remains unserved."],
            ["Site compatibility", "How well a strategy matches local community, noise and infrastructure conditions."],
            ["Delivery risk", "Energy-related risk to programme delivery from charging, grid limits, backup or unmet demand."],
        ],
        columns=["Term", "Meaning"],
    )
    st.dataframe(glossary, use_container_width=True, hide_index=True)

# =====================================================================
# SECTION F
# =====================================================================
with section_f:
    st.header("F — Method and calculation boundaries")

    st.subheader("F1 · Carbon boundaries")
    boundary_left, boundary_right = st.columns(2)
    with boundary_left:
        with st.container(border=True):
            st.markdown("**Operational carbon**")
            st.markdown(
                """
Includes:
- direct carbon from diesel used by plant and generators;
- carbon associated with all grid electricity used for machine charging, temporary power and site-battery recharging.
"""
            )
    with boundary_right:
        with st.container(border=True):
            st.markdown("**Expanded energy carbon**")
            st.markdown(
                """
Includes the operational boundary plus:
- upstream diesel emissions;
- electricity transmission and distribution;
- upstream electricity emissions.
"""
            )
    st.info(
        "Neither boundary is a full whole-life carbon assessment. Plant manufacture, battery manufacture, "
        "construction materials and end-of-life impacts are excluded."
    )

    st.subheader("F2 · Working-time and energy calculations")
    st.markdown("**Working time**")
    st.latex(r"h_{active}=h_{shift}(1-f_{idle})")
    st.latex(r"h_{idle}=h_{shift}f_{idle}")

    st.markdown("**Electric-plant demand**")
    st.latex(r"E_{plant}=h_{active}r_{electric}+h_{idle}r_{electric}f_{electric\ idle}")

    st.markdown("**Usable battery and planned charging**")
    st.latex(r"E_{machine,usable}=C_{machine}f_{usable}")
    st.latex(r"E_{planned}=P_{charger,effective}t_{planned}\eta_{charge}")
    st.caption(
        "Effective charger power is the lower of the charger rating and the grid power remaining after direct temporary-power demand. "
        "Planned charging supply is capped at the remaining plant-energy demand."
    )

    st.markdown("**Plant charging downtime**")
    st.latex(r"t_{downtime}=\frac{E_{plant\ gap}}{P_{charger,effective}\eta_{charge}}")
    st.caption(
        "Downtime is calculated only when the machine must stop for additional charging outside planned breaks and no other supply covers the gap."
    )

    st.markdown("**Temporary site power**")
    st.latex(r"E_{temporary}=E_{grid,direct}+E_{site\ battery}+E_{diesel\ backup}+E_{unserved}")

    st.markdown("**Off-shift recharge**")
    st.latex(r"t_{offshift}=\frac{E_{machine\ battery\ recharge}/\eta_{charge}+E_{BESS\ output}/\eta_{BESS}}{P_{grid,max}}")

    st.subheader("F3 · Carbon calculations")
    st.markdown("**Diesel strategies**")
    st.latex(r"L_{plant,day}=h_{active}r_{diesel}+h_{idle}f_{idle\ control}r_{diesel}f_{idle\ fuel}")
    st.latex(r"L_{generator,day}=E_{temporary}r_{generator}")
    st.latex(r"L_{diesel,total}=N_{days}(L_{plant,day}+L_{generator,day})")
    st.latex(r"CO_{2e,operational}=L_{diesel,total}\,EF_{diesel,direct}")
    st.latex(r"CO_{2e,expanded}=L_{diesel,total}(EF_{diesel,direct}+EF_{diesel,upstream})")

    st.markdown("**Electric strategies: grid input and backup fuel**")
    st.latex(r"E_{grid,day}=\frac{E_{machine\ supply}}{\eta_{charge}}+E_{grid,temporary}+\frac{E_{BESS\ output}}{\eta_{BESS}}")
    st.latex(r"L_{backup,day}=\left(E_{backup,temporary}+\frac{E_{backup,plant}}{\eta_{charge}}\right)r_{generator}")
    st.caption(
        "Machine supply includes energy drawn from the machine battery, planned charging and any additional direct charging. "
        "Site-battery output is converted back to required grid input using the site-battery round-trip efficiency."
    )

    st.markdown("**Smart-charging adjustment**")
    st.latex(r"EF_{grid,effective}=EF_{grid,direct}\left[(1-s_{smart})+s_{smart}m_{low\ carbon}\right]")
    st.caption(
        "The lower-carbon adjustment applies only when both the strategy uses smart charging and the selected site makes it available."
    )

    st.markdown("**Electric operational and expanded energy carbon**")
    st.latex(r"CO_{2e,operational}=E_{grid,total}EF_{grid,effective}+L_{backup,total}EF_{diesel,direct}")
    st.latex(r"CO_{2e,expanded}=E_{grid,total}(EF_{grid,effective}+EF_{grid,T\&D}+EF_{grid,upstream})+L_{backup,total}(EF_{diesel,direct}+EF_{diesel,upstream})")
    st.warning(
        "A carbon result is marked incomplete when required energy remains unserved or the repeated off-shift recharge cycle cannot be completed. "
        "This prevents an under-supplied strategy from appearing artificially low-carbon."
    )

    st.subheader("F4 · Cost calculations")
    st.markdown("**Energy cost**")
    st.latex(r"C_{energy}=E_{grid,total}p_{electricity}+L_{diesel,total}p_{diesel}")
    st.caption(
        "For an electric strategy, diesel litres refer only to diesel backup. For a diesel strategy, they include plant and generator fuel."
    )

    st.markdown("**Plant and power-system hire**")
    st.latex(r"C_{hire}=N_{days}(C_{plant,day}+C_{power\ system,day})")

    st.markdown("**Indicative total cost**")
    st.latex(r"C_{total}=C_{energy}+C_{hire}")
    st.info(
        "The cost is an indicative teaching comparison. It excludes labour, grid-connection installation, maintenance, finance, overheads and other project costs unless they are explicitly represented in the input assumptions."
    )

    st.subheader("F5 · Decision-evidence rules")
    st.markdown(
        "The model deliberately avoids one overall label such as ‘suitable’. Each dimension answers a different question."
    )

    st.markdown("**Carbon performance relative to conventional diesel**")
    carbon_rules = pd.DataFrame(
        [
            ["Baseline / high carbon", "Less than 5% reduction or the conventional-diesel baseline."],
            ["Limited carbon reduction", "5% to below 30% reduction."],
            ["Moderate carbon reduction", "30% to below 60% reduction."],
            ["Substantial carbon reduction", "60% to below 90% reduction."],
            ["Very substantial carbon reduction", "90% or greater reduction."],
            ["Incomplete carbon result", "Required energy is unmet or the repeated battery-recharge cycle is unresolved; the result is not a complete comparison."],
        ],
        columns=["Label", "Meaning"],
    )
    st.dataframe(carbon_rules, use_container_width=True, hide_index=True)

    st.markdown("**Energy supply status**")
    energy_rules = pd.DataFrame(
        [
            ["All demand supplied", "All plant and temporary-power demand is supplied without diesel backup."],
            ["All demand supplied using diesel backup", "All demand is supplied, but backup diesel contributes energy and carbon."],
            ["Daily demand supplied; recharge cycle incomplete", "The working day can be supplied, but the batteries cannot be restored reliably for repeated daily operation."],
            ["Demand partly unmet", "Some, but not all, required demand is supplied."],
            ["Demand cannot be supplied", "The selected system supplies essentially none of the required demand."],
        ],
        columns=["Status", "Meaning"],
    )
    st.dataframe(energy_rules, use_container_width=True, hide_index=True)

    st.markdown("**Site compatibility, local environment and delivery risk**")
    decision_rules = pd.DataFrame(
        [
            ["Site compatibility", "Good site fit / Site fit with conditions / Poor site fit", "Community and noise sensitivity, grid availability, battery access, smart-charging access and unmet demand."],
            ["Local environmental performance", "Strong / Moderate / Poor", "Relative point-of-use exhaust NOx, exhaust PM and noise indicators."],
            ["Delivery risk", "Low / Moderate / High", "Unserved energy, charging downtime, diesel-backup dependence, grid limits, battery cycles and off-shift recharge."],
        ],
        columns=["Dimension", "Labels", "Evidence considered"],
    )
    st.dataframe(decision_rules, use_container_width=True, hide_index=True)

    st.subheader("F6 · Data sources and teaching assumptions")
    st.markdown(
        """
- Published carbon factors are used where identified in the source table.
- Plant energy, fuel use, hire cost, productivity and local-environment indices are teaching assumptions informed by the cited specifications.
- Users should replace these defaults with contractor quotations, supplier data and site measurements for professional project appraisal.
"""
    )

    st.markdown("**Emission factors**")
    st.dataframe(
        factors,
        use_container_width=True,
        hide_index=True,
        column_config={"Primary_Source_URL": st.column_config.LinkColumn("Primary source")},
    )

    st.markdown("**Plant specifications**")
    st.dataframe(
        plant_specs,
        use_container_width=True,
        hide_index=True,
        column_config={"Source_URL": st.column_config.LinkColumn("Source")},
    )

    st.subheader("F7 · Limitations")
    st.markdown(
        """
- This is an educational decision-support tool, not a certified whole-life carbon assessment.
- Machine and battery manufacture and end-of-life impacts are outside the model.
- Costs, fuel use, productivity and equipment availability are teaching assumptions.
- Exhaust and noise indices are comparative indicators, not exposure or acoustic models.
- The model does not calculate mechanical breakdown, maintenance, refuelling delays or detailed safety risk.
- Site compatibility and delivery-risk labels are transparent teaching rules, not regulatory approvals.
- Grid capacity, battery logistics and charging arrangements require project-specific engineering verification.
"""
    )

st.caption(
    "Educational prototype for a Level 5 civil engineering apprenticeship session. "
    "The dashboard supports professional judgement; it does not replace it."
)
