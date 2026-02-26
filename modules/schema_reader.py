from modules.schema_manager import SchemaManager
from modules.clickhouse_client import get_ch_client
import streamlit as st

class SchemaReader:
    def __init__(self):
        self.manager = SchemaManager()
        self.client = get_ch_client()

    def get_table_schema(self, table_name):
        """
        Fetches columns from cache or ClickHouse using SchemaManager.
        Returns list of dicts with original and friendly names.
        """
        if not table_name:
            return []
        return self.manager.get_schema_with_mapping(table_name)

    def get_sample_data(self, table_name, limitCount=5):
        """
        Fetches sample data to help user understand the data format.
        """
        query = f"SELECT * FROM {table_name} LIMIT {limitCount}"
        return self.client.query_as_df(query)
