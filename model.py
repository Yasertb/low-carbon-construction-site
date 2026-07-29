from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y", "on"}


def load_tables() -> dict[str, pd.DataFrame]:
    return {
        "sites": pd.read_csv(DATA_DIR / "site_presets.csv"),
        "strategies": pd.read_csv(DATA_DIR / "strategy_assumptions.csv"),
        "factors": pd.read_csv(DATA_DIR / "emission_factors.csv"),
        "plant_specs": pd.read_csv(DATA_DIR / "plant_specs.csv"),
        "energy_defaults": pd.read_csv(DATA_DIR / "energy_system_defaults.csv"),
    }


def factor_value(factors: pd.DataFrame, factor_id: str) -> float:
    match = factors.loc[factors["Factor_ID"] == factor_id, "Value"]
    if match.empty:
        raise KeyError(f"Missing factor: {factor_id}")
    return float(match.iloc[0])


def default_value(defaults: pd.DataFrame, parameter: str) -> float:
    match = defaults.loc[defaults["Parameter"] == parameter, "Value"]
    if match.empty:
        raise KeyError(f"Missing energy-system default: {parameter}")
    return float(match.iloc[0])


def build_custom_strategy(
    *,
    use_electric_plant: bool,
    reduce_idling: bool,
    use_grid_temporary_power: bool,
    use_bess: bool,
    use_smart_charging: bool,
    allow_diesel_backup: bool,
    defaults: pd.DataFrame,
) -> dict[str, Any]:
    """Build a custom strategy from simple apprentice switches."""
    if use_electric_plant:
        return {
            "Strategy_ID": "SC",
            "Strategy": "Custom apprentice strategy",
            "Short_Name": "Custom strategy",
            "Plant_Powertrain": "Custom electric package",
            "Uses_Electric_Plant": True,
            "Uses_BESS": use_bess,
            "Uses_Smart_Charging": use_smart_charging,
            "Uses_Grid_Temporary_Power": use_grid_temporary_power,
            "Idle_Reduction_Factor": 1.0,
            "Plant_Diesel_L_per_active_h": 0.0,
            "Diesel_Idle_Fuel_Fraction": 0.0,
            "Generator_Diesel_L_per_kWh": default_value(defaults, "Backup_Generator_L_per_kWh"),
            "Plant_Electricity_kWh_per_active_h": 3.33,
            "Electric_Idle_Energy_Fraction": 0.05,
            "BESS_Temporary_Power_Share": 0.5 if use_bess else 0.0,
            "Plant_Hire_GBP_per_day": default_value(defaults, "Electric_Plant_Hire_GBP_day"),
            "Power_System_GBP_per_day": (
                default_value(defaults, "BESS_Power_System_Hire_GBP_day")
                if use_bess
                else default_value(defaults, "Grid_Power_System_Hire_GBP_day")
            ),
            "Productivity_Index": 98.0,
            "Exhaust_NOx_Index": 0.0,
            "Exhaust_PM_Index": 0.0,
            "Noise_Index": 52.0,
            "Description": "A user-built combination of electric plant, site power and charging options.",
            "Key_Risk": "The custom combination must be checked against grid, battery and programme limits.",
            "Data_Quality": "Teaching assumptions and user-selected options",
            "Force_Diesel_Backup": allow_diesel_backup,
        }

    return {
        "Strategy_ID": "SC",
        "Strategy": "Custom apprentice strategy",
        "Short_Name": "Custom strategy",
        "Plant_Powertrain": "Custom diesel package",
        "Uses_Electric_Plant": False,
        "Uses_BESS": False,
        "Uses_Smart_Charging": False,
        "Uses_Grid_Temporary_Power": False,
        "Idle_Reduction_Factor": 0.5 if reduce_idling else 1.0,
        "Plant_Diesel_L_per_active_h": 2.8 if reduce_idling else 3.2,
        "Diesel_Idle_Fuel_Fraction": 0.15 if reduce_idling else 0.35,
        "Generator_Diesel_L_per_kWh": 0.24 if reduce_idling else 0.30,
        "Plant_Electricity_kWh_per_active_h": 0.0,
        "Electric_Idle_Energy_Fraction": 0.0,
        "BESS_Temporary_Power_Share": 0.0,
        "Plant_Hire_GBP_per_day": (
            default_value(defaults, "Efficient_Diesel_Plant_Hire_GBP_day")
            if reduce_idling
            else default_value(defaults, "Diesel_Plant_Hire_GBP_day")
        ),
        "Power_System_GBP_per_day": (
            default_value(defaults, "Efficient_Generator_Hire_GBP_day")
            if reduce_idling
            else default_value(defaults, "Diesel_Generator_Hire_GBP_day")
        ),
        "Productivity_Index": 100.0,
        "Exhaust_NOx_Index": 35.0 if reduce_idling else 100.0,
        "Exhaust_PM_Index": 25.0 if reduce_idling else 100.0,
        "Noise_Index": 95.0 if reduce_idling else 100.0,
        "Description": "A user-built diesel strategy with optional anti-idling measures.",
        "Key_Risk": "The strategy remains dependent on diesel.",
        "Data_Quality": "Teaching assumptions and user-selected options",
        "Force_Diesel_Backup": allow_diesel_backup,
    }


