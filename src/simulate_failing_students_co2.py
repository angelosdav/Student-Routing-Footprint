import csv
import json
import math
import random
import os
import requests
import concurrent.futures

# Base configuration
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTCODES_PATH = os.path.join(BASE_DIR, 'data', 'postcodes_attica.json')
DATASET_PATH = os.path.join(BASE_DIR, 'data', 'synthetic_students.csv')

# Load postcodes
with open(POSTCODES_PATH, 'r', encoding='utf-8') as f:
    local_postcodes = json.load(f)

# Destination campus coordinates map
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

TARGET_CAMPUS = "UNIWA Egaleo" # Change this to any key from the dictionary above!
DEST_LAT, DEST_LON = UNIVERSITIES.get(TARGET_CAMPUS, (37.9857, 23.6792))

# Emission factors in grams of CO2 per passenger kilometer
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

def pseudo_hash(s):
    # Deterministic hash for vehicle access (repeatability)
    h = 0
    for char in s:
        h = (h * 31 + ord(char)) & 0xFFFFFFFF
    return h

def fetch_osrm_route(port, profile, lat1, lon1, lat2, lon2):
    # Call local routing engine
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

def fetch_otp_transit_routes(lat1, lon1, lat2, lon2, date_str, time_str):
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
        res = requests.post(url, json={'query': query}, timeout=25.0)
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

