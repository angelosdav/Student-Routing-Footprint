"""
Analyzes whether a student's commute to the exam location could be
considered "unnecessary" - defined as: the student showed up to the
exam and got a grade of 0 or 1.

Uses both haversine (straight-line) and OSRM (road) distance for
comparison, with geocoding results cached per postal code so the same
postal code is never geocoded twice.
"""

import random
import statistics
import time

from co2_model import (
    CO2_EMISSION_FACTORS_G_PER_KM,
    ROUND_TRIP_MULTIPLIER,
    calculate_expected_co2_kg,
    p_car_given_distance,
)
from utils import geocode_tk, haversine_distance, road_distance


def analyze_student_commutes(students: list[dict], university_tk: str) -> list[dict]:
    """
    students: list of dicts, each with keys:
        - "onoma_mathimatos": str
        - "tk": str (student's postal code)
        - "bathmos": int or float

    university_tk: postal code of the exam location

    Returns a new list of dicts, each with the original keys plus:
        - "straight_distance_km": float or None
        - "road_distance_km": float or None
        - "unnecessary_trip": bool
        - "p_car": float or None (estimated probability the trip was by car,
          based on the one-way distance)
        - "one_way_distance_km": float or None (the distance actually used
          for the CO2 calculation: road_distance_km, or straight_distance_km
          as a fallback)
        - "expected_co2_kg": float or None (weighted average over car and
          public_transport, for the ROUND TRIP there and back, based on
          road_distance_km, falls back to straight_distance_km if the road
          distance could not be calculated)
    """
    geocode_cache: dict[str, tuple[float, float] | None] = {}

    def get_coords(tk: str) -> tuple[float, float] | None:
        if tk not in geocode_cache:
            geocode_cache[tk] = geocode_tk(tk)
            time.sleep(1)  # be polite to the free API
        return geocode_cache[tk]

    university_coords = get_coords(university_tk)

    results = []
    for student in students:
        student_coords = get_coords(student["tk"])

        straight_distance_km = None
        road_distance_km = None
        if student_coords and university_coords:
            straight_distance_km = haversine_distance(student_coords, university_coords)
            road_distance_km = road_distance(student_coords, university_coords)

        unnecessary_trip = student["bathmos"] in (0, 1)

        distance_for_co2 = road_distance_km if road_distance_km is not None else straight_distance_km
        p_car = p_car_given_distance(distance_for_co2) if distance_for_co2 is not None else None
        expected_co2_kg = calculate_expected_co2_kg(distance_for_co2)

        results.append({
            **student,
            "straight_distance_km": straight_distance_km,
            "road_distance_km": road_distance_km,
            "unnecessary_trip": unnecessary_trip,
            "p_car": p_car,
            "one_way_distance_km": distance_for_co2,
            "expected_co2_kg": expected_co2_kg,
        })

    return results


def unnecessary_trips_co2_by_course(records: list[dict]) -> dict[str, float]:
    """
    Sums up the expected CO2eq footprint (in kg) of unnecessary trips,
    grouped by course name. Records with unnecessary_trip=False or
    expected_co2_kg=None are not included in the sums.
    """
    totals: dict[str, float] = {}

    for record in records:
        if not record["unnecessary_trip"] or record["expected_co2_kg"] is None:
            continue

        course_name = record["onoma_mathimatos"]
        totals[course_name] = totals.get(course_name, 0) + record["expected_co2_kg"]

    return totals


def _percentile(sorted_values: list[float], pct: float) -> float:
    """
    Returns the value at the given percentile (0-1) from an already sorted
    list of values.
    """
    index = min(int(pct * len(sorted_values)), len(sorted_values) - 1)
    return sorted_values[index]


def monte_carlo_unnecessary_trips_co2(records: list[dict], n_simulations: int = 1000,
                                       random_seed: int | None = None) -> dict[str, dict]:
    """
    Runs a Monte Carlo simulation to estimate the CO2eq footprint (in kg) of
    unnecessary trips, grouped by course name. Instead of using the expected
    value (a fixed weighted average), each simulation randomly samples each
    student's mode of transport (car or public_transport) based on their
    p_car probability, then sums up the resulting CO2 per course. Running
    many simulations gives a distribution of plausible totals instead of a
    single point estimate.

    records: output of analyze_student_commutes
    n_simulations: number of Monte Carlo runs
    random_seed: optional seed for reproducibility

    Returns a dict mapping course_name -> dict with keys:
        - "mean_kg", "std_kg", "p5_kg", "p95_kg"
    """
    rng = random.Random(random_seed)

    relevant_records = [
        record for record in records
        if record["unnecessary_trip"]
        and record["p_car"] is not None
        and record["one_way_distance_km"] is not None
    ]

    course_names = sorted({record["onoma_mathimatos"] for record in relevant_records})
    simulated_totals_by_course: dict[str, list[float]] = {course_name: [] for course_name in course_names}

    for _ in range(n_simulations):
        run_totals = {course_name: 0.0 for course_name in course_names}

        for record in relevant_records:
            round_trip_distance_km = record["one_way_distance_km"] * ROUND_TRIP_MULTIPLIER
            used_car = rng.random() < record["p_car"]
            emission_factor_g_per_km = CO2_EMISSION_FACTORS_G_PER_KM["car" if used_car else "public_transport"]
            co2_kg = (round_trip_distance_km * emission_factor_g_per_km) / 1000
            run_totals[record["onoma_mathimatos"]] += co2_kg

        for course_name, total_kg in run_totals.items():
            simulated_totals_by_course[course_name].append(total_kg)

    summary = {}
    for course_name, totals in simulated_totals_by_course.items():
        sorted_totals = sorted(totals)
        summary[course_name] = {
            "mean_kg": statistics.mean(totals),
            "std_kg": statistics.stdev(totals) if len(totals) > 1 else 0.0,
            "p5_kg": _percentile(sorted_totals, 0.05),
            "p95_kg": _percentile(sorted_totals, 0.95),
        }

    return summary


def sensitivity_analysis_total_co2(records: list[dict], midpoint_values_km: list[float],
                                    steepness_values: list[float]) -> dict[tuple[float, float], float]:
    """
    Recomputes the total expected CO2eq (kg) across ALL unnecessary trips,
    for a grid of P_CAR_MIDPOINT_KM / P_CAR_STEEPNESS values, to see how
    sensitive the total is to these assumptions (which were not derived
    from real data).

    records: output of analyze_student_commutes
    midpoint_values_km: list of P_CAR_MIDPOINT_KM values to try
    steepness_values: list of P_CAR_STEEPNESS values to try

    Returns a dict mapping (midpoint_km, steepness) -> total_co2_kg
    """
    relevant_records = [
        record for record in records
        if record["unnecessary_trip"] and record["one_way_distance_km"] is not None
    ]

    results = {}
    for midpoint_km in midpoint_values_km:
        for steepness in steepness_values:
            total_co2_kg = 0.0

            for record in relevant_records:
                one_way_distance_km = record["one_way_distance_km"]
                p_car = p_car_given_distance(one_way_distance_km, midpoint_km, steepness)
                round_trip_distance_km = one_way_distance_km * ROUND_TRIP_MULTIPLIER

                co2_car_kg = (round_trip_distance_km * CO2_EMISSION_FACTORS_G_PER_KM["car"]) / 1000
                co2_public_transport_kg = (round_trip_distance_km * CO2_EMISSION_FACTORS_G_PER_KM["public_transport"]) / 1000

                total_co2_kg += p_car * co2_car_kg + (1 - p_car) * co2_public_transport_kg

            results[(midpoint_km, steepness)] = total_co2_kg

    return results