def calculate_strategy(
    site: dict[str, Any],
    strategy: dict[str, Any],
    factors: pd.DataFrame,
    defaults: pd.DataFrame,
) -> dict[str, Any]:
    ef_diesel_direct = factor_value(factors, "EF1")
    ef_diesel_wtt = factor_value(factors, "EF2")
    ef_grid_direct = float(site["Grid_Carbon_kgCO2e_per_kWh"])
    ef_grid_td = factor_value(factors, "EF4")
    ef_grid_wtt = factor_value(factors, "EF5")

    days = float(site["Working_Days"])
    shift_hours = float(site["Shift_Hours"])
    idle_fraction = float(site["Idle_Percent"])
    planned_charging_hours = float(site["Planned_Charging_Hours"])
    temporary_power_day = float(site["Temporary_Power_kWh_per_day"])
    grid_status = str(site["Grid_Availability"])
    max_grid_power = max(0.0, float(site["Max_Grid_Power_kW"]))
    overnight_charging = as_bool(site["Overnight_Charging_Available"])
    charging_during_breaks = as_bool(site["Charging_During_Breaks"])
    bess_available = as_bool(site["Battery_Storage_Available"])
    site_backup_available = as_bool(site["Diesel_Backup_Available"])
    grid_temp_share = min(1.0, max(0.0, float(site["Grid_Temporary_Power_Share"])))
    smart_available = as_bool(site["Smart_Charging_Available"])
    lower_carbon_share = min(1.0, max(0.0, float(site["Lower_Carbon_Charging_Share"])))

    diesel_price = float(site["Diesel_Price_GBP_per_L"])
    electricity_price = float(site["Electricity_Price_GBP_per_kWh"])

    machine_battery = float(site["Machine_Battery_Capacity_kWh"])
    machine_usable_fraction = float(site["Machine_Usable_Battery_Fraction"])
    charger_power = float(site["Charger_Power_kW"])
    charging_efficiency = float(site["Charging_Efficiency"])
    bess_capacity = float(site["BESS_Capacity_kWh"])
    bess_usable_fraction = float(site["BESS_Usable_Fraction"])
    bess_efficiency = float(site["BESS_Roundtrip_Efficiency"])
    lower_carbon_multiplier = float(site["Lower_Carbon_Grid_Multiplier"])

    active_hours_day = shift_hours * (1.0 - idle_fraction)
    idle_hours_day = shift_hours * idle_fraction

    uses_electric = as_bool(strategy.get("Uses_Electric_Plant"))
    uses_bess = as_bool(strategy.get("Uses_BESS"))
    uses_smart = as_bool(strategy.get("Uses_Smart_Charging"))
    uses_grid_temp = as_bool(strategy.get("Uses_Grid_Temporary_Power"))
    force_backup = strategy.get("Force_Diesel_Backup")
    backup_available = site_backup_available if force_backup is None else as_bool(force_backup)

    result: dict[str, Any] = {
        "Context_ID": site["Context_ID"],
        "Site_Context": site["Site_Context"],
        "Strategy_ID": strategy["Strategy_ID"],
        "Strategy": strategy["Strategy"],
        "Short_Name": strategy["Short_Name"],
        "Plant_Powertrain": strategy["Plant_Powertrain"],
        "Description": strategy["Description"],
        "Key_Risk": strategy["Key_Risk"],
        "Data_Quality_Note": strategy["Data_Quality"],
        "Working_Days": days,
        "Shift_Hours": shift_hours,
        "Idle_Percent": idle_fraction,
        "Grid_Availability": grid_status,
        "Max_Grid_Power_kW": max_grid_power,
        "Uses_Electric_Plant": uses_electric,
        "Uses_BESS": uses_bess,
        "Uses_Smart_Charging": uses_smart,
        "Diesel_Backup_Enabled": backup_available,
        "Active_Hours_per_day": active_hours_day,
        "Idle_Hours_per_day": idle_hours_day,
        "Plant_Energy_Demand_kWh_per_day": 0.0,
        "Temporary_Power_Demand_kWh_per_day": temporary_power_day,
        "Usable_Machine_Battery_kWh": 0.0,
        "Machine_Battery_Supply_kWh_per_day": 0.0,
        "Planned_Charge_Energy_kWh_per_day": 0.0,
        "Planned_Charge_Supply_kWh_per_day": 0.0,
        "Additional_Charging_Supply_kWh_per_day": 0.0,
        "BESS_to_Plant_kWh_per_day": 0.0,
        "BESS_to_Temporary_kWh_per_day": 0.0,
        "BESS_Energy_Used_kWh_per_day": 0.0,
        "Direct_Grid_Temporary_kWh_per_day": 0.0,
        "Backup_to_Plant_kWh_per_day": 0.0,
        "Backup_to_Temporary_kWh_per_day": 0.0,
        "Plant_Energy_Unserved_kWh_per_day": 0.0,
        "Temporary_Energy_Unserved_kWh_per_day": 0.0,
        "Effective_Charger_Power_kW": 0.0,
        "Available_Offshift_Hours": 0.0,
        "Grid_Electricity_kWh": 0.0,
        "Backup_Diesel_L": 0.0,
        "Plant_Diesel_L": 0.0,
        "Plant_Diesel_L_per_day": 0.0,
        "Temporary_Power_Diesel_L": 0.0,
        "Temporary_Power_Diesel_L_per_day": 0.0,
        "Calculated_Downtime_h_per_day": 0.0,
        "Required_Overnight_Recharge_h": 0.0,
        "Battery_Equivalent_Cycles_per_day": 0.0,
        "Energy_Unserved_kWh_per_day": 0.0,
        "Backup_Energy_Share": 0.0,
    }

    # -----------------------------------------------------------------
    # Diesel strategies
    # -----------------------------------------------------------------
    if not uses_electric:
        idle_reduction = min(1.0, max(0.0, float(strategy["Idle_Reduction_Factor"])))
        diesel_rate = float(strategy["Plant_Diesel_L_per_active_h"])
        idle_fuel_fraction = float(strategy["Diesel_Idle_Fuel_Fraction"])
        generator_rate = float(strategy["Generator_Diesel_L_per_kWh"])

        plant_diesel_day = (
            active_hours_day * diesel_rate
            + idle_hours_day * idle_reduction * diesel_rate * idle_fuel_fraction
        )
        temp_diesel_day = temporary_power_day * generator_rate
        total_diesel = days * (plant_diesel_day + temp_diesel_day)

        operational = total_diesel * ef_diesel_direct
        expanded = total_diesel * (ef_diesel_direct + ef_diesel_wtt)
        energy_cost = total_diesel * diesel_price
        hire_cost = days * (
            float(strategy["Plant_Hire_GBP_per_day"])
            + float(strategy["Power_System_GBP_per_day"])
        )

        result.update(
            {
                "Plant_Diesel_L": days * plant_diesel_day,
                "Plant_Diesel_L_per_day": plant_diesel_day,
                "Temporary_Power_Diesel_L": days * temp_diesel_day,
                "Temporary_Power_Diesel_L_per_day": temp_diesel_day,
                "Operational_CO2e_kg": operational,
                "Expanded_Energy_CO2e_kg": expanded,
                "Energy_Cost_GBP": energy_cost,
                "Hire_and_Power_Cost_GBP": hire_cost,
                "Total_Cost_GBP": energy_cost + hire_cost,
                "Productivity_Index": float(strategy["Productivity_Index"]),
                "Exhaust_NOx_Index": float(strategy["Exhaust_NOx_Index"]),
                "Exhaust_PM_Index": float(strategy["Exhaust_PM_Index"]),
                "Noise_Index": float(strategy["Noise_Index"]),
                "Air_Quality_Benefit_Index": 100.0
                - (
                    float(strategy["Exhaust_NOx_Index"])
                    + float(strategy["Exhaust_PM_Index"])
                )
                / 2.0,
                "Noise_Benefit_Index": 100.0 - float(strategy["Noise_Index"]),
            }
        )
        return result

    # -----------------------------------------------------------------
    # Electric strategies
    # -----------------------------------------------------------------
    electricity_rate = float(strategy["Plant_Electricity_kWh_per_active_h"])
    electric_idle_fraction = float(strategy["Electric_Idle_Energy_Fraction"])
    plant_demand = (
        active_hours_day * electricity_rate
        + idle_hours_day * electricity_rate * electric_idle_fraction
    )
    initial_machine_energy = machine_battery * machine_usable_fraction
    battery_cycles = plant_demand / initial_machine_energy if initial_machine_energy > 0 else math.inf

    grid_available = grid_status.lower() != "unavailable" and max_grid_power > 0
    shift_grid_capacity = max_grid_power * shift_hours if grid_available else 0.0

    bess_temp_share = (
        min(1.0, max(0.0, float(strategy["BESS_Temporary_Power_Share"])))
        if uses_bess and bess_available
        else 0.0
    )

    direct_grid_temp_request = (
        temporary_power_day * grid_temp_share * (1.0 - bess_temp_share)
        if uses_grid_temp
        else 0.0
    )
    direct_grid_temp = min(direct_grid_temp_request, shift_grid_capacity)
    average_temp_grid_power = direct_grid_temp / shift_hours if shift_hours > 0 else 0.0

    effective_charger_power = (
        max(0.0, min(charger_power, max_grid_power - average_temp_grid_power))
        if grid_available
        else 0.0
    )
    planned_hours_effective = planned_charging_hours if charging_during_breaks else 0.0
    planned_charge_output_available = (
        effective_charger_power * planned_hours_effective * charging_efficiency
    )

    machine_battery_supply = min(initial_machine_energy, plant_demand)
    remaining_plant_demand = max(0.0, plant_demand - machine_battery_supply)
    planned_charge_supply = min(planned_charge_output_available, remaining_plant_demand)
    plant_gap = max(0.0, remaining_plant_demand - planned_charge_supply)

    temp_gap = max(0.0, temporary_power_day - direct_grid_temp)

    bess_usable_output = (
        bess_capacity * bess_usable_fraction if uses_bess and bess_available else 0.0
    )
    bess_to_plant = min(plant_gap, bess_usable_output)
    plant_gap -= bess_to_plant
    bess_remaining = max(0.0, bess_usable_output - bess_to_plant)
    bess_to_temp = min(temp_gap, bess_remaining)
    temp_gap -= bess_to_temp
    bess_output_total = bess_to_plant + bess_to_temp

    backup_plant_output = 0.0
    backup_temp_output = 0.0
    additional_shift_charge_output = 0.0
    downtime = 0.0
    unserved_plant = 0.0
    unserved_temp = 0.0

    if backup_available:
        backup_plant_output = plant_gap
        backup_temp_output = temp_gap
        plant_gap = 0.0
        temp_gap = 0.0
    else:
        if plant_gap > 0:
            if effective_charger_power > 0:
                additional_shift_charge_output = plant_gap
                downtime = plant_gap / (effective_charger_power * charging_efficiency)
                plant_gap = 0.0
            else:
                unserved_plant = plant_gap
                plant_gap = 0.0
        if temp_gap > 0:
            unserved_temp = temp_gap
            temp_gap = 0.0

    direct_machine_output = (
        machine_battery_supply
        + planned_charge_supply
        + additional_shift_charge_output
    )
    direct_machine_grid_input = (
        direct_machine_output / charging_efficiency if charging_efficiency > 0 else math.inf
    )
    bess_grid_input = bess_output_total / bess_efficiency if bess_efficiency > 0 else math.inf
    backup_generator_output = backup_temp_output + backup_plant_output / charging_efficiency
    backup_fuel_day = backup_generator_output * float(strategy["Generator_Diesel_L_per_kWh"])

    total_grid_input_day = direct_machine_grid_input + direct_grid_temp + bess_grid_input
    smart_share = lower_carbon_share if uses_smart and smart_available else 0.0
    effective_grid_factor = ef_grid_direct * (
        (1.0 - smart_share) + smart_share * lower_carbon_multiplier
    )

    total_grid_input = days * total_grid_input_day
    total_backup_fuel = days * backup_fuel_day

    operational = total_grid_input * effective_grid_factor + total_backup_fuel * ef_diesel_direct
    expanded = (
        total_grid_input * (effective_grid_factor + ef_grid_td + ef_grid_wtt)
        + total_backup_fuel * (ef_diesel_direct + ef_diesel_wtt)
    )

    energy_cost = total_grid_input * electricity_price + total_backup_fuel * diesel_price
    hire_cost = days * (
        float(strategy["Plant_Hire_GBP_per_day"])
        + float(strategy["Power_System_GBP_per_day"])
    )

    initial_battery_used = machine_battery_supply
    offshift_grid_input = initial_battery_used / charging_efficiency + bess_grid_input
    available_offshift_hours = max(0.0, 24.0 - shift_hours) if overnight_charging else 0.0
    required_overnight_time = (
        offshift_grid_input / max_grid_power if max_grid_power > 0 else math.inf
    )

    total_demand = plant_demand + temporary_power_day
    backup_output_total = backup_plant_output + backup_temp_output
    backup_share = backup_output_total / total_demand if total_demand > 0 else 0.0
    unserved_total = unserved_plant + unserved_temp

    result.update(
        {
            "Plant_Energy_Demand_kWh_per_day": plant_demand,
            "Usable_Machine_Battery_kWh": initial_machine_energy,
            "Machine_Battery_Supply_kWh_per_day": machine_battery_supply,
            "Planned_Charge_Energy_kWh_per_day": planned_charge_output_available,
            "Planned_Charge_Supply_kWh_per_day": planned_charge_supply,
            "Additional_Charging_Supply_kWh_per_day": additional_shift_charge_output,
            "BESS_to_Plant_kWh_per_day": bess_to_plant,
            "BESS_to_Temporary_kWh_per_day": bess_to_temp,
            "BESS_Energy_Used_kWh_per_day": bess_output_total,
            "Direct_Grid_Temporary_kWh_per_day": direct_grid_temp,
            "Backup_to_Plant_kWh_per_day": backup_plant_output,
            "Backup_to_Temporary_kWh_per_day": backup_temp_output,
            "Plant_Energy_Unserved_kWh_per_day": unserved_plant,
            "Temporary_Energy_Unserved_kWh_per_day": unserved_temp,
            "Effective_Charger_Power_kW": effective_charger_power,
            "Available_Offshift_Hours": available_offshift_hours,
            "Grid_Electricity_kWh": total_grid_input,
            "Backup_Diesel_L": total_backup_fuel,
            "Calculated_Downtime_h_per_day": downtime,
            "Required_Overnight_Recharge_h": required_overnight_time
            if math.isfinite(required_overnight_time)
            else 0.0,
            "Battery_Equivalent_Cycles_per_day": battery_cycles,
            "Energy_Unserved_kWh_per_day": unserved_total,
            "Backup_Energy_Share": backup_share,
            "Operational_CO2e_kg": operational,
            "Expanded_Energy_CO2e_kg": expanded,
            "Energy_Cost_GBP": energy_cost,
            "Hire_and_Power_Cost_GBP": hire_cost,
            "Total_Cost_GBP": energy_cost + hire_cost,
            "Productivity_Index": float(strategy["Productivity_Index"]),
            "Exhaust_NOx_Index": float(strategy["Exhaust_NOx_Index"]),
            "Exhaust_PM_Index": float(strategy["Exhaust_PM_Index"]),
            "Noise_Index": float(strategy["Noise_Index"]),
            "Air_Quality_Benefit_Index": 100.0
            - (
                float(strategy["Exhaust_NOx_Index"])
                + float(strategy["Exhaust_PM_Index"])
            )
            / 2.0,
            "Noise_Benefit_Index": 100.0 - float(strategy["Noise_Index"]),
        }
    )
    return result