def compute_student_route_and_co2(tk, is_peak=True, reverse=False, go_mode_id=None, is_driver=False):
    clean_tk = str(tk).strip()
    if clean_tk not in local_postcodes:
        return None

    coord = local_postcodes[clean_tk]
    lat, lon = coord['lat'], coord['lon']

    # Vehicle availability constraints
    h = pseudo_hash(clean_tk)
    
    if go_mode_id in ['transit1', 'transit2', 'foot']:
        has_car = False
        has_moto = False
    else:
        has_car = (h % 100 < 20)
        has_moto = ((h >> 2) % 100 < 15)

    # Route options
    if not reverse:
        osrm_car  = fetch_osrm_route(5000, "driving", lat, lon, DEST_LAT, DEST_LON)
        osrm_foot = fetch_osrm_route(5001, "walking", lat, lon, DEST_LAT, DEST_LON)
    else:
        osrm_car  = fetch_osrm_route(5000, "driving", DEST_LAT, DEST_LON, lat, lon)
        osrm_foot = fetch_osrm_route(5001, "walking", DEST_LAT, DEST_LON, lat, lon)

    # Fallback to straight line distance if engine fails
    straight_km = haversine_km(lat, lon, DEST_LAT, DEST_LON)
    car_dist_km  = osrm_car['dist_km'] if osrm_car else (straight_km * 1.25)
    raw_car_min  = osrm_car['dur_min'] if osrm_car else max(4.0, car_dist_km * 2.8)
    car_multiplier = 1.45 if is_peak else 1.0
    speed_correction = max(0.60, 1.0 - 0.015 * car_dist_km)
    car_dur_min  = raw_car_min * car_multiplier * speed_correction
    
    foot_dist_km = osrm_foot['dist_km'] if osrm_foot else (straight_km * 1.15)
    foot_dur_min = (osrm_foot['dur_min'] * 1.15) if osrm_foot else max(3.0, foot_dist_km * 13.0)

    # Query OpenTripPlanner for real transit itineraries
    date_str = "2026-07-22"
    time_str = "08:00" if is_peak else "14:00"
    
    otp_itineraries = []
    if not reverse:
        otp_itineraries = fetch_otp_transit_routes(lat, lon, DEST_LAT, DEST_LON, date_str, time_str)
    else:
        otp_itineraries = fetch_otp_transit_routes(DEST_LAT, DEST_LON, lat, lon, date_str, time_str)

    otp_online = otp_itineraries is not None
    if otp_itineraries is None:
        otp_itineraries = []

    # Parse OTP results to find transit1 (Metro + Bus) and transit2 (Direct Bus)
    t1_otp = None
    t2_otp = None
    
    for itin in otp_itineraries:
        legs = itin.get('legs', [])
        has_metro = any(leg['mode'] in ('SUBWAY', 'TRAM', 'RAIL') for leg in legs)
        has_bus = any(leg['mode'] == 'BUS' for leg in legs)
        
        # Calculate emissions
        co2_g = 0.0
        for leg in legs:
            dist_km = leg['distance'] / 1000.0
            if leg['mode'] == 'BUS':
                co2_g += dist_km * EF_BUS
            elif leg['mode'] in ('SUBWAY', 'TRAM', 'RAIL'):
                co2_g += dist_km * EF_METRO
        
        dur_min = itin['duration'] / 60.0
        wait_min = itin['waitingTime'] / 60.0
        walk_min = itin['walkTime'] / 60.0
        in_vehicle_min = max(0.0, dur_min - wait_min - walk_min)
        
        if has_metro: # Metro + Bus or Metro only
            if t1_otp is None or dur_min < t1_otp['dur']:
                t1_otp = {'dur': dur_min, 'wait': wait_min, 'walk': walk_min, 'in_vehicle': in_vehicle_min, 'co2': co2_g}
        elif has_bus: # Direct Bus only
            if t2_otp is None or dur_min < t2_otp['dur']:
                t2_otp = {'dur': dur_min, 'wait': wait_min, 'walk': walk_min, 'in_vehicle': in_vehicle_min, 'co2': co2_g}

    # Fallback parameters if OTP fails to find routes
    bus_dist_km  = straight_km * 1.15
    moto_dist_km = car_dist_km
    moto_dur_min = car_dur_min * 0.90

    # Wait and travel times defaults
    metro_wait_def = 4.0 if is_peak else 6.0
    bus_wait_def   = 7.0 if is_peak else 11.0

    # Transit 1 (Metro + Express Bus)
    if t1_otp:
        t1_total_dur = t1_otp['dur']
        t1_wait = t1_otp['wait']
        t1_walk = t1_otp['walk']
        t1_in_metro = t1_otp['in_vehicle'] * 0.5
        t1_in_bus = t1_otp['in_vehicle'] * 0.5
        t1_co2_grams = round(t1_otp['co2'])
    elif not otp_online:
        t1_in_metro  = max(3.0, straight_km * 1.5)
        t1_in_bus    = max(4.0, straight_km * 1.8)
        t1_wait      = metro_wait_def + bus_wait_def
        t1_walk      = 7.0
        t1_total_dur = t1_walk + t1_wait + t1_in_metro + t1_in_bus
        t1_co2_grams = round((bus_dist_km * 0.45 * EF_METRO) + (bus_dist_km * 0.55 * EF_BUS))
    else:
        t1_in_metro = 9999
        t1_in_bus = 9999
        t1_wait = 9999
        t1_walk = 9999
        t1_total_dur = 9999
        t1_co2_grams = 0

    # Transit 2 (Direct Bus)
    if t2_otp:
        t2_total_dur = t2_otp['dur']
        t2_wait = t2_otp['wait']
        t2_walk = t2_otp['walk']
        t2_in_bus = t2_otp['in_vehicle']
        t2_co2_grams = round(t2_otp['co2'])
    elif not otp_online:
        t2_in_bus    = max(8.0, straight_km * 3.1)
        t2_wait      = 9.0 if is_peak else 14.0
        t2_walk      = 9.0
        t2_total_dur = t2_walk + t2_wait + t2_in_bus
        t2_co2_grams = round(bus_dist_km * EF_BUS)
    else:
        t2_in_bus = 9999
        t2_wait = 9999
        t2_walk = 9999
        t2_total_dur = 9999
        t2_co2_grams = 0

    car_co2_grams  = round(car_dist_km * EF_CAR)
    moto_co2_grams = round(car_dist_km * EF_MOTO)
    foot_co2_grams = 0.0

    # Mode cost parameters
    parking_car  = 4.0 if not reverse else 0.0
    parking_moto = 1.0 if not reverse else 0.0
    
    C_car  = (car_dur_min + parking_car) + ((car_dist_km ** 0.85) * 0.35 * 5) + ASC_CAR
    # Added (car_dist_km * 0.8) as a fatigue/discomfort penalty for riding a motorcycle over long distances
    C_moto = (moto_dur_min + parking_moto) + ((car_dist_km ** 0.85) * 0.18 * 5) + (car_dist_km * 0.8) + ASC_MOTO
    C_t1   = (t1_in_metro + t1_in_bus + t1_walk) + (1.2 * t1_wait) + 4.0 + ASC_T1 if t1_total_dur < 9999 else 999999
    C_t2   = (t2_in_bus + t2_walk) + (1.2 * t2_wait) + ASC_T2 if t2_total_dur < 9999 else 999999
    C_foot = foot_dur_min * 1.1 + ASC_FOOT

    # Walk bias logic
    if foot_dist_km <= 0.6:
        foot_bias = -30.0
    elif foot_dist_km <= 1.0:
        foot_bias = -12.0
    elif foot_dist_km <= 1.5:
        foot_bias = 0.0
    else:
        foot_bias = 30.0

    C_foot_adj = C_foot + foot_bias

    # Mode probabilities
    if go_mode_id in ['car', 'moto'] and is_driver:
        exp_car  = 1.0 if go_mode_id == 'car' else 0.0
        exp_moto = 1.0 if go_mode_id == 'moto' else 0.0
        exp_t1   = 0.0
        exp_t2   = 0.0
        exp_foot = 0.0
    else:
        is_convenience_return = False
        if reverse and go_mode_id not in ['car', 'moto']:
            # 80% chance to stick to the same transit/foot mode due to convenience
            if random.random() < 0.80:
                is_convenience_return = True

        if is_convenience_return:
            exp_car  = 0.0
            exp_moto = 0.0
            exp_t1   = 1.0 if go_mode_id == 'transit1' else 0.0
            exp_t2   = 1.0 if go_mode_id == 'transit2' else 0.0
            exp_foot = 1.0 if go_mode_id == 'foot' else 0.0
        else:
            exp_car  = math.exp(-THETA * C_car) if (has_car and not reverse) else 0.0
            exp_moto = math.exp(-THETA * C_moto) if (has_moto and not reverse) else 0.0
            exp_t1   = math.exp(-THETA * C_t1)
            exp_t2   = math.exp(-THETA * C_t2)
            exp_foot = math.exp(-THETA * C_foot_adj)
            
            # Inbound Lift Probabilities (If they don't have a personal car parked at campus)
            if reverse:
                p_inbound_carpool = max(0.0, 0.20 - (0.005 * car_dist_km))
                p_inbound_pickup  = max(0.0, 0.08 - (0.007 * car_dist_km))
                p_total_lift = p_inbound_carpool + p_inbound_pickup
                
                if p_total_lift > 0 and random.random() < p_total_lift:
                    exp_car = 1.0
                    exp_moto = 0.0
                    exp_t1 = 0.0; exp_t2 = 0.0; exp_foot = 0.0

    sum_exp  = exp_car + exp_moto + exp_t1 + exp_t2 + exp_foot

    p_car  = exp_car / sum_exp
    p_moto = exp_moto / sum_exp
    p_t1   = exp_t1 / sum_exp
    p_t2   = exp_t2 / sum_exp
    p_foot = exp_foot / sum_exp

    total_p = p_car + p_moto + p_t1 + p_t2 + p_foot
    p_car  /= total_p
    p_moto /= total_p
    p_t1   /= total_p
    p_t2   /= total_p
    p_foot /= total_p

    # Mode selection
    modes = [
        ('transit1', 'Metro + Express Bus', p_t1, t1_co2_grams, t1_total_dur),
        ('transit2', 'Direct Bus',          p_t2, t2_co2_grams, t2_total_dur),
        ('car',      'Car',                 p_car, car_co2_grams, car_dur_min),
        ('moto',     'Motorcycle',          p_moto, moto_co2_grams, moto_dur_min),
        ('foot',     'Walking',             p_foot, foot_co2_grams, foot_dur_min)
    ]

    r = random.random()
    cumulative = 0.0
    chosen_mode = modes[0]

    for mode in modes:
        cumulative += mode[2]
        if r <= cumulative:
            chosen_mode = mode
            break

    # Dynamic Luck/Error simulation per trip leg
    p_traffic_incident = 0.40 if is_peak else 0.15
    max_traffic_delay = 25.0
    
    max_bus_wait_delay = 12.0 if is_peak else 25.0
    p_bus_late = 0.30 if is_peak else 0.15
    
    error_car = 0.0
    error_bus_wait = 0.0
    error_metro = 0.0
    
    # 1. Traffic Error
    if random.random() < p_traffic_incident:
        error_car = min(random.expovariate(1.0 / 10.0), max_traffic_delay)
    else:
        error_car = min(random.expovariate(1.0 / 2.0), 5.0)
        
    # 2. Bus Wait Error
    if random.random() < p_bus_late:
        error_bus_wait = min(random.expovariate(1.0 / (max_bus_wait_delay / 2.0)), max_bus_wait_delay)
    
    # 3. Metro Error
    if random.random() < 0.02:
        error_metro = min(random.expovariate(1.0 / 5.0), 10.0)

    chosen_id = chosen_mode[0]
    base_dur = chosen_mode[4]
    total_error = 0.0
    
    if chosen_id == 'car':
        total_error = error_car
    elif chosen_id == 'moto':
        total_error = error_car * 0.30
    elif chosen_id == 'transit1':
        total_error = error_bus_wait + error_car + error_metro
    elif chosen_id == 'transit2':
        total_error = error_bus_wait + error_car
    
    final_dur_min = base_dur + total_error
    
    # Context CO2 logic (Driver, Drop-off, Carpool)
    co2_multiplier = 1.0
    outbound_is_driver = False
    context_name = ""
    
    if not reverse and chosen_id in ['car', 'moto']:
        base_p_carpool = 0.25
        base_p_dropoff = 0.15
        p_carpool = max(0.0, base_p_carpool - (0.005 * car_dist_km))
        p_dropoff = max(0.0, base_p_dropoff - (0.007 * car_dist_km))
        p_driver = 1.0 - p_carpool - p_dropoff
        
        rand_context = random.random()
        if rand_context < p_driver:
            outbound_is_driver = True
            co2_multiplier = 1.0
            context_name = "Driver"
        elif rand_context < (p_driver + p_dropoff):
            outbound_is_driver = False
            co2_multiplier = 2.0
            context_name = "Drop-off"
        else:
            outbound_is_driver = False
            co2_multiplier = 0.5
            context_name = "Carpool"
            
    elif reverse and chosen_id == 'car' and not is_driver:
        p_inbound_carpool = max(0.0, 0.20 - (0.005 * car_dist_km))
        p_inbound_pickup  = max(0.0, 0.08 - (0.007 * car_dist_km))
        p_total_lift = p_inbound_carpool + p_inbound_pickup
        
        if p_total_lift <= 0:
            co2_multiplier = 0.5
            context_name = "Carpool"
        elif random.random() < (p_inbound_carpool / p_total_lift):
            co2_multiplier = 0.5
            context_name = "Carpool"
        else:
            co2_multiplier = 2.0
            context_name = "Pick-up"
            
    final_co2 = chosen_mode[3] * co2_multiplier

    return {
        'tk': clean_tk,
        'dist_km': round(car_dist_km, 2),
        'probabilities': {m[0]: round(m[2]*100, 1) for m in modes},
        'chosen_mode_id': chosen_mode[0],
        'chosen_mode_name': chosen_mode[1] + (f" [{context_name}]" if context_name else ""),
        'chosen_co2_grams': round(final_co2),
        'chosen_dur_min': round(final_dur_min, 1),
        'delay_min': round(total_error, 1),
        'is_driver': outbound_is_driver
    }

