import pandas as pd
import json
import os
import random
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

class LLMSyntheticGenerator:
    def __init__(self, concept_rules):
        self.rules = concept_rules
        self.api_key = os.getenv("AZURE_OPENAI_API_KEY")
        self.endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
        self.api_version = "2024-02-15-preview" # Defaulting to a stable preview version
        
        if self.api_key and self.endpoint:
            self.client = AzureOpenAI(
                api_key=self.api_key,
                azure_endpoint=self.endpoint,
                api_version=self.api_version
            )
        else:
            self.client = None

    def generate_quiz_data(self, columns, count=5):
        """
        Uses LLM to generate synthetic data for all specified columns.
        """
        if not self.client:
            return self._fallback_generate(columns, count)

        prompt = f"""
        Generate {count} synthetic healthcare claim records for a training quiz.
        Concept: {self.rules.get('name', 'General Claims')}
        Rules: {json.dumps(self.rules.get('overpayment_conditions', {}))}
        
        Required Columns: {", ".join(columns)}
        
        IMPORTANT:
        1. No PHI (Patient Health Information). Use realistic but fake names and IDs.
        2. Vary the scenarios based on the concept rules provided.
        3. Include at least 2 clear 'overpayment' cases and 3 'valid' cases.
        4. Output strictly as a JSON list of objects.
        5. Include a 'ground_truth' object for each row with:
           "is_overpayment": true/false,
           "explanation": "Short reason why"
        """

        try:
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            
            raw_data = json.loads(response.choices[0].message.content)
            # Assuming the LLM returns {"claims": [...]}
            claims = raw_data.get("claims", raw_data)
            if isinstance(claims, dict) and len(claims) == 1:
                claims = list(claims.values())[0]

            df = pd.DataFrame(claims)
            
            # Extract ground truth separately
            ground_truth = []
            for i, row in df.iterrows():
                gt = row.get("ground_truth", {})
                if not gt: # Fallback if LLM didn't nest it
                    gt = {
                        "is_overpayment": row.get("is_overpayment", False),
                        "explanation": row.get("explanation", "Standard processing")
                    }
                ground_truth.append({
                    "index": i,
                    "is_overpayment": gt.get("is_overpayment", False),
                    "explanation": gt.get("explanation", "LLM Generated Scenario")
                })
            
            # Clean up DF from ground_truth columns
            if "ground_truth" in df.columns:
                df = df.drop(columns=["ground_truth"])
            if "is_overpayment" in df.columns:
                df = df.drop(columns=["is_overpayment"])
            if "explanation" in df.columns:
                df = df.drop(columns=["explanation"])

            return df, ground_truth

        except Exception as e:
            print(f"LLM Generation failed: {e}")
            return self._fallback_generate(columns, count)

    def _fallback_generate(self, columns, count):
        # Very basic fallback if LLM/API fails
        data = []
        gt = []
        for i in range(count):
            row = {col: f"FAKE_{col}_{i}" for col in columns}
            if "Claim_ID" in columns: row["Claim_ID"] = f"CLM{1000+i}"
            if "PAID_AMT" in columns: row["PAID_AMT"] = round(random.uniform(50, 500), 2)
            data.append(row)
            gt.append({"index": i, "is_overpayment": random.choice([True, False]), "explanation": "Fallback random data"})
        return pd.DataFrame(data), gt
