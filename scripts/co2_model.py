"""
Core CO2eq footprint model for student commutes: sigmoid-based probability
of commuting by car (given distance), and expected CO2eq calculation
(weighted average over car and public_transport).
"""

import math


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
    "public_transport": 60,
}

# Sigmoid parameters for estimating the probability that a student commuted
# by car, based purely on distance (the actual mode of transport is unknown).
# MIDPOINT_KM: distance at which p_car = 0.5
# STEEPNESS: how sharply the probability shifts from public_transport to car
# as distance increases. Tune these based on domain knowledge.
P_CAR_MIDPOINT_KM = 8.0
P_CAR_STEEPNESS = 0.3

# Students travel to the exam and back, so total distance traveled is
# double the one-way distance between their postal code and the exam
# location.
ROUND_TRIP_MULTIPLIER = 2


def p_car_given_distance(distance_km: float, midpoint_km: float = P_CAR_MIDPOINT_KM,
                          steepness: float = P_CAR_STEEPNESS) -> float:
    """
    Estimates the probability that a student commuted by car, as a function
    of distance, using a logistic (sigmoid) curve. Close to the university,
    p_car is low (students tend to use public transport); far from the
    university, p_car approaches 1 (public transport becomes too time
    consuming). Around midpoint_km, p_car = 0.5.
    """
    return 1 / (1 + math.exp(-steepness * (distance_km - midpoint_km)))


def calculate_expected_co2_kg(one_way_distance_km: float | None) -> float | None:
    """
    Calculates the EXPECTED CO2eq footprint (in kg) of a ROUND TRIP (there
    and back), given the one-way distance in km. Since the actual mode of
    transport is unknown, this is a weighted average of the car and
    public_transport emission factors, weighted by
    p_car_given_distance(one_way_distance_km) - the mode choice is assumed
    to depend on the one-way distance, while the emissions are calculated
    over the full round-trip distance.

    Returns None if the distance is unknown.
    """
    if one_way_distance_km is None:
        return None

    p_car = p_car_given_distance(one_way_distance_km)
    round_trip_distance_km = one_way_distance_km * ROUND_TRIP_MULTIPLIER

    co2_car_kg = (round_trip_distance_km * CO2_EMISSION_FACTORS_G_PER_KM["car"]) / 1000
    co2_public_transport_kg = (round_trip_distance_km * CO2_EMISSION_FACTORS_G_PER_KM["public_transport"]) / 1000

    return p_car * co2_car_kg + (1 - p_car) * co2_public_transport_kg