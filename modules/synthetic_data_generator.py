import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta

class SyntheticDataGenerator:
    def __init__(self, concept_rules):
        self.rules = concept_rules
        self.columns = [
            "Claim_ID", "Provider_ID", "Member_ID", "DOS", 
            "Proc_Code", "Modifier", "Units", "Paid_Amt", "Status"
        ]

    def generate_quiz_data(self, count=5):
        """
        Generates synthetic claim rows based on the concept rules.
        """
        data = []
        ground_truth = []

        # Scenarios: 0: Valid Pair, 1: Duplicate Overpayment (Exact Match), 2: Valid Single
        scenarios = [
            {"type": "valid_pair", "is_overpayment_idx": []}, # Both allowed
            {"type": "exact_duplicate", "is_overpayment_idx": [1]}, # Second is overpayment
            {"type": "modifier_mismatch", "is_overpayment_idx": [0]}, # Billed wrong
        ]

        scenario = random.choice(scenarios)
        
        for i in range(count):
            if scenario["type"] == "valid_pair" and i < 2:
                # Row 0: QX, Row 1: QK (Concurrent - Valid)
                row = self._generate_row(i, "valid", mod="QX" if i == 0 else "QK")
            elif scenario["type"] == "exact_duplicate" and i < 2:
                # Both rows identical attributes (Invalid)
                row = self._generate_row(i, "valid", mod="QX")
            elif scenario["type"] == "modifier_mismatch" and i == 0:
                # Wrong modifier
                row = self._generate_row(i, "mismatch")
            else:
                row = self._generate_row(i, "valid")

            data.append(row)
            is_overpayment = i in scenario["is_overpayment_idx"]
            
            explanation = "Valid concurrent billing (QX/QK)." if scenario["type"] == "valid_pair" and i < 2 else \
                          "Exact attribute match (Duplicate)." if scenario["type"] == "exact_duplicate" and i == 1 else \
                          "Invalid modifier for Concept." if i in scenario["is_overpayment_idx"] else \
                          "Standard processing."

            ground_truth.append({
                "index": i,
                "is_overpayment": is_overpayment,
                "explanation": explanation
            })

        return pd.DataFrame(data), ground_truth

    def _generate_row(self, idx, scenario_type, mod="QX"):
        base_claim = {
            "Claim_ID": f"CLM{1000 + idx}",
            "Provider_ID": "PROV_99",
            "Member_ID": "MEM_88",
            "DOS": "2024-01-15",
            "Proc_Code": "00100",
            "Modifier": mod,
            "Units": 1,
            "Paid_Amt": 150.00,
            "Status": "Paid"
        }

        if scenario_type == "mismatch":
            base_claim["Modifier"] = "ZZ"

        return base_claim
