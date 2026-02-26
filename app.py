import streamlit as st
import json
import os
import pandas as pd
from dotenv import load_dotenv
from modules.ui_components import apply_custom_css, render_header, render_concept_card, show_score
from modules.schema_reader import SchemaReader
from modules.questionnaire_builder import QuestionnaireBuilder
from modules.synthetic_data_generator import SyntheticDataGenerator
from modules.evaluation_engine import EvaluationEngine
from modules.schema_manager import SchemaManager
from modules.llm_synthetic_generator import LLMSyntheticGenerator

# Load environment variables
load_dotenv()

# Page Config
st.set_page_config(page_title="Claims Concept Quiz", page_icon="📝", layout="wide")
apply_custom_css()

# Session State Initialization
if "current_concept" not in st.session_state:
    st.session_state.current_concept = None
if "quiz_data" not in st.session_state:
    st.session_state.quiz_data = None
if "ground_truth" not in st.session_state:
    st.session_state.ground_truth = None
if "step" not in st.session_state:
    st.session_state.step = "Setup"

# Helper to load concepts
def load_concepts():
    with open("config/concepts.json", "r") as f:
        return json.load(f)

def load_rules(rule_file):
    with open(f"config/{rule_file}", "r") as f:
        return json.load(f)

# Sidebar
st.sidebar.title("Navigation")
concepts = load_concepts()
concept_names = [c["name"] for c in concepts]
selected_concept_name = st.sidebar.selectbox("Select Concept", concept_names)
selected_concept = next(c for c in concepts if c["name"] == selected_concept_name)

# Auto-load existing questionnaire when concept changes
if st.session_state.get("current_concept_id") != selected_concept["id"]:
    st.session_state.current_concept_id = selected_concept["id"]
    existing_q = QuestionnaireBuilder.load_questionnaire(selected_concept["id"])
    if existing_q:
        schema_mgr = SchemaManager()
        # Set the friendly list for the multiselect
        friendly_cols = [schema_mgr.get_friendly_name(q["column"]) for q in existing_q["questions"]]
        st.session_state.selected_friendly_list = friendly_cols
        # Pre-populate question fields in session state
        for q in existing_q["questions"]:
            col = q["column"]
            st.session_state[f"q_text_{col}"] = q["text"]
            st.session_state[f"q_type_{col}"] = q["type"]
            if q.get("options"):
                st.session_state[f"q_opts_{col}"] = ", ".join(q["options"])
    else:
        # Reset if no questionnaire exists for this concept
        st.session_state.selected_friendly_list = []

if st.sidebar.button("Reset Session"):
    st.session_state.clear()
    st.rerun()

# Main App
#render_header("Concept-Based Claims Quiz", "Education & Calibration Platform")

tab1, tab2, tab3 = st.tabs(["📚 Concept Overview", "🛠️ Questionnaire Builder", "✍️ Take Quiz"])

with tab1:
    st.header("Concept Details")
    render_concept_card(selected_concept)
    
    rules = load_rules(selected_concept["rule_file"])
    st.subheader("Reference Rules")
    st.json(rules.get("overpayment_conditions", {}))

