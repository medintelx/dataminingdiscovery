import clickhouse_connect
import pandas as pd
import streamlit as st
import os

class ClickHouseClient:
    def __init__(self, host=None, port=None, username=None, password=None, database=None):
        # Helper to get config from st.secrets or os.getenv
        def get_cfg(key, default=None):
            if key in st.secrets:
                return st.secrets[key]
            return os.getenv(key, default)

        self.host = host or get_cfg("CLICKHOUSE_HOST", "localhost")
        raw_port = port or get_cfg("CLICKHOUSE_PORT", 8443)
        self.port = int(raw_port)
        self.username = username or get_cfg("CLICKHOUSE_USER", "default")
        self.password = password or get_cfg("CLICKHOUSE_PASSWORD", "")
        self.database = database or get_cfg("CLICKHOUSE_DATABASE", "default")
        self.client = None

    def connect(self):
        try:
            self.client = clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                database=self.database,
                secure=True if self.port == 8443 else False
            )
            return True
        except Exception as e:
            st.error(f"Failed to connect to ClickHouse: {e}")
            return False

    def query_as_df(self, query):
        if not self.client:
            if not self.connect():
                return pd.DataFrame()
        try:
            result = self.client.query(query)
            return pd.DataFrame(result.result_rows, columns=result.column_names)
        except Exception as e:
            st.error(f"Query failed: {e}")
            return pd.DataFrame()

    def get_columns(self, table_name):
        query = f"DESCRIBE TABLE {table_name}"
        df = self.query_as_df(query)
        if not df.empty:
            return df['name'].tolist()
        # Fallback columns if connection fails (for demo/development)
        return ["Claim_ID", "Provider_ID", "Member_ID", "DOS", "Modifier", "Units", "Paid_Amt", "Paid_Dt"]

@st.cache_resource
def get_ch_client():
    return ClickHouseClient()
