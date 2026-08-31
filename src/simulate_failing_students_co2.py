import csv
import json
import math
import random
import os
import requests
import argparse
import time
from concurrent.futures import ThreadPoolExecutor

# Import grade distribution and random choice functions from grade_model
from grade_model import generate_course_distribution

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTCODES_PATH = os.path.join(BASE_DIR, 'data', 'postcodes_attica.json')
DATASET_PATH = os.path.join(BASE_DIR, 'data', 'synthetic_students.csv')

# Load postcodes
with open(POSTCODES_PATH, 'r', encoding='utf-8') as f:
    local_postcodes = json.load(f)

# Destination campus coordinates
UNIVERSITIES = {
    "UNIWA Egaleo": (37.9857, 23.6792),
    "EKPA Zografou": (37.9676, 23.7665),
    "EKPA Goudi": (37.9834, 23.7681),
    "EKPA Center": (37.9804, 23.7335),
    "EKPA Dafni": (37.9546, 23.7431),
    "EMP Zografou": (37.9760, 23.7840),
    "EMP Patision": (37.9877, 23.7313),
    "OPA Center": (37.9942, 23.7328),
    "OPA Evelpidon": (37.9961, 23.7381),
    "OPA Troias": (37.9985, 23.7345),
    "PADA Egaleo": (38.0031, 23.6758),
    "PADA Ralli": (37.9818, 23.6765),
    "PADA Alexandras": (37.9880, 23.7550),
    "PAPEI Center": (37.9416, 23.6528),
    "PAPEI Lampraki": (37.9415, 23.6552),
    "Panteion": (37.9602, 23.7196),
    "GPA Votanikos": (37.9827, 23.7051),
    "Harokopio": (37.9610, 23.7088),
    "ASKT Tavros": (37.9617, 23.6888),
    "Ikaron": (38.1091, 23.7828),
    "N. Dokimon": (37.9282, 23.6288),
    "Evelpidon": (37.8282, 23.7744)
}

TARGET_CAMPUS = "UNIWA Egaleo"
DEST_LAT, DEST_LON = UNIVERSITIES.get(TARGET_CAMPUS, (37.9857, 23.6792))

# Emission factors in grams of CO2 per passenger-kilometer
EF_CAR   = 120.0
EF_MOTO  = 70.0
EF_BUS   = 10.81
EF_METRO = 3.1
EF_FOOT  = 0.0

# Mode bias values (Alternative-Specific Constants)
ASC_CAR   = 6.0
ASC_MOTO  = 9.0
ASC_T1    = -4.0
ASC_T2    = -2.0
ASC_FOOT  = 0.0
THETA     = 0.09

# Course metadata: difficulty tiers and base coefficients
COURSES_META = {
    "ΔΙΟΙΚΗΤΙΚΗ ΛΟΓΙΣΤΙΚΗ": {"a": -0.32, "tier": "Hard"},
    "ΣΤΑΤΙΣΤΙΚΗ ΕΠΙΧΕΙΡΗΣΕΩΝ": {"a": -0.14, "tier": "Hard"},
    "ΜΙΚΡΟΟΙΚΟΝΟΜΙΑ": {"a": -0.08, "tier": "Medium"},
    "ΕΙΣΑΓΩΓΗ ΣΤΟ ΔΙΚΑΙΟ": {"a": -0.02, "tier": "Medium"},
    "ΠΛΗΡΟΦΟΡΙΑΚΑ ΣΥΣΤΗΜΑΤΑ ΔΙΟΙΚΗΣΗΣ": {"a": 0.15, "tier": "Easy"},
    "ΜΑΚΡΟΟΙΚΟΝΟΜΙΑ": {"a": 0.33, "tier": "Easy"}
}

# In-memory routing cache to allow thousands of fast Monte Carlo iterations
POSTCODE_CACHE = {}

def pseudo_hash(s):
    h = 0
    for char in s:
        h = (h * 31 + ord(char)) & 0xFFFFFFFF
    return h

