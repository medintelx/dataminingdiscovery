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

        # Ensure we always include mandatory ID columns if requested in prompt
        # but the caller might have missed them
        required_cols = list(columns)
        if "CLCL_ID" not in required_cols:
            required_cols.append("CLCL_ID")

        # Advanced Medical Field Bridge
        schema_mgr = SchemaManager()
        from modules.schema_manager import MAPPING
        
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
        ACT AS A MEDICAL CLAIMS DATABASE. NO CONVERSATION. JSON ONLY.
        Generate {count} synthetic healthcare claim records.
        
        CONCEPT: {self.rules.get('name')}
        
        STRICT SCHEMA (Use these exact INTERNAL names as keys):
        - CLCL_ID (MANDATORY)
        {map_str}
        
        JSON STRUCTURE:
        {{
          "claims": [
            {{
              "CLCL_ID": "CLM1002",
              "PAID_DT": "2024-01-01",
              "...": "...",
              "ground_truth": {{"is_overpayment": bool, "explanation": "..."}}
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
                ],
                response_format={"type": "json_object"}
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
            return self._fallback_generate(columns, count)

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
        4. Always end with "Other" (OTHER) for the audit final determination.

        OUTPUT JSON EXAMPLE:
        [
          {{"column": "CLCL_ID", "text": "Confirm Claim under review?", "type": "Yes/No"}},
          {{"column": "IPCD_MOD1_DER", "text": "Is modifier correct per policy?", "type": "Yes/No"}},
          {{"column": "OTHER", "text": "Final Determination", "type": "Multiple Choice", "options": ["Allowed", "Denied"]}}
        ]
        """

        try:
            print(f"Generating suggestions for concept: {self.rules.get('name')}")
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": "You are a senior healthcare audit expert. You strictly use Yes/No or Multiple Choice questions. No Free Text."},
                    {"role": "user", "content": prompt}
                ]
            )
            
            content = response.choices[0].message.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            raw_data = json.loads(content.strip())
            
            suggestions = []
            if isinstance(raw_data, list):
                suggestions = raw_data
            elif isinstance(raw_data, dict):
                for val in raw_data.values():
                    if isinstance(val, list):
                        suggestions = val
                        break

            final_suggestions = []
            if isinstance(suggestions, list):
                for item in suggestions:
                    if isinstance(item, dict) and "column" in item:
                        # ENFORCE: No Free Text. Map to Yes/No as safest fallback.
                        q_type = item.get("type", "Yes/No")
                        if q_type in ["Free Text", "Informational", "Unknown"]:
                            item["type"] = "Yes/No"
                        final_suggestions.append(item)
                
            return final_suggestions

        except Exception as e:
            print(f"Auto-questionnaire generation failed: {e}")
            return []

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
