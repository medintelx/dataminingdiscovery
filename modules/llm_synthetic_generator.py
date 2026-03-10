import pandas as pd
import json
import os
import random
import streamlit as st
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

class LLMSyntheticGenerator:
    def __init__(self, concept_rules):
        self.rules = concept_rules
        
        # Helper to get config from st.secrets or os.getenv
        def get_cfg(key, default=None):
            if key in st.secrets:
                return st.secrets[key]
            return os.getenv(key, default)

        self.api_key = get_cfg("AZURE_OPENAI_API_KEY")
        self.endpoint = get_cfg("AZURE_OPENAI_ENDPOINT")
        self.deployment = get_cfg("AZURE_OPENAI_DEPLOYMENT")
        self.api_version = "2024-02-15-preview" 
        
        if self.api_key and self.endpoint:
            self.client = AzureOpenAI(
                api_key=self.api_key,
                azure_endpoint=self.endpoint,
                api_version=self.api_version,
                timeout=3.0,
                max_retries=0
            )
        else:
            self.client = None

    def generate_quiz_data(self, columns, count=5):
        """
        Uses LLM to generate synthetic data for all specified columns.
        """
        if not self.client:
            return self._fallback_generate(columns, count)

        # Ensure we always include mandatory ID columns if requested in prompt
        # but the caller might have missed them
        required_cols = list(columns)
        if "CLCL_ID" not in required_cols:
            required_cols.append("CLCL_ID")

        # Advanced Medical Field Bridge
        from modules.schema_manager import MAPPING, SchemaManager
        schema_mgr = SchemaManager()
        
        # 1. Build a massive bridge: All Friendly Names -> Internal Names
        global_bridge = {}
        for internal, friendly in MAPPING.items():
            global_bridge[friendly.lower()] = internal
            global_bridge[internal.lower()] = internal

        # 2. Add common "AI Hallucination" aliases for healthcare
        aliases = {
            "claim_id": "CLCL_ID", "claimid": "CLCL_ID", "claim id": "CLCL_ID", "clm_id": "CLCL_ID",
            "dos": "FROM_DT", "date of service": "FROM_DT", "service date": "FROM_DT",
            "modifier": "IPCD_MOD1_DER", "mod": "IPCD_MOD1_DER", "proc_mod": "IPCD_MOD1_DER",
            "proc_code": "IPCD_ID", "procedure": "IPCD_ID", "cpt": "IPCD_ID", "procedure_code": "IPCD_ID",
            "member_id": "MEME_CK", "member identifier": "MEME_CK",
            "paid": "PAID_AMT", "paid_amount": "PAID_AMT", "amount": "PAID_AMT",
            "status": "CUR_STS", "claim_status": "CUR_STS"
        }
        global_bridge.update(aliases)

        column_map = {col: schema_mgr.get_friendly_name(col) for col in required_cols}
        map_str = "\n".join([f"- {internal}: {friendly}" for internal, friendly in column_map.items()])

        prompt = f"""
        ACT AS A MEDICAL CLAIMS DATABASE EXPERT. NO CONVERSATION. JSON ONLY.
        Generate {count} HIGHLY REALISTIC synthetic healthcare claim records.
        
        CONCEPT: {self.rules.get('name')}
        CONCEPT RULES TO IMPLEMENT: {json.dumps(self.rules.get('overpayment_conditions', {}))}
        
        CRITICAL GENERATION INSTRUCTIONS:
        1. DO NOT use generic fake data like "Member_1" or "123". Use extremely realistic medical data (actual HCPCS/CPT codes, actual standard modifiers like RT/LT/59, realistic NPIs).
        2. Financials must be realistic. Allow amounts should be mathematically sound relative to Charge amounts.
        3. Dates must be logically sequenced and valid.
        4. Data must explicitly test the boundaries of the rules provided above (e.g., generate one claim that perfectly fails the rules, and one that perfectly passes the rules using realistic CPT code variations).
        5. CRITICAL RELATION MATCHER: If generating {count} claims to test a concept like duplicate billing or related logic, you MUST use the EXACT SAME Member ID (MEME_CK), Provider ID (PRPR_ID), and Date of Service across all generated objects so they definitively link together in the scenario as positive matches!
        
        STRICT SCHEMA (Use these exact INTERNAL names as keys):
        - CLCL_ID (MANDATORY, e.g. "CLM-2024-88492A")
        {map_str}
        
        JSON STRUCTURE:
        {{
          "claims": [
            {{
              "CLCL_ID": "CLM-2024-88492A",
              "PAID_DT": "2024-03-15",
              "ground_truth": {{"is_overpayment": true, "explanation": "Detailed explanation of why this specific claim passed or failed the rules based on the realistic codes used."}}
            }}
          ]
        }}
        """

        try:
            print(f"DEBUG: Requesting synthetic data for: {required_cols}")
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": "You are a database. You strictly output JSON mapping to the requested internal keys."},
                    {"role": "user", "content": prompt}
                ]
            )
            
            raw_data = json.loads(response.choices[0].message.content)
            claims = raw_data.get("claims", [])
            if not claims and isinstance(raw_data, list): claims = raw_data
            
            df = pd.DataFrame(claims)
            print(f"DEBUG: Raw LLM Columns: {df.columns.tolist()}")

            # 3. AGGRESSIVE RECOVERY - Map AI Keys back to Database Keys
            rename_dict = {}
            for col in df.columns:
                col_clean = str(col).strip().lower().replace(" ", "_")
                if col_clean in global_bridge:
                    target_internal = global_bridge[col_clean]
                    rename_dict[col] = target_internal
            
            if rename_dict:
                df = df.rename(columns=rename_dict)
                print(f"DEBUG: Repaired Columns: {df.columns.tolist()}")

            # 4. EMERGENCY IDENTITY GUARD
            if "CLCL_ID" not in df.columns:
                # If we missed it but have something like "Claim_ID", it's already caught by aliases.
                # Last resort: fallback to row indices if AI completely failed.
                df["CLCL_ID"] = [f"CLM-{1000+i}" for i in range(len(df))]

            # 5. EXTRACT GROUND TRUTH
            ground_truth = []
            for i, row in df.iterrows():
                gt = row.get("ground_truth", {})
                ground_truth.append({
                    "index": i,
                    "is_overpayment": gt.get("is_overpayment", False) if isinstance(gt, dict) else False,
                    "explanation": gt.get("explanation", "Scenario generated by AI") if isinstance(gt, dict) else "Review required"
                })
            
            # Clean up metadata
            if "ground_truth" in df.columns:
                df = df.drop(columns=["ground_truth"])
            
            return df, ground_truth

        except Exception as e:
            print(f"LLM Generation failed: {e}")
            return self._fallback_generate(required_cols, count)

    def generate_suggested_questionnaire(self, available_columns):
        """
        Uses LLM to analyze concept rules and suggest the most relevant columns and questions.
        """
        if not self.client:
            return []

        # Create a detailed column reference for the LLM
        schema_reference = "\n".join([f"- {c['friendly']} (Internal Name: {c['original']})" for c in available_columns])
        
        prompt = f"""
        Design a medical audit questionnaire for the concept: "{self.rules.get('name')}"
        Rules: {json.dumps(self.rules.get('overpayment_conditions', {}))}

        Schema to pick from:
        {schema_reference}
        - Other (Internal Name: OTHER)

        INSTRUCTIONS:
        1. Select 5-7 relevant columns.
        2. DO NOT use "Free Text" or "Informational" types. Use only "Yes/No" or "Multiple Choice".
        3. For identification fields like CLCL_ID, ask a verification question like "Is this the correct claim?".
        4. Always return EXACTLY 2 claim examples based on the generated questionnaire.
        5. CRITICAL: If the concept involves duplicate detection or checking attributes across related claims, the 2 claim examples MUST have identical values for correlation IDs like Member ID (MEME_CK), Provider ID (PRPR_ID), or Dates to accurately represent a matching condition!
        
        OUTPUT JSON EXAMPLE:
        {{
          "questions": [
            {{"column": "CLCL_ID", "text": "Confirm Claim under review?", "type": "Yes/No"}},
            {{"column": "IPCD_MOD1_DER", "text": "Is modifier correct per policy?", "type": "Yes/No"}}
          ],
          "examples": [
            {{"CLCL_ID": "CLM-001", "IPCD_MOD1_DER": "59"}},
            {{"CLCL_ID": "CLM-002", "IPCD_MOD1_DER": "RT"}}
          ]
        }}
        """

        try:
            print(f"Generating suggestions for concept: {self.rules.get('name')}")
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": "You are a senior healthcare audit expert. You output strictly JSON containing 'questions' and 'examples' lists."},
                    {"role": "user", "content": prompt}
                ]
            )
            
            raw_data = json.loads(response.choices[0].message.content)
            
            suggestions = raw_data.get("questions", [])
            examples = raw_data.get("examples", [])

            final_suggestions = []
            if isinstance(suggestions, list):
                for item in suggestions:
                    if isinstance(item, dict) and "column" in item:
                        # ENFORCE: No Free Text. Map to Yes/No as safest fallback.
                        q_type = item.get("type", "Yes/No")
                        if q_type in ["Free Text", "Informational", "Unknown"]:
                            item["type"] = "Yes/No"
                        final_suggestions.append(item)
                
            return final_suggestions, examples

        except Exception as e:
            print(f"Auto-questionnaire generation failed: {e}")
            return [], []

    def _fallback_generate(self, columns, count):
        # Realistic fallback mapping similar to Standard Rule-based SyntheticDataGenerator in the quiz section
        data = []
        gt = []
        import datetime
        
        # Pre-assign base correlation identities for the entire batch to mimic true positive relation scenarios
        base_mem = f"MEM_88{random.randint(100, 999)}"
        base_prov = f"PROV_{random.randint(10, 99)}"
        base_dt = (datetime.datetime(2024, 1, 15) + datetime.timedelta(days=random.randint(0, 100))).strftime("%Y-%m-%d")
        base_diag = random.choice(["J01.90", "E11.9", "I10", "Z00.00"])
        
        for i in range(count):
            row = {}
            for col in columns:
                col_upper = str(col).strip().upper()
                if "ID" in col_upper and "CL" in col_upper:
                    row[col] = f"CLM-{random.randint(20000, 99999)}"
                elif "MEM" in col_upper:
                    row[col] = base_mem  # Matching Relation
                elif "PRV" in col_upper or "PRPR" in col_upper:
                    row[col] = base_prov # Matching Relation
                elif "DT" in col_upper or "DATE" in col_upper:
                    row[col] = base_dt   # Matching Relation
                elif "MOD" in col_upper:
                    row[col] = random.choice(["QX", "RT", "LT", "59", "25"])
                elif "AMT" in col_upper or "PAID" in col_upper:
                    row[col] = round(random.uniform(50.00, 500.00), 2)
                elif "UNIT" in col_upper:
                    row[col] = random.choice([1, 2, 3])
                elif "STS" in col_upper or "STATUS" in col_upper:
                    row[col] = "Paid"
                elif "PROC" in col_upper or "IPCD" in col_upper or "CPT" in col_upper:
                    row[col] = random.choice(["00100", "99213", "99214", "A0425"])
                elif "DIAG" in col_upper or "ICD" in col_upper:
                    row[col] = base_diag # Matching Relation
                else:
                    row[col] = f"SAMPLE_{col}_{i}"
            
            data.append(row)
            gt.append({"index": i, "is_overpayment": random.choice([True, False]), "explanation": "Generated from local fallback positive logic matching algorithm"})
        return pd.DataFrame(data), gt
