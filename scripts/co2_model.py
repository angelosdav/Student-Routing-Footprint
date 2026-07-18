"""
Core CO2eq footprint model for student commutes: sigmoid-based probability
of commuting by car (given distance), and expected CO2eq calculation
(weighted average over car and public_transport).
"""

import json
import math
import os


# Average emission factors (grams of CO2eq per km per passenger), based on
# the UK Government's DESNZ greenhouse gas conversion factors (the dataset
# companies use for emissions reporting), as summarized by Our World in Data
# (Ritchie, 2023, https://ourworldindata.org/travel-carbon-footprint):
#   - car: ~170 gCO2/km (average petrol car)
#   - public_transport: blended estimate between metro (~30 gCO2/km) and bus
#     (~75-90 gCO2/km), since the exact mode within "public transport" is
#     not known
CO2_EMISSION_FACTORS_G_PER_KM = {
    "car": 170,
    "public_transport_average": 60,
    "public_transport_marginal": 0,  # 0 if the bus/train runs regardless of the student
    "walk_cycle": 0,
}

# Load MNL parameters from config.json (fallback to defaults if missing)
config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')
try:
    with open(config_path, 'r', encoding='utf-8') as f:
        _config = json.load(f)
        MNL_BETA_TIME = _config["mnl_model"]["beta_time"]
        MNL_ASC_CAR = _config["mnl_model"]["asc_car"]
        MNL_ASC_PT = _config["mnl_model"]["asc_pt"]
        MNL_ASC_WALK = _config["mnl_model"]["asc_walk"]
except Exception:
    MNL_BETA_TIME = -0.05
    MNL_ASC_CAR = 0.5
    MNL_ASC_PT = 1.5
    MNL_ASC_WALK = 2.5

# Students travel to the exam and back, so total distance traveled is
# double the one-way distance between their postal code and the exam
# location.
ROUND_TRIP_MULTIPLIER = 2


def get_transport_mode_probabilities(distance_km: float, 
                                     driving_duration_min: float | None = None,
                                     beta_time: float = MNL_BETA_TIME) -> dict[str, float]:
    """
    Estimates the probability distribution of commuting by car, public transport,
    and walking/cycling using a Multinomial Logit (MNL) utility model based on
    estimated travel times. This is the industry standard for transport modeling.
    """
    if driving_duration_min is None:
        # Estimate driving duration assuming ~30 km/h average speed in urban areas
        driving_duration_min = (distance_km / 30.0) * 60.0

    # 1. Estimate travel times (in minutes) for each mode
    t_car = driving_duration_min
    t_walk = (distance_km / 5.0) * 60.0  # Assumes 5 km/h walking speed
    t_pt = t_car * 1.5 + 15.0            # PT is typically 1.5x driving time + 15 mins for waiting/walking

    # 2. Calculate Utilities (V) for each mode
    v_car = beta_time * t_car + MNL_ASC_CAR
    v_pt = beta_time * t_pt + MNL_ASC_PT
    v_walk = beta_time * t_walk + MNL_ASC_WALK

    # 3. Calculate probabilities using the Logit formula: exp(V_i) / sum(exp(V_j))
    # Cap utilities to prevent math overflow in extreme cases
    max_v = max(v_car, v_pt, v_walk)
    exp_car = math.exp(v_car - max_v)
    exp_pt = math.exp(v_pt - max_v)
    exp_walk = math.exp(v_walk - max_v)
    
    total_exp = exp_car + exp_pt + exp_walk

    return {
        "car": exp_car / total_exp,
        "public_transport": exp_pt / total_exp,
        "walk_cycle": exp_walk / total_exp
    }


def calculate_expected_co2_kg(one_way_distance_km: float | None, 
                              driving_duration_min: float | None = None,
                              use_marginal_pt_emissions: bool = False) -> float | None:
    """
    Calculates the EXPECTED CO2eq footprint (in kg) of a ROUND TRIP (there
    and back), given the one-way distance in km and driving duration.

    use_marginal_pt_emissions: if True, assumes public transport would run anyway (0 additional emissions).

    Returns None if the distance is unknown.
    """
    if one_way_distance_km is None:
        return None

    probs = get_transport_mode_probabilities(one_way_distance_km, driving_duration_min)
    round_trip_distance_km = one_way_distance_km * ROUND_TRIP_MULTIPLIER

    pt_emission_key = "public_transport_marginal" if use_marginal_pt_emissions else "public_transport_average"

    co2_car_kg = (round_trip_distance_km * CO2_EMISSION_FACTORS_G_PER_KM["car"]) / 1000
    co2_public_transport_kg = (round_trip_distance_km * CO2_EMISSION_FACTORS_G_PER_KM[pt_emission_key]) / 1000
    co2_walk_kg = (round_trip_distance_km * CO2_EMISSION_FACTORS_G_PER_KM["walk_cycle"]) / 1000

    return probs["car"] * co2_car_kg + probs["public_transport"] * co2_public_transport_kg + probs["walk_cycle"] * co2_walk_kg