with tab2:
    st.header("Build Your Questionnaire")
     
    reader = SchemaReader()
    default_table = os.getenv("CLICKHOUSE_TABLE", "claims")
    
    # Auto-initialize columns if table name matches default or exists in session
    if "table_name_input" not in st.session_state:
        st.session_state.table_name_input = default_table

    table_name = st.text_input("ClickHouse Table Name", value=st.session_state.table_name_input, key="table_input_sync")

    # If table name changed or columns not loaded, fetch automatically
    if ("available_columns" not in st.session_state or 
        st.session_state.get("last_fetched_table") != table_name):
        
        with st.spinner(f"🔍 Syncing schema for {table_name}..."):
            cols = reader.get_table_schema(table_name)
            st.session_state.available_columns = cols
            st.session_state.last_fetched_table = table_name
            st.session_state.table_name_input = table_name

    if "available_columns" in st.session_state:
        # Pre-defined groups for easier selection
        field_groups = {
            "👤 Member": ["MEME_CK", "MEME_SFX", "MEME_FIRST_NAME", "MEME_LAST_NAME", "MEME_SEX"],
            "🏥 Claim Basic": ["CLCL_ID", "CL_TYPE", "CL_SUB_TYPE", "CUR_STS"],
            "⚕️ Clinical": ["IPCD_ID", "IPCD_MOD1_DER", "IPCD_MOD2", "IPCD_MOD3", "IPCD_MOD4", "PROC_CODE_DER"],
            "📅 Timeline": ["FROM_DT", "TO_DT", "LOW_SVC_DT", "HIGH_SVC_DT", "PAID_DT"],
            "💰 Financials": ["CHG_AMT", "ALLOW", "UNITS", "PAID_AMT", "CLCL_TOT_CHG"],
            "🆔 Provider": ["PRPR_ID", "SRVC_PROV_TIN", "PRPR_NPI"],
            "📁 Other": ["OTHER"]
        }

        # Display Shortcuts
        st.subheader("Selection Shortcuts")
        st.caption("Click a group to see its columns, then click 'Add Group' to include them in your quiz.")
        
        # Grid layout for shortcuts (3 columns)
        chunk_size = 3
        groups = list(field_groups.items())
        schema_mgr = SchemaManager()
        
        for i in range(0, len(groups), chunk_size):
            cols_row = st.columns(chunk_size)
            for j, (group_name, members) in enumerate(groups[i:i+chunk_size]):
                with cols_row[j].expander(group_name, expanded=False):
                    # Filter valid members for display - Allow 'OTHER' as a special virtual column
                    valid_orig = []
                    for c in members:
                        is_in_schema = any(avail["original"] == c for avail in st.session_state.available_columns)
                        if is_in_schema or c == "OTHER":
                            valid_orig.append(c)
                            
                    friendly_names = [schema_mgr.get_friendly_name(c) for c in valid_orig]
                    
                    for f_name in friendly_names:
                        st.markdown(f"- {f_name}")
                    
                    if st.button(f"➕ Add {group_name}", key=f"btn_add_{group_name}", use_container_width=True):
                        current = set(st.session_state.get("selected_friendly_list", []))
                        current.update(friendly_names)
                        st.session_state.selected_friendly_list = list(current)
                        st.rerun()

        if st.button("🗑️ Clear All Selections", use_container_width=True):
            st.session_state.selected_friendly_list = []
            st.rerun()

        st.divider()
        
        # Column Selection - Always Visible after Fetch
        col_options = {col["friendly"]: col["original"] for col in st.session_state.available_columns}
        
        # Manually add virtual/custom columns to options if needed
        if "Other" not in col_options:
            col_options["Other"] = "OTHER"
        
        # Safety: Normalize session state to match friendly names (fixes "OTHER" vs "Other" mismatch)
        if "selected_friendly_list" in st.session_state:
            st.session_state.selected_friendly_list = [
                "Other" if x == "OTHER" else x for x in st.session_state.selected_friendly_list
            ]
        
        # CRITICAL FIX for Streamlit Cloud: Filter default values to ensure they exist in options
        # This prevents the "default value is not part of the options" crash.
        options_list = sorted(list(col_options.keys()))
        current_selections = st.session_state.get("selected_friendly_list", [])
        safe_defaults = [val for val in current_selections if val in options_list]
        
        selected_friendly = st.multiselect(
            "Final Quiz Selection", 
            options=options_list,
            default=safe_defaults,
            help="These columns will be used to generate the quiz data."
        )
        
        # Update session state for sync
        st.session_state.selected_friendly_list = selected_friendly
        
        st.divider()

        if selected_friendly:
            st.subheader("Configure Questions")
            
            q_builder = QuestionnaireBuilder(selected_concept["id"])
            for f_name in selected_friendly:
                orig_name = col_options[f_name]
                with st.container(border=True):
                    st.markdown(f"🖋️ **{f_name}** (`{orig_name}`)")
                    c1, c2 = st.columns([2, 1])
                    
                    # Use session state to persist values across reruns when adding/removing other columns
                    q_text = c1.text_input(
                        "Question text", 
                        value=st.session_state.get(f"q_text_{orig_name}", f"Is the {f_name} correct?"), 
                        key=f"q_text_{orig_name}"
                    )
                    q_type = c2.selectbox(
                        "Response Type", 
                        ["Yes/No", "Multiple Choice", "Informational"], 
                        index=0 if st.session_state.get(f"q_type_{orig_name}") == "Yes/No" else 
                              1 if st.session_state.get(f"q_type_{orig_name}") == "Multiple Choice" else 2,
                        key=f"q_type_{orig_name}"
                    )
                    
                    options = []
                    if q_type == "Multiple Choice":
                        opts_str = st.text_input(
                            "Options (comma separated)", 
                            value=st.session_state.get(f"q_opts_{orig_name}", "Option 1, Option 2, Option 3"),
                            key=f"q_opts_{orig_name}",
                            help="Enter choices separated by commas"
                        )
                        options = [opt.strip() for opt in opts_str.split(",") if opt.strip()]
                    
                    q_builder.add_question(orig_name, q_text, q_type, options=options)
            
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("💾 Save Questionnaire", use_container_width=True, type="primary"):
                path = q_builder.save_questionnaire()
                st.success(f"Successfully saved to {path}!")
        else:
            st.info("Pick columns using the dropdown or shortcuts above to see question templates.")