def _carbon_performance_label(reduction: float, valid: bool, strategy_id: str) -> str:
    """Describe carbon relative to the conventional-diesel baseline."""
    if not valid:
        return "Incomplete carbon result"
    if strategy_id == "S1" or reduction < 0.05:
        return "Baseline / high carbon"
    if reduction < 0.30:
        return "Limited carbon reduction"
    if reduction < 0.60:
        return "Moderate carbon reduction"
    if reduction < 0.90:
        return "Substantial carbon reduction"
    return "Very substantial carbon reduction"


def _energy_supply_profile(row: pd.Series) -> tuple[str, str]:
    if not as_bool(row["Uses_Electric_Plant"]):
        return (
            "All demand supplied",
            "The diesel plant and generator are assumed to supply the required plant work and temporary power.",
        )

    unserved = float(row["Energy_Unserved_kWh_per_day"])
    plant_demand = float(row["Plant_Energy_Demand_kWh_per_day"])
    temporary_demand = float(row["Temporary_Power_Demand_kWh_per_day"])
    total_demand = plant_demand + temporary_demand
    supplied = max(0.0, total_demand - unserved)
    backup_share = float(row["Backup_Energy_Share"])
    routine_recharge_valid = bool(row.get("Routine_Recharge_Valid", True))

    if unserved <= 0.01:
        if not routine_recharge_valid:
            return (
                "Daily demand supplied; recharge cycle incomplete",
                "The working-day demand can be supplied, but the batteries cannot be reliably restored for repeated daily operation under the selected off-shift charging assumptions.",
            )
        if backup_share > 0.001:
            return (
                "All demand supplied using diesel backup",
                f"All demand is supplied, but diesel backup provides about {backup_share:.0%} of daily site energy.",
            )
        return (
            "All demand supplied",
            "All electric-plant and temporary site-power demand is supplied under the selected assumptions.",
        )
    if supplied <= 0.01:
        return (
            "Demand cannot be supplied",
            f"The selected system leaves {unserved:.1f} kWh/day of required energy unserved.",
        )
    return (
        "Demand partly unmet",
        f"The selected system leaves {unserved:.1f} kWh/day of plant or temporary-power demand unserved.",
    )