def run_simulation(min_grade=0.0, max_grade=2.0, dataset_path=DATASET_PATH):
    students_map = {}
    invalid_count = 0

    with open(dataset_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            grade_str = row['GRADE'].strip()
            tk = row['TK_KATOIKIA'].strip()

            try:
                grade_val = float(grade_str)
                if min_grade <= grade_val <= max_grade:
                    clean_tk = tk.strip()
                    if clean_tk in local_postcodes:
                        sid = row.get('STUDENT_ID', 'UNKNOWN')
                        if sid not in students_map:
                            students_map[sid] = {'tk': clean_tk, 'skill': row.get('SKILL', ''), 'courses': []}
                        students_map[sid]['courses'].append({'course': row['COURSE'], 'grade': grade_val})
                    else:
                        invalid_count += 1
            except ValueError:
                continue

    print(f"============================================================")
    print(f"Filters: Found {len(students_map)} unique students with failures in grade range {min_grade} to {max_grade}")
    if invalid_count > 0:
        print(f"Excluded {invalid_count} exams (postcode out of Attica or invalid)")
    print(f"============================================================\n")

    print("Checking Docker APIs connectivity...")
    test_osrm = fetch_osrm_route(5000, "driving", 37.9838, 23.7275, DEST_LAT, DEST_LON)
    test_otp = fetch_otp_transit_routes(37.9838, 23.7275, DEST_LAT, DEST_LON, "2026-07-22", "08:00")
    
    if test_osrm is None and (test_otp is None or len(test_otp) == 0):
        print(" -> [WARNING] Both OSRM and OTP are offline! The simulation will GUESS all routes.\n")
    else:
        print(" -> [OK] Connected to local Docker OSRM/OTP successfully.\n")

    total_co2_grams = 0.0
    mode_counts = {'transit1': 0, 'transit2': 0, 'car': 0, 'moto': 0, 'foot': 0}
    mode_co2    = {'transit1': 0, 'transit2': 0, 'car': 0, 'moto': 0, 'foot': 0}
    total_trips = 0

    def process_student(args):
        sid, s_data = args
        trips = []
        for fail in s_data['courses']:
            go_res = compute_student_route_and_co2(s_data['tk'], is_peak=True, reverse=False)
            if not go_res:
                continue
            ret_res = compute_student_route_and_co2(
                s_data['tk'], is_peak=False, reverse=True, 
                go_mode_id=go_res['chosen_mode_id'], is_driver=go_res['is_driver']
            )
            if ret_res:
                trips.append((fail, go_res, ret_res))
        return sid, s_data, trips

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(process_student, students_map.items())
        
        for res in results:
            if not res: continue
            sid, s_data, trips = res
            if not trips: continue
            
            student_total_co2 = 0
            
            print(f"[{sid}] (Postcode: {s_data['tk']} | Skill: {s_data['skill']}) - Failed {len(trips)} courses:")
            
            for trip in trips:
                fail, go_res, ret_res = trip
                total_trips += 1
                
                go_id = go_res['chosen_mode_id']
                ret_id = ret_res['chosen_mode_id']
                go_co2 = go_res['chosen_co2_grams']
                ret_co2 = ret_res['chosen_co2_grams']
                
                student_total_co2 += (go_co2 + ret_co2)
                total_co2_grams += (go_co2 + ret_co2)
                
                mode_counts[go_id] += 1
                mode_counts[ret_id] += 1
                mode_co2[go_id] += go_co2
                mode_co2[ret_id] += ret_co2
                
                print(f"   -> {fail['course']} (Grade: {fail['grade']})")
                print(f"      Outbound: {go_res['chosen_mode_name']:<24} | CO2: {go_co2:>4}g | Time: {go_res['chosen_dur_min']:>4.1f}m")
                print(f"      Inbound:  {ret_res['chosen_mode_name']:<24} | CO2: {ret_co2:>4}g | Time: {ret_res['chosen_dur_min']:>4.1f}m")
                
            print(f"   === Total Footprint for {sid}: {student_total_co2} g CO2eq ===\n")

    print(f"============================================================")
    print(f"CO2 Environmental Footprint Summary (Grades {min_grade} to {max_grade})")
    print(f"============================================================")
    print(f"Total students who failed at least 1 course:  {len(students_map)}")
    print(f"Total simulated exam trips (Round Trips):     {total_trips}")
    print(f"============================================================")
    print(f"Total CO2 emissions (Round Trip):             {total_co2_grams:,.0f} g CO2eq ({total_co2_grams/1000:.2f} kg CO2)")
    print(f"============================================================")
    print(f"Mode Choice Distribution (Legs):")
    total_legs = total_trips * 2
    for m_id, name in [('transit1', 'Metro + Bus'), ('transit2', 'Direct Bus'), 
                      ('car', 'Car'), ('moto', 'Motorcycle'), ('foot', 'Walking')]:
        cnt = mode_counts[m_id]
        pct = (cnt / total_legs * 100) if total_legs > 0 else 0
        co2_sum = mode_co2[m_id]
        print(f"   * {name:<24}: {cnt:>4} legs ({pct:>4.1f}%) | CO2: {co2_sum:>6} g")
    print(f"============================================================")

if __name__ == '__main__':
    # Run simulation for grades between 0.0 and 2.0
    run_simulation(0.0, 2.0)