def fetch_osrm_route(port, profile, lat1, lon1, lat2, lon2):
    url = f"http://localhost:{port}/route/v1/{profile}/{lon1},{lat1};{lon2},{lat2}"
    try:
        res = requests.get(url, params={"overview": "false"}, timeout=1.5)
        if res.status_code == 200:
            data = res.json()
            if data.get('code') == 'Ok' and data.get('routes'):
                r = data['routes'][0]
                return {
                    'dist_km': r['distance'] / 1000.0,
                    'dur_min': r['duration'] / 60.0
                }
    except Exception:
        pass
    return None

def fetch_otp_transit_routes(lat1, lon1, lat2, lon2, date_str="2026-07-22", time_str="08:00"):
    url = 'http://localhost:8080/otp/routers/default/index/graphql'
    query = f"""
    {{
      plan(
        from: {{ lat: {lat1}, lon: {lon1} }},
        to: {{ lat: {lat2}, lon: {lon2} }},
        date: "{date_str}",
        time: "{time_str}",
        walkReluctance: 5.0
      ) {{
        itineraries {{
          startTime
          duration
          waitingTime
          walkTime
          legs {{
            mode
            duration
            distance
            transitLeg
          }}
        }}
      }}
    }}
    """
    try:
        res = requests.post(url, json={'query': query}, timeout=15.0)
        if res.status_code == 200:
            data = res.json()
            if 'data' in data and data['data'].get('plan'):
                return data['data']['plan'].get('itineraries', [])
    except Exception:
        pass
    return None

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def preload_postcode_routes(postcodes_to_cache):
    """Pre-calculates and caches the routing data for postcodes in parallel."""
    print(f"Pre-caching routing network for {len(postcodes_to_cache)} distinct Attica postcodes...")
    
    def cache_single_tk(tk):
        clean_tk = str(tk).strip()
        if clean_tk not in local_postcodes:
            return clean_tk, None
        
        coord = local_postcodes[clean_tk]
        lat, lon = coord['lat'], coord['lon']
        
        # 1. Car route
        osrm_car = fetch_osrm_route(5000, "driving", lat, lon, DEST_LAT, DEST_LON)
        if not osrm_car:
            d_hav = haversine_km(lat, lon, DEST_LAT, DEST_LON)
            osrm_car = {'dist_km': d_hav * 1.35, 'dur_min': (d_hav * 1.35 / 35.0) * 60.0}
            
        # 2. Foot route
        osrm_foot = fetch_osrm_route(5001, "foot", lat, lon, DEST_LAT, DEST_LON)
        if not osrm_foot:
            d_hav = haversine_km(lat, lon, DEST_LAT, DEST_LON)
            osrm_foot = {'dist_km': d_hav * 1.25, 'dur_min': (d_hav * 1.25 / 4.8) * 60.0}
            
        # 3. Transit route
        otp_itins = fetch_otp_transit_routes(lat, lon, DEST_LAT, DEST_LON)
        
        return clean_tk, {
            'lat': lat,
            'lon': lon,
            'car': osrm_car,
            'foot': osrm_foot,
            'otp': otp_itins
        }

    start_t = time.time()
    with ThreadPoolExecutor(max_workers=16) as executor:
        results = executor.map(cache_single_tk, postcodes_to_cache)
        for tk, data in results:
            if data:
                POSTCODE_CACHE[tk] = data
                
    elapsed = time.time() - start_t
    print(f" -> Successfully cached {len(POSTCODE_CACHE)} postcodes in {elapsed:.2f}s.\n")