def _local_environment_profile(row: pd.Series) -> tuple[str, str]:
    nox = float(row["Exhaust_NOx_Index"])
    pm = float(row["Exhaust_PM_Index"])
    noise = float(row["Noise_Index"])
    mean_exhaust = (nox + pm) / 2.0

    if mean_exhaust <= 10 and noise <= 60:
        label = "Strong local environmental performance"
    elif mean_exhaust <= 40 and noise <= 95:
        label = "Moderate local environmental performance"
    else:
        label = "Poor local environmental performance"

    note = (
        f"Relative teaching indices: NOx {nox:.0f}, PM {pm:.0f}, noise {noise:.0f}; "
        "lower values indicate lower point-of-use impact."
    )
    return label, note


def _site_compatibility_profile(site: dict[str, Any], row: pd.Series, energy_status: str) -> tuple[str, str]:
    levels = {"low": 0, "medium": 1, "high": 2, "very high": 3}
    sensitivity = max(
        levels.get(str(site.get("Noise_Sensitivity", "Medium")).strip().lower(), 1),
        levels.get(str(site.get("Community_Sensitivity", "Medium")).strip().lower(), 1),
    )
    nox = float(row["Exhaust_NOx_Index"])
    pm = float(row["Exhaust_PM_Index"])
    noise = float(row["Noise_Index"])
    mean_exhaust = (nox + pm) / 2.0
    uses_electric = as_bool(row["Uses_Electric_Plant"])
    uses_bess = as_bool(row["Uses_BESS"])
    uses_smart = as_bool(row["Uses_Smart_Charging"])

    rank = 0  # 0 good, 1 conditions, 2 poor
    reasons: list[str] = []

    if sensitivity >= 2:
        if mean_exhaust >= 80 or noise >= 98:
            rank = max(rank, 2)
            reasons.append("High community or noise sensitivity conflicts with the strategy's local exhaust or noise profile.")
        elif mean_exhaust >= 20 or noise >= 70:
            rank = max(rank, 1)
            reasons.append("Community, exhaust or noise controls would be required for this sensitive site.")
    elif sensitivity == 1 and (mean_exhaust >= 50 or noise >= 80):
        rank = max(rank, 1)
        reasons.append("Local exhaust or noise needs management under the selected site context.")

    if uses_electric:
        grid_status = str(site.get("Grid_Availability", "Unavailable")).strip().lower()
        if grid_status == "unavailable" or float(site.get("Max_Grid_Power_kW", 0.0)) <= 0:
            rank = max(rank, 2)
            reasons.append("The electric strategy does not match the available grid infrastructure.")
        elif grid_status == "limited":
            rank = max(rank, 1)
            reasons.append("The limited grid connection requires charging and power-management controls.")

        if uses_bess and not as_bool(site.get("Battery_Storage_Available")):
            rank = max(rank, 2)
            reasons.append("The strategy requires site battery storage that is not available.")
        if uses_smart and not as_bool(site.get("Smart_Charging_Available")):
            rank = max(rank, 1)
            reasons.append("Smart charging is selected but lower-carbon charging periods are not available.")

    if energy_status in {"Demand partly unmet", "Demand cannot be supplied"}:
        rank = max(rank, 2)
        reasons.append("The current site infrastructure does not supply the full required energy demand.")

    labels = {0: "Good site fit", 1: "Site fit with conditions", 2: "Poor site fit"}
    if not reasons:
        reasons.append("The strategy is compatible with the selected site's local constraints and infrastructure assumptions.")
    return labels[rank], " ".join(reasons)


