import time

from utils import geocode_tk, haversine_distance, road_distance
from commute_analysis import (
    analyze_student_commutes,
    monte_carlo_unnecessary_trips_co2,
    sensitivity_analysis_total_co2,
    unnecessary_trips_co2_by_course,
)


if __name__ == "__main__":
    tk_home = "12243"
    tk_university = "12241"

    print(f"Geocoding: {tk_home} -> {tk_university}")
    coord_home = geocode_tk(tk_home)
    time.sleep(1)
    coord_university = geocode_tk(tk_university)

    if coord_home and coord_university:
        straight = haversine_distance(coord_home, coord_university)
        print(f"Straight-line distance (haversine): {straight:.2f} km")

        road = road_distance(coord_home, coord_university)
        if road is not None:
            print(f"Road distance (OSRM):               {road:.2f} km")
            print(f"Road/straight-line ratio:            {road/straight:.2f}x")
        else:
            print("Could not calculate road distance.")
    else:
        print("Could not calculate distance (a postal code was not found).")

    print()
    students = [
        {"onoma_mathimatos": "Statistics", "tk": "12243", "bathmos": 0},
        {"onoma_mathimatos": "Databases", "tk": "18863", "bathmos": 7},
        {"onoma_mathimatos": "Machine Learning", "tk": "15772", "bathmos": 1},
    ]
    university_tk = "12241"

    analyzed = analyze_student_commutes(students, university_tk)

    for record in analyzed:
        print(record)

    print()
    print("Expected CO2eq (kg) from unnecessary trips, by course:")
    for course_name, co2_kg in unnecessary_trips_co2_by_course(analyzed).items():
        print(f"  {course_name}: {co2_kg:.2f} kg")

    print()
    print("Monte Carlo simulation (1000 runs), by course:")
    monte_carlo_summary = monte_carlo_unnecessary_trips_co2(analyzed, n_simulations=1000, random_seed=42)
    for course_name, stats in monte_carlo_summary.items():
        print(f"  {course_name}: mean={stats['mean_kg']:.2f} kg, std={stats['std_kg']:.2f} kg, "
              f"p5={stats['p5_kg']:.2f} kg, p95={stats['p95_kg']:.2f} kg")

    print()
    print("Sensitivity analysis (total CO2eq kg across all unnecessary trips):")
    sensitivity_results = sensitivity_analysis_total_co2(
        analyzed,
        midpoint_values_km=[5.0, 8.0, 12.0],
        steepness_values=[0.2, 0.3, 0.5],
    )
    for (midpoint_km, steepness), total_co2_kg in sensitivity_results.items():
        print(f"  midpoint={midpoint_km}km, steepness={steepness}: {total_co2_kg:.2f} kg")