def compute_student_leg_fast(clean_tk, is_peak=True, reverse=False, go_mode_id=None, is_driver=False):
    """Calculates one trip leg using in-memory cached routes and stochastic MNL logic."""
    if clean_tk not in POSTCODE_CACHE:
        return None

    cached = POSTCODE_CACHE[clean_tk]
    osrm_car = cached['car']
    osrm_foot = cached['foot']
    otp_itins = cached['otp']
    
    car_dist_km = osrm_car['dist_km']
    car_dur_min = osrm_car['dur_min'] * (1.35 if is_peak else 1.0)
    
    foot_dist_km = osrm_foot['dist_km']
    foot_dur_min = osrm_foot['dur_min']

    h = pseudo_hash(clean_tk)
    if go_mode_id in ['transit1', 'transit2', 'foot']:
        has_car = False
        has_moto = False
    else:
        has_car = (h % 100 < 20)
        has_moto = ((h >> 2) % 100 < 15)

    # Inbound Convenience Bias
    if reverse and go_mode_id:
        p_stay = 0.80
        p_lift_carpool = max(0.0, 0.20 - (0.005 * car_dist_km))
        p_lift_pickup  = max(0.0, 0.08 - (0.007 * car_dist_km))
        total_lift_p = p_lift_carpool + p_lift_pickup

        if go_mode_id in ['transit1', 'transit2', 'foot']:
            if random.random() < (1.0 - p_stay):
                if random.random() < (p_lift_pickup / (total_lift_p + 1e-6)):
                    return {
                        'mode_id': 'car',
                        'mode_name': 'Car [Pick-up]',
                        'co2_grams': round(car_dist_km * EF_CAR * 2.0),
                        'dur_min': round(car_dur_min, 1),
                        'dist_km': round(car_dist_km, 2),
                        'is_driver': False
                    }
                else:
                    return {
                        'mode_id': 'car',
                        'mode_name': 'Car [Carpool]',
                        'co2_grams': round(car_dist_km * EF_CAR * 0.5),
                        'dur_min': round(car_dur_min, 1),
                        'dist_km': round(car_dist_km, 2),
                        'is_driver': False
                    }

    modes = []
    
    # Mode 1: Car
    if has_car or (reverse and not go_mode_id):
        cost_car = car_dur_min + 5.0 + ASC_CAR
        co2_car = car_dist_km * EF_CAR
        modes.append(('car', 'Car', cost_car, co2_car, car_dur_min, 'road'))

    # Mode 2: Moto
    if has_moto or (reverse and not go_mode_id):
        dur_moto = car_dur_min * 0.8
        cost_moto = dur_moto + 2.0 + ASC_MOTO
        co2_moto = car_dist_km * EF_MOTO
        modes.append(('moto', 'Motorcycle', cost_moto, co2_moto, dur_moto, 'road'))

    # Modes 3 & 4: Public Transit
    if otp_itins and len(otp_itins) > 0:
        for idx, itin in enumerate(otp_itins[:2]):
            t_id = f"transit{idx+1}"
            dur = itin['duration'] / 60.0
            wait = itin.get('waitingTime', 0) / 60.0
            walk = itin.get('walkTime', 0) / 60.0
            
            legs = itin.get('legs', [])
            num_transfers = max(0, sum(1 for leg in legs if leg.get('transitLeg')) - 1)
            
            c_co2 = 0.0
            has_rail = False
            for leg in legs:
                d_km = leg.get('distance', 0) / 1000.0
                m = leg.get('mode', '').upper()
                if m in ['SUBWAY', 'METRO', 'TRAM', 'RAIL']:
                    c_co2 += d_km * EF_METRO
                    has_rail = True
                elif m == 'BUS':
                    c_co2 += d_km * EF_BUS
            
            asc = ASC_T1 if has_rail else ASC_T2
            penalty_transfer = num_transfers * (10.0 if not is_peak else 6.0)
            cost_t = (dur - wait - walk) + 1.2 * wait + 1.5 * walk + penalty_transfer + asc
            t_name = "Metro + Bus" if has_rail else "Direct Bus"
            modes.append((t_id, t_name, cost_t, c_co2, dur, 'transit'))
    else:
        # Fallback Transit
        d_transit = car_dist_km * 1.25
        dur_t1 = (d_transit / 25.0) * 60.0 + 8.0
        cost_t1 = dur_t1 + 1.2 * 5.0 + 1.5 * 5.0 + 8.0 + ASC_T1
        co2_t1 = (d_transit * 0.7 * EF_METRO) + (d_transit * 0.3 * EF_BUS)
        modes.append(('transit1', 'Metro + Bus', cost_t1, co2_t1, dur_t1, 'transit'))

    # Mode 5: Walking
    if foot_dist_km <= 3.5:
        cost_foot = foot_dur_min * 1.5 + ASC_FOOT
        modes.append(('foot', 'Walking', cost_foot, 0.0, foot_dur_min, 'walk'))

    # Multinomial Logit Choice Probability
    min_cost = min(m[2] for m in modes)
    exp_utils = [math.exp(-THETA * (m[2] - min_cost)) for m in modes]
    sum_exp = sum(exp_utils)
    probs = [u / sum_exp for u in exp_utils]

    # Weighted random selection
    rand_val = random.random()
    cum = 0.0
    chosen_idx = 0
    for i, p in enumerate(probs):
        cum += p
        if rand_val <= cum:
            chosen_idx = i
            break

    chosen_mode = modes[chosen_idx]
    chosen_id = chosen_mode[0]
    base_dur = chosen_mode[4]

    # Stochastic Delay Error
    delay_error = random.expovariate(1.0 / (4.5 if is_peak else 2.5))
    final_dur_min = base_dur + delay_error

    # Context CO2 logic (Driver, Drop-off, Carpool)
    co2_multiplier = 1.0
    outbound_is_driver = False
    context_name = ""

    if not reverse and chosen_id in ['car', 'moto']:
        p_carpool = max(0.0, 0.25 - (0.005 * car_dist_km))
        p_dropoff = max(0.0, 0.15 - (0.007 * car_dist_km))
        p_driver = 1.0 - p_carpool - p_dropoff
        
        rand_context = random.random()
        if rand_context < p_driver:
            outbound_is_driver = True
            co2_multiplier = 1.0
            context_name = "Driver"
        elif rand_context < (p_driver + p_dropoff):
            co2_multiplier = 2.0
            context_name = "Drop-off"
        else:
            co2_multiplier = 0.5
            context_name = "Carpool"
            
    elif reverse and chosen_id == 'car' and not is_driver:
        p_inbound_carpool = max(0.0, 0.20 - (0.005 * car_dist_km))
        p_inbound_pickup  = max(0.0, 0.08 - (0.007 * car_dist_km))
        p_total_lift = p_inbound_carpool + p_inbound_pickup
        
        if p_total_lift <= 0 or random.random() < (p_inbound_carpool / p_total_lift):
            co2_multiplier = 0.5
            context_name = "Carpool"
        else:
            co2_multiplier = 2.0
            context_name = "Pick-up"

    final_co2 = chosen_mode[3] * co2_multiplier

    return {
        'mode_id': chosen_id,
        'mode_name': chosen_mode[1] + (f" [{context_name}]" if context_name else ""),
        'co2_grams': round(final_co2),
        'dur_min': round(final_dur_min, 1),
        'dist_km': round(car_dist_km, 2),
        'is_driver': outbound_is_driver
    }