def _delivery_risk_profile(site: dict[str, Any], row: pd.Series, energy_status: str) -> tuple[str, str]:
    if not as_bool(row["Uses_Electric_Plant"]):
        return (
            "Low delivery risk",
            "Fuel-based operation is assumed to meet the programme; mechanical failure, maintenance and refuelling delays are outside the model.",
        )

    downtime = float(row["Calculated_Downtime_h_per_day"])
    backup_share = float(row["Backup_Energy_Share"])
    cycles = float(row["Battery_Equivalent_Cycles_per_day"])
    recharge = float(row["Required_Overnight_Recharge_h"])
    available_offshift = float(row["Available_Offshift_Hours"])
    grid_status = str(site.get("Grid_Availability", "Unavailable")).strip().lower()
    overnight = as_bool(site.get("Overnight_Charging_Available"))
    days = float(site.get("Working_Days", 1))

    high_reasons: list[str] = []
    moderate_reasons: list[str] = []

    if energy_status in {"Demand partly unmet", "Demand cannot be supplied"}:
        high_reasons.append("Some required energy is not supplied.")
    if downtime > 1.0:
        high_reasons.append(f"Plant charging creates about {downtime:.1f} hours/day of interruption.")
    elif downtime > 0.25:
        moderate_reasons.append(f"Plant charging creates about {downtime:.1f} hours/day of interruption.")
    if backup_share > 0.25:
        high_reasons.append(f"Diesel backup supplies about {backup_share:.0%} of daily site energy.")
    elif backup_share > 0.001:
        moderate_reasons.append(f"Diesel backup supplies about {backup_share:.0%} of daily site energy.")
    if overnight and recharge > available_offshift + 0.01:
        high_reasons.append("The required recharge time exceeds the available off-shift period.")
    elif overnight and available_offshift > 0 and recharge > 0.75 * available_offshift:
        moderate_reasons.append("Overnight recharging uses most of the available off-shift period.")
    if not overnight and days > 1 and recharge > 0.01:
        high_reasons.append("Repeated daily operation needs off-shift recharging, but overnight charging is unavailable.")
    if grid_status == "limited":
        moderate_reasons.append("The limited grid connection requires careful scheduling.")
    if cycles > 1.0:
        moderate_reasons.append(f"The plant requires about {cycles:.1f} battery-equivalent cycles per day.")

    if high_reasons:
        return "High delivery risk", " ".join(high_reasons + moderate_reasons)
    if moderate_reasons:
        return "Moderate delivery risk", " ".join(moderate_reasons)
    return "Low delivery risk", "No material energy-related programme interruption is calculated under the selected assumptions."


