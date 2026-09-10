import math
import random

def generate_course_distribution(
    a, 
    gamma=None, 
    apply_integer_snapping=None, 
    snapping_intensity=None, 
    stochastic=True
):
    """
    Generates the theoretical grade probability distribution (0-100%) for grades 0.0 to 10.0.
    Implements:
      - Mathematical base curve P(x) = C * e^(ax)
      - Rule 1: Integer Snapping (Stochastic rounding on failing marks < 4.0)
      - Rule 2: Pity Pass (Stochastic evaluator generosity gamma on borderline 4.0/4.5)
      - Rule 3: Ceiling at 10.0 (Universal scale ceiling and bonus accumulation for all courses)
      
    Note: Survivorship Bias (Rule 4) is modeled as a Student Agent Behavioral Dynamic 
    (Bimodal Engagement & Mastery Commitment) at the student population layer.
    """
    # 1. Domain (0.0, 0.5, 1.0 ... 10.0) + Theoretical grades > 10.0 for universal ceiling
    grades = [x * 0.5 for x in range(21)] 
    theoretical_grades = [x * 0.5 for x in range(21, 25)] # 10.5, 11.0, 11.5, 12.0
    all_grades = grades + theoretical_grades
    
    # 2. Base Probability (e^ax * C)
    raw_p = {x: math.exp(a * x) for x in all_grades}
    total_raw = sum(raw_p.values())
    base_p = {x: raw_p[x] / total_raw for x in all_grades} # C is (1 / total_raw)
    
    final_p = {x: base_p.get(x, 0.0) for x in grades}
    
    # 3. Determine Evaluator Characteristics (Stochastic Profile)
    if stochastic:
        # Rule 1: Integer Snapping probability based on course difficulty
        if apply_integer_snapping is None:
            if a <= -0.10: # Hard courses (high volume of weak papers)
                p_snap = 0.80
            elif a <= 0.0: # Medium courses
                p_snap = 0.50
            else: # Easy courses (rarely encounters < 4.0)
                p_snap = 0.20
            apply_integer_snapping = (random.random() < p_snap)
            
        if snapping_intensity is None:
            snapping_intensity = random.uniform(0.60, 1.0) if apply_integer_snapping else 0.0
            
        # Rule 2: Pity Pass generosity gamma
        if gamma is None:
            # 20% Strict, 60% Typical, 20% Generous
            evaluator_type = random.choices(["strict", "typical", "generous"], weights=[20, 60, 20])[0]
            if evaluator_type == "strict":
                gamma = random.uniform(0.25, 0.50)
            elif evaluator_type == "typical":
                gamma = random.uniform(0.70, 0.85)
            else: # generous
                gamma = random.uniform(0.85, 0.98)
    else:
        # Deterministic default fallback
        if apply_integer_snapping is None:
            apply_integer_snapping = True
        if snapping_intensity is None:
            snapping_intensity = 1.0
        if gamma is None:
            gamma = 0.80

    # 4. Apply Evaluator Rules
    
    # Rule 1: Integer Snapping (Professor avoids decimal precision on weak exams < 4.0)
    if apply_integer_snapping and snapping_intensity > 0:
        for decimal in [0.5, 1.5, 2.5, 3.5]:
            integer_below = decimal - 0.5
            integer_above = decimal + 0.5
            val = final_p[decimal] * snapping_intensity
            final_p[decimal] -= val
            final_p[integer_below] += val / 2.0
            final_p[integer_above] += val / 2.0
            
    # Rule 2: Pity Pass (Professor generously pushes borderline 4.0 and 4.5 papers to 5.0)
    if gamma > 0:
        pity_transfer_40 = final_p[4.0] * gamma
        pity_transfer_45 = final_p[4.5] * gamma
        final_p[4.0] -= pity_transfer_40
        final_p[4.5] -= pity_transfer_45
        final_p[5.0] += (pity_transfer_40 + pity_transfer_45)
        
    # Rule 3: Ceiling at 10.0 (Universal scale boundary and bonus accumulation for all courses)
    tail_sum = sum(base_p[x] for x in theoretical_grades)
    final_p[10.0] += tail_sum
    
    return final_p

def print_distribution(a_value, course_name):
    dist = generate_course_distribution(a_value)
    print(f"==================================================")
    print(f" COURSE: {course_name} (Coefficient a = {a_value})")
    print(f"==================================================")
    
    pass_prob = sum(p for g, p in dist.items() if g >= 5.0)
    fail_prob = sum(p for g, p in dist.items() if g < 5.0)
    
    print(f"Predicted Pass Rate (>=5.0): {pass_prob*100:5.1f}%")
    print(f"Predicted Fail Rate (<5.0):  {fail_prob*100:5.1f}%\n")
    
    print("Distribution (ASCII Chart):")
    for g in [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]:
        # Merge half points with whole points for visual representation (e.g. 5.0 + 5.5)
        prob = dist[g]
        if g < 10.0:
             prob += dist[g + 0.5]
             
        bar = "#" * int(prob * 100)
        print(f"Grade {g:2.0f} : {prob*100:5.1f}% | {bar}")
    print("\n")

if __name__ == '__main__':
    print("STARTING GRADE MODELING ENGINE...\n")
    
    # 6 Courses mathematically tuned to hit the exact pass rates from the real dataset
    print_distribution(-0.08, "COURSE_SEM1_MEDIUM") # Target: 51.9%
    print_distribution(-0.02, "COURSE_SEM2_MEDIUM") # Target: 59.4%
    print_distribution(-0.14, "COURSE_SEM2_HARD")   # Target: 44.1%
    print_distribution(0.33,  "COURSE_SEM2_EASY")   # Target: 95.3%
    print_distribution(-0.32, "COURSE_SEM4_HARD")   # Target: 25.8%
    print_distribution(0.15,  "COURSE_SEM4_EASY")   # Target: 85.4%
