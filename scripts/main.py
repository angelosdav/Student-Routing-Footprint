import csv
import json
import os

from commute_analysis import (
    analyze_student_commutes,
    monte_carlo_unnecessary_trips_co2,
)

if __name__ == "__main__":
    print("=====================================================")
    print(" STUDENT ROUTING & ENVIRONMENTAL FOOTPRINT ANALYSIS  ")
    print("=====================================================\n")
    
    # 1. Load Configuration
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"Error loading config.json: {e}")
        exit(1)
        
    university_tk = config["data"]["university_tk"]
    csv_path = os.path.join(os.path.dirname(__file__), '..', config["data"]["students_csv_path"])
    
    # 2. Load Student Data
    students = []
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                row["bathmos"] = float(row["bathmos"])
                students.append(row)
    except Exception as e:
        print(f"Error loading {csv_path}: {e}")
        exit(1)

    max_grade = config["policy"]["max_unnecessary_grade"]
    marginal_emissions = config["policy"]["use_marginal_pt_emissions"]
    n_sims = config["simulation"]["n_simulations"]

    print(f"[*] Loaded configuration from config.json")
    print(f"[*] Loaded {len(students)} student records from {config['data']['students_csv_path']}")
    print(f"[*] Policy: Trips with exam grades <= {max_grade} are considered 'unnecessary'.")
    print(f"[*] Emissions: Using {'marginal (0 gCO2)' if marginal_emissions else 'average (~60 gCO2)'} emissions for public transport.\n")
    
    # 3. Analyze Commutes
    analyzed = analyze_student_commutes(
        students, 
        university_tk, 
        max_unnecessary_grade=max_grade,
        use_marginal_pt_emissions=marginal_emissions
    )
    
    # 4. Extract and display unnecessary trips
    print("--- IDENTIFIED UNNECESSARY TRIPS ---")
    unnecessary_records = [r for r in analyzed if r["unnecessary_trip"]]
    
    if not unnecessary_records:
        print("  No unnecessary trips found based on the current policy threshold.")
    else:
        for record in unnecessary_records:
            probs = record["mode_probabilities"]
            dist_str = f"{record['one_way_distance_km']:.1f} km" if record['one_way_distance_km'] else "Unknown"
            print(f"  Student: {record['student_id']:<6} | Course: {record['onoma_mathimatos']:<18} | Grade: {record['bathmos']} | Distance: {dist_str:<8} | "
                  f"Est. Mode: PT ({probs['public_transport']:.0%}), Car ({probs['car']:.0%}), Walk ({probs['walk_cycle']:.0%})")

    # 5. Monte Carlo Simulation for robust estimates
    print("\n--- ENVIRONMENTAL IMPACT REPORT ---")
    print(f"[*] Running {n_sims:,} Monte Carlo simulations to calculate statistical footprint distributions...")
    
    monte_carlo_summary = monte_carlo_unnecessary_trips_co2(
        analyzed, n_simulations=n_sims, random_seed=config["simulation"]["random_seed"], use_marginal_pt_emissions=marginal_emissions
    )
    
    total_mean = sum(stats['mean_kg'] for stats in monte_carlo_summary.values())
    print(f"\n=> TOTAL ESTIMATED CO2 EMISSIONS: {total_mean:.2f} kg CO2eq <=")
    print("\nBreakdown by Course (95% Confidence Intervals):")
    
    for course_name, stats in monte_carlo_summary.items():
        print(f"  - {course_name}: {stats['mean_kg']:.2f} kg "
              f"(Range: {stats['p5_kg']:.2f} kg -> {stats['p95_kg']:.2f} kg)")

    print("\n[Analysis Complete]")