with tab3:
    st.header("Calibration Quiz")
    
    rules = load_rules(selected_concept["rule_file"])
    
    gen_mode = st.radio("Generation Mode", ["Standard (Rule-based)", "LLM (AI Generated)"], horizontal=True)
    
    if gen_mode == "Standard (Rule-based)":
        generator = SyntheticDataGenerator(rules)
    else:
        generator = LLMSyntheticGenerator(rules)
    
    # Load the saved questionnaire for this concept
    saved_q = QuestionnaireBuilder.load_questionnaire(selected_concept["id"])
    
    if st.button("🔄 Generate New Quiz Data"):
        if gen_mode == "LLM (AI Generated)":
            if not saved_q:
                st.error("Please build a questionnaire first so the LLM knows which columns to generate.")
            else:
                cols = [q["column"] for q in saved_q["questions"]]
                with st.spinner("LLM is generating synthetic claims..."):
                    df, gt = generator.generate_quiz_data(cols, 5)
                    st.session_state.quiz_data = df
                    st.session_state.ground_truth = gt
        else:
            df, gt = generator.generate_quiz_data(5)
            st.session_state.quiz_data = df
            st.session_state.ground_truth = gt
            
        st.session_state.user_responses = {} # Reset answers
        st.success("New synthetic data generated!")

    if st.session_state.quiz_data is not None:
        st.subheader("Synthetic Claim Records (Non-PHI)")
        schema_mgr = SchemaManager()
        # Rename columns for display using the mapping
        display_df = st.session_state.quiz_data.rename(columns=lambda x: schema_mgr.get_friendly_name(x))
        st.dataframe(display_df, use_container_width=True)
        
        st.divider()
        st.subheader("Questions")
        
        if not saved_q or not saved_q.get("questions"):
            st.warning("No questionnaire found for this concept. Please build one in Tab 2 first.")
        else:
            user_quiz_answers = {}
            for i, row in st.session_state.quiz_data.iterrows():
                # Safely get a claim identifier for the label
                claim_label = row.get('Claim_ID', row.get('CLCL_ID', f"Record {i+1}"))
                with st.expander(f"📋 Questions for Claim {claim_label}", expanded=(i==0)):
                    row_answers = {}
                    schema_mgr = SchemaManager() # To get friendly names for display
                    for q_idx, q in enumerate(saved_q["questions"]):
                        orig_col = q["column"]
                        friendly_col = schema_mgr.get_friendly_name(orig_col)
                        q_key = f"q_{i}_{q_idx}"
                        st.write(f"**Field: {friendly_col}**")
                        
                        if q["type"] == "Yes/No":
                                ans = st.radio(q["text"], ["Yes", "No"], key=q_key)
                        elif q["type"] == "Multiple Choice":
                            # Use custom options from the questionnaire, fallback to defaults if none provided
                            item_options = q.get("options", [])
                            if not item_options:
                                item_options = ["Option A", "Option B"]
                            ans = st.selectbox(q["text"], item_options, key=q_key)
                        else:
                            ans = st.text_input(q["text"], key=q_key)
                        
                        row_answers[q["column"]] = ans
                    user_quiz_answers[i] = row_answers

            if st.button("🚀 Submit Quiz"):
                # Use ground truth logic (simplified to overpayment for now)
                engine = EvaluationEngine(st.session_state.ground_truth)
                
                # We need to map the complex user_quiz_answers to something the engine understands
                # For now, let's assume the engine checks if 'Is this an overpayment?' question exists
                # or just use the first Boolean question as proxy for scoring.
                
                # Simplified flattening for the existing engine:
                flat_answers = {}
                for idx, row_ans in user_quiz_answers.items():
                    # If user asked "Is this an overpayment?", use that. Otherwise, use what they picked.
                    flat_answers[idx] = "Yes" if any("Yes" in str(v) for v in row_ans.values()) else "No"

                results = engine.evaluate_quiz(flat_answers)
                
                show_score(results["percentage"])
                
                with st.expander("🧐 View Detailed Feedback"):
                    for detail in results["details"]:
                        icon = "✅" if detail["is_correct"] else "❌"
                        st.markdown(f"**Row {detail['row_idx']}**: {icon}")
                        st.write(f"- Correct Determination: {detail['expected']}")
                        st.write(f"- Explanation: {detail['explanation']}")
                        st.divider()
