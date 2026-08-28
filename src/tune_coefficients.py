import math

def get_pass_rate(a, gamma=0.8):
    """
    Δέχεται ένα 'a' (δυσκολία) και επιστρέφει το τελικό ποσοστό επιτυχίας (βαθμοί >= 5.0) 
    αφού εφαρμόσει το μαθηματικό μοντέλο και τους κανόνες μας.
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
        
    # Επιστρέφει το άθροισμα των πιθανοτήτων για βαθμούς 5.0 και άνω
    return sum(p for g, p in final_p.items() if g >= 5.0) * 100


def tune_courses():
    """
    Δοκιμάζει χιλιάδες πιθανά 'a' για να βρει αυτό που πετυχαίνει ακριβώς 
    το Target Pass Rate (το πραγματικό ποσοστό από τα δεδομένα).
    """
    targets = [
        ('ΔΙΟΙΚΗΤΙΚΗ ΛΟΓΙΣΤΙΚΗ', 25.8), 
        ('ΣΤΑΤΙΣΤΙΚΗ ΕΠΙΧΕΙΡΗΣΕΩΝ', 44.1), 
        ('ΜΙΚΡΟΟΙΚΟΝΟΜΙΑ', 51.9), 
        ('ΕΙΣΑΓΩΓΗ ΣΤΟ ΔΙΚΑΙΟ', 59.4), 
        ('ΠΛΗΡΟΦΟΡΙΑΚΑ ΣΥΣΤΗΜΑΤΑ ΔΙΟΙΚΗΣΗΣ', 85.4), 
        ('ΜΑΚΡΟΟΙΚΟΝΟΜΙΑ', 95.3)
    ]

    print("Ξεκινάει το Auto-Tuning των Μαθημάτων...\n")

    for name, target_pass_rate in targets:
        best_a = 0
        min_diff = 100 # Αρχικό τεράστιο σφάλμα
        
        # Ελέγχουμε όλες τις τιμές του 'a' από -1.00 έως +1.00 με βήμα 0.01
        for i in range(-100, 100):
            test_a = i / 100.0
            
            # Τι ποσοστό επιτυχίας βγάζει το μοντέλο μας με αυτό το test_a;
            simulated_pass_rate = get_pass_rate(test_a)
            
            # Πόσο απέχει από το πραγματικό νούμερο του Excel;
            diff = abs(simulated_pass_rate - target_pass_rate)
            
            # Αν είναι πιο κοντά, κράτα το ως το καλύτερο 'a'
            if diff < min_diff:
                min_diff = diff
                best_a = test_a
                
        final_rate = get_pass_rate(best_a)
        print(f"{name}:")
        print(f"  -> Ιδανικό 'a' βρέθηκε: {best_a}")
        print(f"  -> Επίτευξη: {final_rate:.1f}% (Πραγματικό Στόχος: {target_pass_rate}%)\n")

if __name__ == '__main__':
    tune_courses()
