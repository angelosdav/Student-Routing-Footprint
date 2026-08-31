import math

def get_pass_rate(a, gamma=0.8):
    """
    Accepts a difficulty coefficient 'a' and returns the final pass rate (grades >= 5.0) 
    after applying the mathematical model and business rules.
    """
    grades = [x * 0.5 for x in range(21)]
    theoretical_grades = [x * 0.5 for x in range(21, 25)] if a > 0 else []
    all_grades = grades + theoretical_grades
    
    # Base formula e^(ax)
    raw_p = {x: math.exp(a * x) for x in all_grades}
    total_raw = sum(raw_p.values())
    base_p = {x: raw_p[x] / total_raw for x in all_grades}
    final_p = {x: base_p.get(x, 0.0) for x in grades}
    
    # Rule 1: Integer Snapping
    for decimal in [0.5, 1.5, 2.5, 3.5]:
        val = final_p[decimal]
        final_p[decimal] = 0.0
        final_p[decimal - 0.5] += val / 2.0
        final_p[decimal + 0.5] += val / 2.0
        
    # Rule 2: Pity Pass
    pity_40 = final_p[4.0] * gamma
    pity_45 = final_p[4.5] * gamma
    final_p[4.0] -= pity_40
    final_p[4.5] -= pity_45
    final_p[5.0] += (pity_40 + pity_45)
    
    # Rule 3: Ceiling Spike
    if a > 0:
        final_p[10.0] += sum(base_p[x] for x in theoretical_grades)
        
    # Return the sum of probabilities for grades 5.0 and above
    return sum(p for g, p in final_p.items() if g >= 5.0) * 100


def tune_courses():
    """
    Tests thousands of possible 'a' coefficients to find the one that perfectly
    matches the Target Pass Rate (the empirical rate from the data).
    """
    targets = [
        ('ΔΙΟΙΚΗΤΙΚΗ ΛΟΓΙΣΤΙΚΗ', 25.8), 
        ('ΣΤΑΤΙΣΤΙΚΗ ΕΠΙΧΕΙΡΗΣΕΩΝ', 44.1), 
        ('ΜΙΚΡΟΟΙΚΟΝΟΜΙΑ', 51.9), 
        ('ΕΙΣΑΓΩΓΗ ΣΤΟ ΔΙΚΑΙΟ', 59.4), 
        ('ΠΛΗΡΟΦΟΡΙΑΚΑ ΣΥΣΤΗΜΑΤΑ ΔΙΟΙΚΗΣΗΣ', 85.4), 
        ('ΜΑΚΡΟΟΙΚΟΝΟΜΙΑ', 95.3)
    ]

    print("Starting Auto-Tuning of Courses...\n")

    for name, target_pass_rate in targets:
        best_a = 0
        min_diff = 100 # Initial large error
        
        # Check all values of 'a' from -1.00 to +1.00 with a 0.01 step
        for i in range(-100, 100):
            test_a = i / 100.0
            
            # What pass rate does this test_a produce?
            simulated_pass_rate = get_pass_rate(test_a)
            
            # How far is it from the empirical target?
            diff = abs(simulated_pass_rate - target_pass_rate)
            
            # If closer, keep it as the best 'a'
            if diff < min_diff:
                min_diff = diff
                best_a = test_a
                
        final_rate = get_pass_rate(best_a)
        print(f"{name}:")
        print(f"  -> Ideal 'a' found: {best_a}")
        print(f"  -> Achieved: {final_rate:.1f}% (Empirical Target: {target_pass_rate}%)\n")

if __name__ == '__main__':
    tune_courses()
