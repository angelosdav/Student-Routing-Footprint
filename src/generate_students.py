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
    {"name": "COURSE_SEM1_MEDIUM", "a": -0.08, "tier": "Medium"},
    {"name": "COURSE_SEM2_MEDIUM", "a": -0.02, "tier": "Medium"},
    {"name": "COURSE_SEM2_HARD",   "a": -0.14, "tier": "Hard"},
    {"name": "COURSE_SEM2_EASY",   "a": 0.33,  "tier": "Easy"},
    {"name": "COURSE_SEM4_HARD",   "a": -0.32, "tier": "Hard"},
    {"name": "COURSE_SEM4_EASY",   "a": 0.15,  "tier": "Easy"}
]

STUDENT_CATEGORIES = {
    "Bad Students": {
        "skill_val": -0.08,
        "weight": 25,
        "commit_prob_hard_sem4": 0.02,
        "commit_prob_hard_sem2": 0.05
    },
    "Average Students": {
        "skill_val": 0.00,
        "weight": 50,
        "commit_prob_hard_sem4": 0.15,
        "commit_prob_hard_sem2": 0.30
    },
    "Good Students": {
        "skill_val": 0.08,
        "weight": 25,
        "commit_prob_hard_sem4": 0.55,
        "commit_prob_hard_sem2": 0.70
    }
}

def load_postcodes():
    """Loads the Attica postcodes from the JSON file."""
    with open(POSTCODES_PATH, 'r', encoding='utf-8') as f:
        return list(json.load(f).keys())

def get_random_student_category():
    """
    Assigns a student performance/behavior category based on the 3 discrete categories:
    - Bad Students (-0.08): 25% probability
    - Average Students (0.00): 50% probability (The majority / Mode)
    - Good Students (+0.08): 25% probability
    """
    cat_names = list(STUDENT_CATEGORIES.keys())
    weights = [STUDENT_CATEGORIES[c]["weight"] for c in cat_names]
    chosen_cat = random.choices(cat_names, weights=weights, k=1)[0]
    
    base_skill = STUDENT_CATEGORIES[chosen_cat]["skill_val"]
    noise = random.uniform(-0.02, 0.02)
    final_skill = max(-0.10, min(0.10, base_skill + noise))
    
    return chosen_cat, final_skill

def pick_grade_for_distribution(dist):
    """Picks a random grade based on the weighted probability distribution."""
    grades = list(dist.keys())
    weights = list(dist.values())
    return random.choices(grades, weights=weights, k=1)[0]

def generate_dataset(num_students=300):
    tks = load_postcodes()
    dataset = []

    print(f"Generating {num_students} synthetic students with 3 Performance Categories (Bad, Average, Good)...")
    
    for student_id in range(1, num_students + 1):
        # 1. Uniformly pick a TK (Postcode)
        student_tk = random.choice(tks)
        
        # 2. Assign the 3-category student performance trait
        cat_name, student_skill = get_random_student_category()
        cat_info = STUDENT_CATEGORIES[cat_name]
        
        # 3. Simulate exams for all 6 courses
        for course in COURSES:
            tier = course.get("tier", "Medium")
            base_a = course["a"]
            
            # Rule 4: Student Behavioral Dynamics (Survivorship Bias & Deep Study Decision across the 3 categories)
            # In very demanding / hard courses, students bifurcate in effort:
            # - Casual study leads to failure ([0-3]).
            # - Deep study / mastery commitment overcomes the hurdle and leads to excellence (6.5-8.5).
            if tier == "Hard":
                p_commit = cat_info["commit_prob_hard_sem4"] if course["name"] == "COURSE_SEM4_HARD" else cat_info["commit_prob_hard_sem2"]
                if random.random() < p_commit:
                    delta_a_mastery = 0.40 if course["name"] == "COURSE_SEM4_HARD" else 0.20
                    effective_a = base_a + student_skill + delta_a_mastery
                else:
                    penalty = -0.14 if course["name"] == "COURSE_SEM4_HARD" else -0.08
                    effective_a = base_a + student_skill + penalty
            else:
                # Standard difficulty modulation for medium and easy courses
                effective_a = base_a + student_skill
            
            # Generate the personalized probability curve for this student (applies Professor rules 1, 2, 3)
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