def classify_skill(skill_val):
    """Categorizes numeric student skill into the 5 discrete archetypes."""
    val = float(skill_val)
    if val <= -0.075:
        return "Apathetic (-0.10)"
    elif val <= -0.025:
        return "Below Average (-0.05)"
    elif val <= 0.025:
        return "Average (0.00)"
    elif val <= 0.075:
        return "Above Average (+0.05)"
    else:
        return "Excellent (+0.10)"

def load_failing_students(min_grade=0.0, max_grade=2.0, dataset_path=DATASET_PATH):
    """Reads synthetic_students.csv and extracts students with severe failures."""
    students_map = {}
    with open(dataset_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            grade_val = float(row['GRADE'].strip())
            tk = row['TK_KATOIKIA'].strip()
            
            if min_grade <= grade_val <= max_grade and tk in local_postcodes:
                sid = row.get('STUDENT_ID', 'UNKNOWN')
                skill = float(row.get('SKILL', 0.0))
                course = row['COURSE'].strip()
                
                if sid not in students_map:
                    students_map[sid] = {
                        'tk': tk,
                        'skill': skill,
                        'skill_class': classify_skill(skill),
                        'failed_courses': []
                    }
                students_map[sid]['failed_courses'].append({
                    'course': course,
                    'initial_grade': grade_val,
                    'tier': COURSES_META.get(course, {}).get('tier', 'Medium'),
                    'base_a': COURSES_META.get(course, {}).get('a', 0.0)
                })
    return students_map

def run_single_simulation(students_map, max_retakes=6, learning_rate=0.05):
    """
    Executes one complete Monte Carlo simulation run with the Retake Loop.
    Returns aggregated metrics for this iteration.
    """
    total_co2_grams = 0.0
    total_round_trips = 0
    mode_counts = {'transit1': 0, 'transit2': 0, 'car': 0, 'moto': 0, 'foot': 0}
    
    tier_stats = {
        'Hard': {'attempts': 0, 'co2': 0.0, 'courses_count': 0},
        'Medium': {'attempts': 0, 'co2': 0.0, 'courses_count': 0},
        'Easy': {'attempts': 0, 'co2': 0.0, 'courses_count': 0}
    }
    
    skill_stats = {
        "Apathetic (-0.10)": {'students': 0, 'co2': 0.0, 'attempts': 0, 'failed_courses': 0},
        "Below Average (-0.05)": {'students': 0, 'co2': 0.0, 'attempts': 0, 'failed_courses': 0},
        "Average (0.00)": {'students': 0, 'co2': 0.0, 'attempts': 0, 'failed_courses': 0},
        "Above Average (+0.05)": {'students': 0, 'co2': 0.0, 'attempts': 0, 'failed_courses': 0},
        "Excellent (+0.10)": {'students': 0, 'co2': 0.0, 'attempts': 0, 'failed_courses': 0}
    }
    
    # Track unique students per skill class
    for s_info in students_map.values():
        s_class = s_info['skill_class']
        skill_stats[s_class]['students'] += 1

    for sid, s_info in students_map.items():
        tk = s_info['tk']
        skill = s_info['skill']
        s_class = s_info['skill_class']
        
        student_co2 = 0.0
        student_attempts = 0

        for fail in s_info['failed_courses']:
            course_name = fail['course']
            tier = fail['tier']
            base_a = fail['base_a']
            
            tier_stats[tier]['courses_count'] += 1
            skill_stats[s_class]['failed_courses'] += 1
            
            # Retake loop for this course
            attempts = 0
            passed = False
            
            while attempts < max_retakes and not passed:
                attempts += 1
                student_attempts += 1
                total_round_trips += 1
                
                # Outbound commute
                go_res = compute_student_leg_fast(tk, is_peak=True, reverse=False)
                if not go_res:
                    continue
                # Inbound commute
                ret_res = compute_student_leg_fast(
                    tk, is_peak=False, reverse=True, 
                    go_mode_id=go_res['mode_id'], is_driver=go_res['is_driver']
                )
                if not ret_res:
                    continue

                trip_co2 = go_res['co2_grams'] + ret_res['co2_grams']
                total_co2_grams += trip_co2
                student_co2 += trip_co2
                
                tier_stats[tier]['co2'] += trip_co2
                mode_counts[go_res['mode_id']] += 1
                mode_counts[ret_res['mode_id']] += 1
                
                # Simulate the exam retake grade
                # Experience/Preparation boost: Scales dynamically with the student's study archetype
                # Apathetic barely studies (+0.02), while Excellent students prepare seriously (+0.18)
                skill_learning_rates = {
                    "Apathetic (-0.10)": 0.02,
                    "Below Average (-0.05)": 0.04,
                    "Average (0.00)": 0.06,
                    "Above Average (+0.05)": 0.10,
                    "Excellent (+0.10)": 0.18
                }
                boost_rate = skill_learning_rates.get(s_class, learning_rate)
                # First retake also gets an immediate preparation boost for top students (they study seriously)
                initial_prep_boost = 0.24 if skill > 0.075 else (0.12 if skill > 0.025 else (0.05 if skill > -0.025 else 0.0))
                
                effective_a = base_a + skill + initial_prep_boost + (attempts - 1) * boost_rate
                dist = generate_course_distribution(effective_a)
                
                # Roll new grade
                grades = list(dist.keys())
                weights = list(dist.values())
                new_grade = random.choices(grades, weights=weights, k=1)[0]
                
                if new_grade >= 5.0:
                    passed = True

            tier_stats[tier]['attempts'] += attempts

        skill_stats[s_class]['co2'] += student_co2
        skill_stats[s_class]['attempts'] += student_attempts

    return {
        'total_co2_kg': total_co2_grams / 1000.0,
        'total_round_trips': total_round_trips,
        'avg_co2_per_student_kg': (total_co2_grams / len(students_map) / 1000.0) if students_map else 0.0,
        'mode_counts': mode_counts,
        'tier_stats': tier_stats,
        'skill_stats': skill_stats
    }

def calculate_distribution_stats(values):
    """Calculates comprehensive statistical indicators for a list of numbers."""
    if not values:
        return {}
    
    n = len(values)
    sorted_v = sorted(values)
    mean_val = sum(values) / n
    variance = sum((x - mean_val)**2 for x in values) / (n - 1) if n > 1 else 0.0
    std_dev = math.sqrt(variance)
    
    def percentile(p):
        idx = int(p * (n - 1))
        return sorted_v[idx]
    
    p5  = percentile(0.05)
    p25 = percentile(0.25)
    median = percentile(0.50)
    p75 = percentile(0.75)
    p95 = percentile(0.95)
    iqr = p75 - p25
    
    # 95% Confidence Interval for the Mean
    margin_of_error = 1.96 * (std_dev / math.sqrt(n)) if n > 0 else 0.0
    ci_lower = mean_val - margin_of_error
    ci_upper = mean_val + margin_of_error
    
    return {
        'mean': mean_val,
        'std': std_dev,
        'median': median,
        'min': sorted_v[0],
        'max': sorted_v[-1],
        'p5': p5,
        'p25': p25,
        'p75': p75,
        'p95': p95,
        'iqr': iqr,
        'ci95': (ci_lower, ci_upper)
    }

def run_monte_carlo_experiments(num_runs=1000, min_grade=0.0, max_grade=2.0, max_retakes=6, learning_rate=0.05):
    """Executes N Monte Carlo iterations and displays comprehensive statistical summaries."""
    print("=" * 70)
    print(f"  MONTE CARLO MOBILITY & CO2 SIMULATION ENGINE ({num_runs:,} ITERATIONS)")
    print(f"  Target Campus: {TARGET_CAMPUS} | Grade Filter: [{min_grade} - {max_grade}]")
    print(f"  Retake Mechanism: Max {max_retakes} attempts | Learning Boost: +{learning_rate} 'a'/attempt")
    print("=" * 70 + "\n")

    # Load dataset
    students_map = load_failing_students(min_grade, max_grade)
    if not students_map:
        print("Error: No failing students found matching the criteria!")
        return

    print(f"Loaded {len(students_map)} unique failing students from dataset.")
    distinct_postcodes = list({s['tk'] for s in students_map.values()})
    
    # Pre-cache all routes
    preload_postcode_routes(distinct_postcodes)

    print(f"Executing {num_runs:,} Monte Carlo simulation runs in memory...")
    start_sim_time = time.time()
    
    sim_co2_kg = []
    sim_avg_student_co2_kg = []
    sim_trips = []
    
    global_mode_counts = {'transit1': 0, 'transit2': 0, 'car': 0, 'moto': 0, 'foot': 0}
    
    # Tier aggregators
    tier_attempts = {'Hard': [], 'Medium': [], 'Easy': []}
    tier_co2_kg   = {'Hard': [], 'Medium': [], 'Easy': []}
    
    # Skill aggregators
    skill_attempts = {k: [] for k in ["Apathetic (-0.10)", "Below Average (-0.05)", "Average (0.00)", "Above Average (+0.05)", "Excellent (+0.10)"]}
    skill_co2_kg   = {k: [] for k in ["Apathetic (-0.10)", "Below Average (-0.05)", "Average (0.00)", "Above Average (+0.05)", "Excellent (+0.10)"]}

    # Milestone intervals
    report_step = max(1, num_runs // 10)

    for run_idx in range(1, num_runs + 1):
        res = run_single_simulation(students_map, max_retakes, learning_rate)
        
        sim_co2_kg.append(res['total_co2_kg'])
        sim_avg_student_co2_kg.append(res['avg_co2_per_student_kg'])
        sim_trips.append(res['total_round_trips'])
        
        for m, cnt in res['mode_counts'].items():
            global_mode_counts[m] += cnt
            
        for tier, data in res['tier_stats'].items():
            avg_att = (data['attempts'] / data['courses_count']) if data['courses_count'] > 0 else 0.0
            tier_attempts[tier].append(avg_att)
            tier_co2_kg[tier].append(data['co2'] / 1000.0)
            
        for s_class, data in res['skill_stats'].items():
            if data['students'] > 0:
                avg_s_co2 = (data['co2'] / data['students']) / 1000.0
                avg_s_att = (data['attempts'] / data['failed_courses']) if data['failed_courses'] > 0 else 0.0
                skill_co2_kg[s_class].append(avg_s_co2)
                skill_attempts[s_class].append(avg_s_att)
                
        if run_idx % report_step == 0 or run_idx == num_runs:
            pct = (run_idx / num_runs) * 100
            print(f"  -> Progress: {run_idx:>6,}/{num_runs:,} runs ({pct:>5.1f}%) completed...")

    sim_duration = time.time() - start_sim_time
    print(f"\nAll {num_runs:,} iterations completed in {sim_duration:.2f} seconds ({num_runs/sim_duration:.0f} runs/sec)!\n")

    # Statistical summaries
    stats_co2 = calculate_distribution_stats(sim_co2_kg)
    stats_student_co2 = calculate_distribution_stats(sim_avg_student_co2_kg)
    stats_trips = calculate_distribution_stats(sim_trips)

    # 1. Global Environmental Footprint Report
    print("=" * 75)
    print("  1. GLOBAL ENVIRONMENTAL FOOTPRINT & MOBILITY STATISTICS")
    print("=" * 75)
    print(f"{'Metric':<35} | {'Mean ± SD':<20} | {'Median [P25 - P75]':<20}")
    print("-" * 75)
    print(f"{'Total CO2 Footprint (kg)':<35} | {stats_co2['mean']:>7.2f} ± {stats_co2['std']:<9.2f} | {stats_co2['median']:>7.2f} [{stats_co2['p25']:.1f} - {stats_co2['p75']:.1f}]")
    print(f"{'Avg CO2 per Student (kg)':<35} | {stats_student_co2['mean']:>7.2f} ± {stats_student_co2['std']:<9.2f} | {stats_student_co2['median']:>7.2f} [{stats_student_co2['p25']:.1f} - {stats_student_co2['p75']:.1f}]")
    print(f"{'Total Round Trips Generated':<35} | {stats_trips['mean']:>7.1f} ± {stats_trips['std']:<9.1f} | {stats_trips['median']:>7.1f} [{stats_trips['p25']:.0f} - {stats_trips['p75']:.0f}]")
    print("-" * 75)
    print(f"-> 95% Confidence Interval (Total CO2): [{stats_co2['ci95'][0]:.2f} kg - {stats_co2['ci95'][1]:.2f} kg]")
    print(f"-> Full Simulation Range (Total CO2):    Min: {stats_co2['min']:.2f} kg | Max: {stats_co2['max']:.2f} kg (IQR: {stats_co2['iqr']:.2f} kg)")
    print(f"-> 90% Confidence Interval Range:        P5: {stats_co2['p5']:.2f} kg  | P95: {stats_co2['p95']:.2f} kg\n")

    # 2. Breakdown by Course Difficulty Tier
    print("=" * 75)
    print("  2. BREAKDOWN BY COURSE DIFFICULTY TIER")
    print("=" * 75)
    print(f"{'Difficulty Tier':<16} | {'Courses Included':<30} | {'Mean Attempts':<14} | {'Mean CO2 (kg)':<14}")
    print("-" * 75)
    tier_desc = {
        'Hard': 'Λογιστική, Στατιστική',
        'Medium': 'Μικροοικονομία, Δίκαιο',
        'Easy': 'Πληροφοριακά, Μακροοικονομία'
    }
    for tier in ['Hard', 'Medium', 'Easy']:
        att_stat = calculate_distribution_stats(tier_attempts[tier])
        co2_stat = calculate_distribution_stats(tier_co2_kg[tier])
        co2_pct = (co2_stat['mean'] / stats_co2['mean'] * 100) if stats_co2['mean'] > 0 else 0
        print(f"{tier:<16} | {tier_desc[tier]:<30} | {att_stat['mean']:>6.2f} ± {att_stat['std']:<4.2f}   | {co2_stat['mean']:>6.2f} kg ({co2_pct:>4.1f}%)")
    print("\n")

    # 3. Breakdown by Student Skill Archetype
    print("=" * 75)
    print("  3. BREAKDOWN BY STUDENT SKILL PROFILE")
    print("=" * 75)
    print(f"{'Student Archetype':<26} | {'Sample %':<10} | {'Mean Attempts/Course':<20} | {'Mean CO2/Student':<16}")
    print("-" * 75)
    skill_pcts = {
        "Apathetic (-0.10)": "20%",
        "Below Average (-0.05)": "25%",
        "Average (0.00)": "30% (Mode)",
        "Above Average (+0.05)": "15%",
        "Excellent (+0.10)": "10%"
    }
    for s_class in ["Apathetic (-0.10)", "Below Average (-0.05)", "Average (0.00)", "Above Average (+0.05)", "Excellent (+0.10)"]:
        if skill_co2_kg[s_class]:
            att_stat = calculate_distribution_stats(skill_attempts[s_class])
            co2_stat = calculate_distribution_stats(skill_co2_kg[s_class])
            print(f"{s_class:<26} | {skill_pcts[s_class]:<10} | {att_stat['mean']:>6.2f} ± {att_stat['std']:<4.2f} attempts   | {co2_stat['mean']:>6.2f} ± {co2_stat['std']:<4.2f} kg")
    print("\n")

    # 4. Modal Split across all simulations
    print("=" * 75)
    print("  4. TRANSPORTATION MODE DISTRIBUTION (ACROSS ALL RUNS)")
    print("=" * 75)
    total_legs = sum(global_mode_counts.values())
    mode_names = [
        ('transit1', 'Metro + Bus'),
        ('transit2', 'Direct Bus'),
        ('car', 'Car (Driver / Carpool / Lift)'),
        ('moto', 'Motorcycle'),
        ('foot', 'Walking')
    ]
    for m_id, m_label in mode_names:
        cnt = global_mode_counts.get(m_id, 0)
        pct = (cnt / total_legs * 100) if total_legs > 0 else 0
        bar = "█" * int(pct / 2.5)
        print(f"  * {m_label:<32}: {pct:>5.1f}% | {bar}")
    print("=" * 75 + "\n")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Multi-run Monte Carlo simulation for university student mobility & CO2 emissions.")
    parser.add_argument('-n', '--runs', type=int, default=1000, help="Number of Monte Carlo simulation runs (default: 1000)")
    parser.add_argument('--min-grade', type=float, default=0.0, help="Minimum initial failing grade (default: 0.0)")
    parser.add_argument('--max-grade', type=float, default=2.0, help="Maximum initial failing grade (default: 2.0)")
    parser.add_argument('--max-retakes', type=int, default=6, help="Maximum retake attempts before loop termination (default: 6)")
    parser.add_argument('--learning-rate', type=float, default=0.05, help="Learning boost to 'a' per retake attempt (default: 0.05)")

    args = parser.parse_args()

    run_monte_carlo_experiments(
        num_runs=args.runs,
        min_grade=args.min_grade,
        max_grade=args.max_grade,
        max_retakes=args.max_retakes,
        learning_rate=args.learning_rate
    )
