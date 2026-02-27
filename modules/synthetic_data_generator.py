import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta

class SyntheticDataGenerator:
    def __init__(self, concept_rules):
        self.rules = concept_rules
        # Use internal database names to match schema and questionnaire
        self.columns = [
            "CLCL_ID", "PRPR_ID", "MEME_CK", "FROM_DT", 
            "IPCD_ID", "IPCD_MOD1_DER", "UNITS", "PAID_AMT", "CUR_STS"
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
            "CLCL_ID": f"CLM{1000 + idx}",
            "PRPR_ID": "PROV_99",
            "MEME_CK": "MEM_88",
            "FROM_DT": "2024-01-15",
            "IPCD_ID": "00100",
            "IPCD_MOD1_DER": mod,
            "UNITS": 1,
            "PAID_AMT": 150.00,
            "CUR_STS": "Paid"
        }

        if scenario_type == "mismatch":
            base_claim["IPCD_MOD1_DER"] = "ZZ"

        return base_claim
