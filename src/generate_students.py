import json
import random
import csv
import os

# Import the grade generation engine we built
from grade_model import generate_course_distribution

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTCODES_PATH = os.path.join(BASE_DIR, 'data', 'postcodes_attica.json')
OUTPUT_CSV_PATH = os.path.join(BASE_DIR, 'data', 'synthetic_students.csv')

COURSES = [
    {"name": "COURSE_SEM1_MEDIUM", "a": -0.08},
    {"name": "COURSE_SEM2_MEDIUM", "a": -0.02},
    {"name": "COURSE_SEM2_HARD",   "a": -0.14},
    {"name": "COURSE_SEM2_EASY",   "a": 0.33},
    {"name": "COURSE_SEM4_HARD",   "a": -0.32},
    {"name": "COURSE_SEM4_EASY",   "a": 0.15}
]

def load_postcodes():
    """Loads the Attica postcodes from the JSON file."""
    with open(POSTCODES_PATH, 'r', encoding='utf-8') as f:
        return list(json.load(f).keys())

def get_random_skill():
    """
    Assigns a skill level based on 5 discrete categories.
    - Apathetic (-0.10): 20% probability
    - Below Average (-0.05): 25% probability
    - Average (0.0): 30% probability (The majority / Mode)
    - Above Average (+0.05): 15% probability
    - Excellent (+0.10): 10% probability
    Total Negative: 45% | Total Positive: 25% (Left-Skewed distribution)
    """
    categories = [-0.10, -0.05, 0.0, 0.05, 0.10]
    weights = [20, 25, 30, 15, 10]
    
    # Pick category based on weights
    base_skill = random.choices(categories, weights=weights, k=1)[0]
    
    # Add minimal uniform noise (+/- 0.02) so not everyone has the exact same decimal
    noise = random.uniform(-0.02, 0.02)
    final_skill = base_skill + noise
    
    # Strict boundaries
    return max(-0.10, min(0.10, final_skill))

def pick_grade_for_distribution(dist):
    """Picks a random grade based on the weighted probability distribution."""
    grades = list(dist.keys())
    weights = list(dist.values())
    # random.choices returns a list, so we take the first element [0]
    return random.choices(grades, weights=weights, k=1)[0]

def generate_dataset(num_students=300):
    tks = load_postcodes()
    dataset = []

    print(f"Generating {num_students} synthetic students with uniform postcode distribution...")
    
    for student_id in range(1, num_students + 1):
        # 1. Uniformly pick a TK (Postcode)
        student_tk = random.choice(tks)
        
        # 2. Assign the internal student "skill" trait
        student_skill = get_random_skill()
        
        # 3. Simulate exams for all 6 courses
        for course in COURSES:
            # The core logic: Course Difficulty + Student Skill
            effective_a = course["a"] + student_skill
            
            # Generate the personalized probability curve for this student
            dist = generate_course_distribution(effective_a)
            
            # Roll the loaded dice to get the grade
            grade = pick_grade_for_distribution(dist)
            
            dataset.append({
                "STUDENT_ID": f"STU_{student_id:03d}",
                "TK_KATOIKIA": student_tk,
                "COURSE": course["name"],
                "GRADE": grade,
                "SKILL": round(student_skill, 2),
                "EFFECTIVE_A": round(effective_a, 2)
            })

    # Save to CSV
    with open(OUTPUT_CSV_PATH, 'w', newline='', encoding='utf-8-sig') as csvfile:
        fieldnames = ["STUDENT_ID", "TK_KATOIKIA", "COURSE", "GRADE", "SKILL", "EFFECTIVE_A"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in dataset:
            writer.writerow(row)
            
    print(f"Dataset successfully saved to: {OUTPUT_CSV_PATH}")
    print(f"Total rows generated: {len(dataset)} (300 students x 6 courses)")

if __name__ == "__main__":
    generate_dataset(300)
