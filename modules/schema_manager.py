import sqlite3
import pandas as pd
import os
from modules.clickhouse_client import get_ch_client

MAPPING = {
    "MEME_CK": "Member Contrived Key",
    "MEME_SFX": "Member Suffix",
    "MEME_FIRST_NAME": "Member First Name",
    "MEME_LAST_NAME": "Member Last Name",
    "GRGR_CK": "Group Identifier",
    "SGSG_CK": "Subgroup Contrived Key",
    "CLCL_ID": "Claim Identifier",
    "CDML_SEQ_NO": "Line-Item Sequence Number",
    "LOBD_ID": "Line of Business Identifier",
    "SEPC_DESC": "Service Pricing ID Description",
    "SEPC_PRICE_ID": "Service Pricing Identifier",
    "RCRC_ID": "Revenue Code",
    "PSCD_ID": "Place of Service Identifier",
    "IPCD_ID": "Procedure Code",
    "IPCD_DESC": "Procedure Description",
    "IPCD_GEN_ID_2": "Alternate Procedure Identifier 1",
    "NASG_NUMBER": "Ambulatory Surgical Center payment group number",
    "IDCD_ID": "Diagnosis Code",
    "IDCD_ID_REL": "Related Diagnosis Identifier",
    "FROM_DT": "From Date",
    "TO_DT": "To Date",
    "CHG_AMT": "Amount Charged",
    "HCPCS_AMT": "HCPCS/Rate",
    "CONSIDER_CHG": "Considered Charge",
    "ALLOW": "Allowable Amount",
    "UNITS": "Number of Units/Days",
    "UNITS_ALLOW": "Units/Days Allowable",
    "DED_AMT": "Deductible Amount",
    "COPAY_AMT": "Copay Amount",
    "COINS_AMT": "Coinsurance Amount",
    "PAID_AMT": "Line Item Paid Amount",
    "IP_PRICE": "Procedure Table Price",
    "PRICE_IND": "Line Item Pricing Indicator",
    "CAP_IND": "Capitated Line-Item Indicator",
    "SB_PYMT_AMT": "Medical Line Item Subscriber Payment Amount",
    "PR_PYMT_AMT": "Medical Line Item Provider Payment Amount",
    "IPCD_MOD1_DER": "Procedure Modifier One Code",
    "IPCD_MOD2": "Second Procedure Modifier",
    "IPCD_MOD3": "Third Procedure Modifier",
    "IPCD_MOD4": "Fourth Procedure Modifier",
    "CDCB_COB_TYPE": "COB/Medicare Type",
    "CDCB_COB_AMT": "COB/Medicare Paid Amount",
    "CLM_ROW_ID": "Claim Row Identifier",
    "PROC_CODE_DER": "Procedure Code (Derived)",
    "CL_TYPE": "Claim Type",
    "CL_SUB_TYPE": "Claim Sub Type",
    "CUR_STS": "Claim Status",
    "PAID_DT": "Claim Paid Date",
    "LOW_SVC_DT": "Claim's Earliest From Date",
    "HIGH_SVC_DT": "Claim's Latest To Date",
    "CLCL_ID_ADJ_TO": "Corrected Claim Identifier",
    "CLCL_ID_ADJ_FROM": "Adjusted Claim Identifier",
    "CLCL_ID_CRTE_FROM": "Claim Identifier of the Adjusted Claim",
    "MEME_SEX": "Member's Gender",
    "PRPR_ID": "Servicing Provider",
    "SRVC_PROV_TIN": "Servicing Provider Tax ID",
    "PRPR_NPI": "National Practitioner Identifier",
    "PA_ACCT_NO": "Patient Account Number",
    "CLCL_TOT_CHG": "Claim Total Charge",
    "CLCL_TOT_PAYABLE": "Claim Total Payable",
    "PDDS_PROD_TYPE": "Product Type",
    "PDDS_MCTR_BCAT": "Business Category",
    "MICRO_ID": "MICROFILM ID",
    "RELHP_FROM_DT": "Beginning date of hospitalization",
    "RELHP_TO_DT": "Ending date of hospitalization",
    "CLHP_ADM_TYP": "Type of Admission",
    "CLHP_ADM_DT": "Admission Date",
    "CLHP_DC_STAT": "Discharge Status",
    "CLHP_DC_DT": "Discharge Date",
    "CLHP_MED_REC_NO": "Medical Record Number",
    "CLHP_IPCD_METH": "Procedure Coding Methodology",
    "DRG": "DRG code",
    "CLHP_ADM_SOURCE": "Admission Source",
    "CLHP_ICD_QUAL_IND": "ICD Qualifier",
    "CLCB_COB_AMT": "Primary Carrier Payment Amount",
    "AUDIT_10": "Audit number (10 pos)",
    "AUDIT_SFX": "Claim Audit Suffix",
    "BILL_TYPE_CODE": "Bill Type Code",
    "BUSINESS_LINE": "Business Line (MCR/MCD/etc)",
    "PAR_STATUS": "Provider Participation Status",
    "SGSG_ID": "Subgroup Identifier",
    "SRVC_TYP_CODE": "Service Type Code",
    "CLHO_SEQ_NO": "UB92 Line-Item Sequence Number",
    "CLHO_OCC_CODE": "UB92 Occurrence Code",
    "CLHO_OCC_FROM_DT": "UB92 Occurrence From Date",
    "CLHO_OCC_TO_DT": "UB92 Occurrence To Date",
    "CLCK_PAYEE_IND": "Payee Indicator",
    "CKPY_PAY_DT": "Pay Date",
    "ROOM_TYPE": "Room Type",
    "OTHER": "Other"
}

DB_PATH = "config/schema_cache.db"

class SchemaManager:
    def __init__(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH)
        self._create_table()

    def _create_table(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_cache (
                table_name TEXT PRIMARY KEY,
                columns_json TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def get_friendly_name(self, col_name):
        return MAPPING.get(col_name.upper(), col_name)

    def get_cached_schema(self, table_name):
        cursor = self.conn.cursor()
        cursor.execute("SELECT columns_json FROM schema_cache WHERE table_name = ?", (table_name,))
        row = cursor.fetchone()
        if row:
            import json
            return json.loads(row[0])
        return None

    def cache_schema(self, table_name, columns):
        import json
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO schema_cache (table_name, columns_json, last_updated)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (table_name, json.dumps(columns)))
        self.conn.commit()

    def get_schema_with_mapping(self, table_name):
        """
        Tries to get schema from cache, else fetches from ClickHouse.
        Returns a list of dicts with 'original' and 'friendly' names.
        """
        cached = self.get_cached_schema(table_name)
        if not cached:
            client = get_ch_client()
            original_cols = client.get_columns(table_name)
            self.cache_schema(table_name, original_cols)
            cached = original_cols
        
        return [{"original": col, "friendly": self.get_friendly_name(col)} for col in cached]
