
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"


def load_tables() -> dict[str, pd.DataFrame]:
    return {
        "sites": pd.read_csv(DATA_DIR / "scenario_presets.csv"),
        "strategies": pd.read_csv(DATA_DIR / "strategy_assumptions.csv"),
        "factors": pd.read_csv(DATA_DIR / "emission_factors.csv"),
        "plant_specs": pd.read_csv(DATA_DIR / "plant_specs.csv"),
        "tableau_wide": pd.read_csv(DATA_DIR / "tableau_wide.csv"),
    }


def factor_value(factors: pd.DataFrame, factor_id: str) -> float:
    match = factors.loc[factors["Factor_ID"] == factor_id, "Value"]
    if match.empty:
        raise KeyError(f"Missing factor: {factor_id}")
    return float(match.iloc[0])


def plant_spec_value(plant_specs: pd.DataFrame, spec_id: str) -> float:
    match = plant_specs.loc[plant_specs["Spec_ID"] == spec_id, "Value"]
    if match.empty:
        raise KeyError(f"Missing plant specification: {spec_id}")
    return float(match.iloc[0])


def calculate_scenarios(
    site: dict[str, Any],
    strategies: pd.DataFrame,
    factors: pd.DataFrame,
    plant_specs: pd.DataFrame,
) -> pd.DataFrame:
    """Apply the same model logic used in the Tableau workbook.

    Operational boundary:
      - diesel combustion (EF1)
      - location-based grid electricity generation (EF3)

    Expanded energy boundary:
      - operational boundary
      - diesel well-to-tank (EF2)
      - electricity transmission/distribution (EF4)
      - electricity well-to-tank generation (EF5)

    Machine and battery embodied carbon remain outside this prototype.
    """

    ef_diesel_direct = factor_value(factors, "EF1")
    ef_diesel_wtt = factor_value(factors, "EF2")
    ef_grid_generation_default = factor_value(factors, "EF3")
    ef_grid_td = factor_value(factors, "EF4")
    ef_grid_wtt = factor_value(factors, "EF5")
    battery_capacity_kwh = plant_spec_value(plant_specs, "PS1")

    working_days = float(site["Working_Days"])
    shift_hours = float(site["Shift_Hours"])
    idle_fraction = float(site["Idle_Percent"])
    temp_power_kwh_day = float(site["Temporary_Power_kWh_per_day"])
    grid_factor = float(site.get("Grid_Carbon_kgCO2e_per_kWh", ef_grid_generation_default))
    diesel_price = float(site["Diesel_Price_GBP_per_L"])
    electricity_price = float(site["Electricity_Price_GBP_per_kWh"])

    active_hours_total = working_days * shift_hours * (1.0 - idle_fraction)
    idle_hours_total = working_days * shift_hours * idle_fraction

    rows: list[dict[str, Any]] = []

    for _, s in strategies.iterrows():
        diesel_rate = float(s["Plant_Diesel_L_per_active_h"])
        electricity_rate = float(s["Plant_Electricity_kWh_per_active_h"])
        idle_energy_fraction = float(s["Idle_Energy_Fraction"])
        generator_rate = float(s["Generator_Diesel_L_per_kWh"])
        charging_loss = float(s["Charging_Loss_Percent"])
        smart_grid_multiplier = float(s["Smart_Grid_CI_Multiplier"])
        storage_loss = float(s["Battery_Storage_Loss_Percent"])

        plant_diesel_l = (
            active_hours_total * diesel_rate
            + idle_hours_total * diesel_rate * idle_energy_fraction
        )

        temporary_power_diesel_l = (
            working_days * temp_power_kwh_day * generator_rate
        )

        plant_grid_kwh = (
            active_hours_total * electricity_rate
            + idle_hours_total * electricity_rate * idle_energy_fraction
        ) * (1.0 + charging_loss) * (1.0 + storage_loss)

        temporary_grid_kwh = (
            working_days * temp_power_kwh_day * (1.0 + storage_loss)
            if generator_rate == 0.0
            else 0.0
        )

        total_grid_kwh = plant_grid_kwh + temporary_grid_kwh
        effective_grid_factor = grid_factor * smart_grid_multiplier

        operational_co2e_kg = (
            (plant_diesel_l + temporary_power_diesel_l) * ef_diesel_direct
            + total_grid_kwh * effective_grid_factor
        )

        expanded_energy_co2e_kg = (
            (plant_diesel_l + temporary_power_diesel_l)
            * (ef_diesel_direct + ef_diesel_wtt)
            + total_grid_kwh
            * (effective_grid_factor + ef_grid_td + ef_grid_wtt)
        )

        energy_cost_gbp = (
            (plant_diesel_l + temporary_power_diesel_l) * diesel_price
            + total_grid_kwh * electricity_price
        )

        hire_and_power_cost_gbp = working_days * (
            float(s["Plant_Hire_GBP_per_day"])
            + float(s["Power_System_GBP_per_day"])
        )

        total_cost_gbp = energy_cost_gbp + hire_and_power_cost_gbp

        daily_plant_electricity_kwh = (
            plant_grid_kwh / working_days if working_days else 0.0
        )

        battery_charges_per_day = (
            max(0.0, round(daily_plant_electricity_kwh / battery_capacity_kwh + 0.499999) - 1)
            if electricity_rate > 0 and battery_capacity_kwh > 0
            else 0.0
        )

        air_quality_benefit_index = 100.0 - (
            float(s["Exhaust_NOx_Index"]) + float(s["Exhaust_PM_Index"])
        ) / 2.0
        noise_benefit_index = 100.0 - float(s["Noise_Index"])

        rows.append({
            "Context_ID": site["Context_ID"],
            "Site_Context": site["Site_Context"],
            "Strategy_ID": s["Strategy_ID"],
            "Strategy": s["Strategy"],
            "Plant_Powertrain": s["Plant_Powertrain"],
            "Working_Days": working_days,
            "Shift_Hours": shift_hours,
            "Idle_Percent": idle_fraction,
            "Grid_Availability": site["Grid_Availability"],
            "Grid_Carbon_kgCO2e_per_kWh": grid_factor,
            "Diesel_Price_GBP_per_L": diesel_price,
            "Electricity_Price_GBP_per_kWh": electricity_price,
            "Noise_Sensitivity": site["Noise_Sensitivity"],
            "Community_Sensitivity": site["Community_Sensitivity"],
            "Plant_Diesel_L": plant_diesel_l,
            "Temporary_Power_Diesel_L": temporary_power_diesel_l,
            "Grid_Electricity_kWh": total_grid_kwh,
            "Operational_CO2e_kg": operational_co2e_kg,
            "Expanded_Energy_CO2e_kg": expanded_energy_co2e_kg,
            "Energy_Cost_GBP": energy_cost_gbp,
            "Hire_and_Power_Cost_GBP": hire_and_power_cost_gbp,
            "Total_Cost_GBP": total_cost_gbp,
            "Productivity_Index": float(s["Productivity_Index"]),
            "Expected_Downtime_h_per_day": float(s["Expected_Downtime_h_per_day"]),
            "Exhaust_NOx_Index": float(s["Exhaust_NOx_Index"]),
            "Exhaust_PM_Index": float(s["Exhaust_PM_Index"]),
            "Noise_Index": float(s["Noise_Index"]),
            "Air_Quality_Benefit_Index": air_quality_benefit_index,
            "Noise_Benefit_Index": noise_benefit_index,
            "Daily_Plant_Electricity_kWh": daily_plant_electricity_kwh,
            "Battery_Charges_per_Day": battery_charges_per_day,
            "Data_Quality_Note": s["Data_Quality"],
            "Calculation_Use": s["Calculation_Use"],
            "Teaching_Note": s["Teaching_Note"],
            "Key_Risk": s["Key_Risk"],
            "Scenario_Note": f"{site['Context_Note']} | {s['Teaching_Note']}",
        })

    result = pd.DataFrame(rows)

    operational_baseline = float(
        result.loc[result["Strategy_ID"] == "S1", "Operational_CO2e_kg"].iloc[0]
    )
    expanded_baseline = float(
        result.loc[result["Strategy_ID"] == "S1", "Expanded_Energy_CO2e_kg"].iloc[0]
    )

    result["Operational_Reduction_vs_Baseline"] = (
        1.0 - result["Operational_CO2e_kg"] / operational_baseline
    )
    result["Expanded_Reduction_vs_Baseline"] = (
        1.0 - result["Expanded_Energy_CO2e_kg"] / expanded_baseline
    )

    return result


def calculate_all_presets(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    frames = []
    for _, site_row in tables["sites"].iterrows():
        frames.append(
            calculate_scenarios(
                site_row.to_dict(),
                tables["strategies"],
                tables["factors"],
                tables["plant_specs"],
            )
        )
    return pd.concat(frames, ignore_index=True)