def _key_implementation_condition(site: dict[str, Any], row: pd.Series, energy_status: str) -> str:
    if energy_status in {"Demand partly unmet", "Demand cannot be supplied"}:
        return "Increase grid, battery or backup capacity so that the full plant and temporary-power demand is supplied."
    if not as_bool(row["Uses_Electric_Plant"]):
        if str(row["Strategy_ID"]) == "S2":
            return "Enforce anti-idling controls and correctly size and maintain the generator."
        return "Manage fuel supply, idling, exhaust and noise throughout the programme."
    if float(row["Backup_Energy_Share"]) > 0.001:
        return "Confirm backup-generator capacity, fuel logistics and the additional carbon before implementation."
    if str(site.get("Grid_Availability", "")).strip().lower() == "limited":
        return "Verify the grid limit and coordinate plant charging with temporary site-power demand."
    if float(row["Required_Overnight_Recharge_h"]) > 0.01:
        return f"Provide reliable off-shift charging for about {float(row['Required_Overnight_Recharge_h']):.1f} hours between working days."
    if as_bool(row["Uses_BESS"]):
        return "Confirm battery-storage capacity, charging access, space, safety controls and supplier availability."
    return "Confirm grid capacity, charger rating and machine battery runtime before mobilisation."

def calculate_scenarios(
    site: dict[str, Any],
    strategies: pd.DataFrame,
    factors: pd.DataFrame,
    defaults: pd.DataFrame,
    custom_strategy: dict[str, Any] | None = None,
) -> pd.DataFrame:
    records = [
        calculate_strategy(site, row.to_dict(), factors, defaults)
        for _, row in strategies.iterrows()
    ]
    if custom_strategy is not None:
        records.append(calculate_strategy(site, custom_strategy, factors, defaults))

    result = pd.DataFrame(records)
    baseline_operational = float(
        result.loc[result["Strategy_ID"] == "S1", "Operational_CO2e_kg"].iloc[0]
    )
    baseline_expanded = float(
        result.loc[result["Strategy_ID"] == "S1", "Expanded_Energy_CO2e_kg"].iloc[0]
    )
    baseline_cost = float(
        result.loc[result["Strategy_ID"] == "S1", "Total_Cost_GBP"].iloc[0]
    )

    result["Operational_Reduction_vs_Baseline"] = (
        1.0 - result["Operational_CO2e_kg"] / baseline_operational
    )
    result["Expanded_Reduction_vs_Baseline"] = (
        1.0 - result["Expanded_Energy_CO2e_kg"] / baseline_expanded
    )
    result["Cost_Difference_vs_Baseline_GBP"] = result["Total_Cost_GBP"] - baseline_cost
    overnight_available = as_bool(site.get("Overnight_Charging_Available"))
    working_days = float(site.get("Working_Days", 1.0))
    result["Routine_Recharge_Valid"] = result.apply(
        lambda row: (
            True
            if not as_bool(row["Uses_Electric_Plant"]) or working_days <= 1
            else (
                float(row["Required_Overnight_Recharge_h"]) <= 0.01
                or (
                    overnight_available
                    and float(row["Required_Overnight_Recharge_h"])
                    <= float(row["Available_Offshift_Hours"]) + 0.01
                )
            )
        ),
        axis=1,
    )
    result["Carbon_Result_Valid"] = (
        (result["Energy_Unserved_kWh_per_day"] <= 0.01)
        & result["Routine_Recharge_Valid"]
    )
    result["Carbon_Comparison_Status"] = result.apply(
        lambda row: (
            "Complete result"
            if bool(row["Carbon_Result_Valid"])
            else (
                "Incomplete – demand unmet"
                if float(row["Energy_Unserved_kWh_per_day"]) > 0.01
                else "Incomplete – recharge cycle unresolved"
            )
        ),
        axis=1,
    )
    result["Carbon_Validity_Note"] = result.apply(
        lambda row: (
            "Complete carbon comparison: all required plant and temporary-power demand is represented and the repeated charging cycle is supported."
            if bool(row["Carbon_Result_Valid"])
            else (
                f"Incomplete carbon result: {float(row['Energy_Unserved_kWh_per_day']):.1f} kWh/day of required energy is not supplied."
                if float(row["Energy_Unserved_kWh_per_day"]) > 0.01
                else "Incomplete carbon result: daily demand is supplied, but the batteries cannot be reliably restored for repeated daily operation under the selected charging assumptions."
            )
        ),
        axis=1,
    )
    result["Operational_Carbon_Performance"] = result.apply(
        lambda row: _carbon_performance_label(
            float(row["Operational_Reduction_vs_Baseline"]),
            bool(row["Carbon_Result_Valid"]),
            str(row["Strategy_ID"]),
        ),
        axis=1,
    )
    result["Expanded_Carbon_Performance"] = result.apply(
        lambda row: _carbon_performance_label(
            float(row["Expanded_Reduction_vs_Baseline"]),
            bool(row["Carbon_Result_Valid"]),
            str(row["Strategy_ID"]),
        ),
        axis=1,
    )

    energy_profiles = result.apply(_energy_supply_profile, axis=1)
    result["Energy_Supply_Status"] = [item[0] for item in energy_profiles]
    result["Energy_Supply_Note"] = [item[1] for item in energy_profiles]

    local_profiles = result.apply(_local_environment_profile, axis=1)
    result["Local_Environmental_Performance"] = [item[0] for item in local_profiles]
    result["Local_Environmental_Note"] = [item[1] for item in local_profiles]

    site_profiles = result.apply(
        lambda row: _site_compatibility_profile(site, row, str(row["Energy_Supply_Status"])),
        axis=1,
    )
    result["Site_Compatibility"] = [item[0] for item in site_profiles]
    result["Site_Compatibility_Note"] = [item[1] for item in site_profiles]

    delivery_profiles = result.apply(
        lambda row: _delivery_risk_profile(site, row, str(row["Energy_Supply_Status"])),
        axis=1,
    )
    result["Delivery_Risk"] = [item[0] for item in delivery_profiles]
    result["Delivery_Risk_Note"] = [item[1] for item in delivery_profiles]
    result["Key_Implementation_Condition"] = result.apply(
        lambda row: _key_implementation_condition(site, row, str(row["Energy_Supply_Status"])),
        axis=1,
    )

    return result

def calculate_all_presets(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    default_map = {
        row["Parameter"]: float(row["Value"])
        for _, row in tables["energy_defaults"].iterrows()
    }
    frames: list[pd.DataFrame] = []
    for _, site_row in tables["sites"].iterrows():
        site = site_row.to_dict()
        site.update(
            {
                "Machine_Battery_Capacity_kWh": default_map["Machine_Battery_Capacity_kWh"],
                "Machine_Usable_Battery_Fraction": default_map["Machine_Usable_Battery_Fraction"],
                "Charger_Power_kW": default_map["Charger_Power_kW"],
                "Charging_Efficiency": default_map["Charging_Efficiency"],
                "BESS_Capacity_kWh": default_map["BESS_Capacity_kWh"],
                "BESS_Usable_Fraction": default_map["BESS_Usable_Fraction"],
                "BESS_Roundtrip_Efficiency": default_map["BESS_Roundtrip_Efficiency"],
                "Lower_Carbon_Grid_Multiplier": default_map["Lower_Carbon_Grid_Multiplier"],
            }
        )
        frames.append(
            calculate_scenarios(
                site,
                tables["strategies"],
                tables["factors"],
                tables["energy_defaults"],
            )
        )
    return pd.concat(frames, ignore_index=True)
