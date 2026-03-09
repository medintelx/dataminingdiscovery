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
            # Maintain the actual type without auto-casting Free Text
            q_type = q.get("type", "Yes/No")
            # Informational gets mapped to Free Text
            if q_type == "Informational":
                q_type = "Free Text"
            st.session_state[f"q_type_{col}"] = q_type
            
            if q.get("options"):
                st.session_state[f"q_opts_{col}"] = ", ".join(q["options"])
    else:
        # Reset if no questionnaire exists for this concept
        st.session_state.selected_friendly_list = []
    
    # Force quiz data reload for new concept
    st.session_state.quiz_data = None
    st.session_state.ground_truth = None
    st.session_state.ai_suggestions = None

if st.sidebar.button("Reset Session"):
    st.session_state.clear()
    st.rerun()

st.sidebar.divider()
st.sidebar.subheader("Data Schema Sync")
reader = SchemaReader()
default_table = os.getenv("CLICKHOUSE_TABLE", "ClaimsInscope")

if "table_name_input" not in st.session_state:
    st.session_state.table_name_input = default_table

table_name = st.sidebar.text_input("ClickHouse Table Name", value=st.session_state.table_name_input, key="table_input_sync")

if ("available_columns" not in st.session_state or 
    st.session_state.get("last_fetched_table") != table_name):
    
    with st.sidebar.status(f"🔍 Syncing schema for {table_name}..."):
        cols = reader.get_table_schema(table_name)
        st.session_state.available_columns = cols
        st.session_state.last_fetched_table = table_name
        st.session_state.table_name_input = table_name
        st.write("✅ Schema synced successfully!")

# Main App
#render_header("Concept-Based Claims Quiz", "Education & Calibration Platform")

# tab1, tab2, tab3, tab4 = st.tabs(["📚 Concept Overview", "🛠️ Questionnaire Builder", "🤖 Questionnaire", "✍️ Take Quiz"])
tab1, tab3, tab4 = st.tabs(["📚 Concept Overview", "🤖 Questionnaire", "✍️ Take Quiz"])

with tab1:
    st.header("Concept Details")
    render_concept_card(selected_concept)
    
    rules = load_rules(selected_concept["rule_file"])
    st.subheader("Reference Rules")
    st.json(rules.get("overpayment_conditions", {}))

if False: # with tab2:
    st.header("Build Your Questionnaire")


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
            
            # Ensure unique elements internally to avoid list.index collision and rendering issues
            unique_selected = []
            seen = set()
            for s in selected_friendly:
                if s not in seen:
                    unique_selected.append(s)
                    seen.add(s)
                    
            for loop_idx, f_name in enumerate(unique_selected):
                orig_name = col_options[f_name]
                with st.container(border=True):
                    st.markdown(f"🖋️ **{f_name}** (`{orig_name}`)")
                    c1, c2 = st.columns([2, 1])
                    
                    # Use session state to persist values across reruns when adding/removing other columns
                    # Append loop_idx to key to guarantee uniqueness if multiple friendly names map to the same original column
                    q_text = c1.text_input(
                        "Question text", 
                        value=st.session_state.get(f"q_text_{orig_name}", f"Is the {f_name} correct?"), 
                        key=f"q_text_{orig_name}_{loop_idx}"
                    )
                    response_type_options = ["Yes/No", "Multiple Choice", "Free Text"]
                    saved_type = st.session_state.get(f"q_type_{orig_name}", "Yes/No")
                    if saved_type not in response_type_options:
                        saved_type = "Yes/No"
                        
                    q_type = c2.selectbox(
                        "Response Type", 
                        response_type_options, 
                        index=response_type_options.index(saved_type),
                        key=f"q_type_{orig_name}_{loop_idx}"
                    )
                    
                    options = []
                    if q_type == "Multiple Choice":
                        opts_str = st.text_input(
                            "Options (comma separated)", 
                            value=st.session_state.get(f"q_opts_{orig_name}", "Option 1, Option 2, Option 3"),
                            key=f"q_opts_{orig_name}_{loop_idx}",
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
    st.header("Sample Questionnaire ")
    
    # Persistent View: Check for existing saved questionnaire first
    saved_q = QuestionnaireBuilder.load_questionnaire(selected_concept["id"])
    
    show_gen_form = False
    
    if saved_q and saved_q.get("questions"):
        ui_schema_mgr = SchemaManager()
        st.success(f"✅ Active Questionnaire found for {selected_concept['name']}")
        
        with st.expander("📋 Current Configuration (Editable)", expanded=True):
            # Remove the form wrapper so changing Response Type triggers an immediate re-run to reveal Options.
            updated_questions = []
            has_notes_already = False
            for idx, q in enumerate(saved_q["questions"]):
                with st.container(border=True):
                    friendly = ui_schema_mgr.get_friendly_name(q["column"])
                    col_title, col_btn = st.columns([4, 1])
                    
                    with col_title:
                        st.markdown(f"**Q{idx+1}: Field: {friendly} (`{q['column']}`)**")
                        
                    # Initialize edit mode state for this specific question
                    edit_key = f"edit_mode_{idx}"
                    if edit_key not in st.session_state:
                        st.session_state[edit_key] = False
                        
                    with col_btn:
                        btn_col1, btn_col2 = st.columns(2)
                        with btn_col1:
                            if st.button("✏️", key=f"btn_edit_{idx}"):
                                st.session_state[edit_key] = not st.session_state[edit_key]
                                st.rerun()
                        with btn_col2:
                            if st.button("🗑️", key=f"btn_del_{idx}"):
                                updated_questions = [q for i, q in enumerate(saved_q["questions"]) if i != idx]
                                q_builder = QuestionnaireBuilder(selected_concept["id"])
                                for q_item in updated_questions:
                                    q_builder.add_question(q_item["column"], q_item["text"], q_item["type"], options=q_item["options"])
                                q_builder.save_questionnaire()
                                st.rerun()

                    if st.session_state[edit_key]:    
                        # --- EDIT MODE ---
                        new_text = st.text_input("Question Text", value=q.get("text", ""), key=f"edit_q_text_{idx}")
                        
                        type_opts = ["Yes/No", "Multiple Choice", "Free Text"]
                        curr_type = q.get("type", "Yes/No")
                        if curr_type == "Informational": curr_type = "Free Text"
                        if curr_type not in type_opts: curr_type = "Yes/No"
                        
                        new_type = st.selectbox("Response Type", type_opts, index=type_opts.index(curr_type), key=f"edit_q_type_{idx}")
                        
                        new_opts = q.get("options", [])
                        if new_type == "Multiple Choice":
                            opts_str = st.text_input("Options (comma separated)", value=", ".join(new_opts), key=f"edit_q_opts_{idx}")
                            new_opts = [o.strip() for o in opts_str.split(",") if o.strip()]
                            
                        updated_questions.append({
                            "column": q["column"],
                            "text": new_text,
                            "type": new_type,
                            "options": new_opts
                        })
                    else:
                        # --- READ-ONLY MODE ---
                        st.write(f"{q.get('text', 'No question text provided')}")
                        display_type = q.get("type", "Yes/No")
                        if display_type == "Multiple Choice":
                            opts = q.get("options", [])
                            st.caption(f"Type: {display_type} | Options: {', '.join(opts) if opts else 'None'}")
                        else:
                            st.caption(f"Type: {display_type}")
                            
                        # Keep the original values in the updated list if not editing
                        updated_questions.append(q)
            
            st.divider()
            st.markdown("### Editable Claim Examples")
            updated_examples = []
            for ex_idx, example in enumerate(saved_q.get("examples", [])):
                st.markdown(f"**Example {ex_idx+1}**")
                new_ex = {}
                # Create a simple grid
                cols = st.columns(3)
                col_counter = 0
                for k, v in example.items():
                    with cols[col_counter % 3]:
                        new_ex[k] = st.text_input(k, value=str(v), key=f"edit_ex_{ex_idx}_{k}")
                    col_counter += 1
                updated_examples.append(new_ex)

            st.divider()
            col1, col2 = st.columns([1, 1])
            with col1:
                submitted = st.button("💾 Save Changes to Questionnaire", use_container_width=True)
            with col2:
                add_blank = st.button("➕ Add Blank Question", use_container_width=True)
                
            if submitted or add_blank:
                q_builder = QuestionnaireBuilder(selected_concept["id"])
                for q_item in updated_questions:
                    q_builder.add_question(q_item["column"], q_item["text"], q_item["type"], options=q_item["options"])
                
                if add_blank:
                     q_builder.add_question("OTHER", "New Custom Question", "Yes/No", options=[])
                     
                q_builder.set_examples(updated_examples)
                q_builder.save_questionnaire()
                st.rerun()
        
        # if st.button("🤖 Regenerate (Overwrites current)", use_container_width=True):
        #     show_gen_form = True
        #     st.session_state.ai_suggestions = None
        #     st.session_state.ai_examples = None
    else:
        st.info("No questionnaire found. Let AI analyze your rules and schema to build an optimized audit form.")
        show_gen_form = True

    if show_gen_form or st.session_state.get("ai_suggestions"):
        if st.button("🚀 RunAnalysis", use_container_width=True, type="primary"):
            if "available_columns" not in st.session_state:
                st.warning("Please ensure the schema is synced first.")
            else:
                rules = load_rules(selected_concept["rule_file"])
                gen = LLMSyntheticGenerator(rules)
                with st.spinner("Analyzing rules..."):
                    suggestions, examples = gen.generate_suggested_questionnaire(st.session_state.available_columns)
                    st.session_state.ai_suggestions = suggestions
                    st.session_state.ai_examples = examples
                    if suggestions:
                        st.success("AI Generation Complete!")

    if st.session_state.get("ai_suggestions"):
        st.subheader("🤖 AI Preview (Editable)")
        schema_mgr = SchemaManager()
        
        # Removed st.form to allow interactive re-renders (like showing options only when Multiple Choice is selected)
        for i, sug in enumerate(st.session_state.ai_suggestions):
            if not isinstance(sug, dict): continue
            with st.container(border=True):
                col1, col2 = st.columns([4, 1])
                with col1:
                    col_name = sug.get("column", "Unknown")
                    friendly = schema_mgr.get_friendly_name(col_name)
                    st.markdown(f"📍 **Field:** {friendly} (`{col_name}`)")
                with col2:
                    if st.button("🗑️", key=f"ai_gen_del_{i}"):
                        st.session_state.ai_suggestions.pop(i)
                        st.rerun()
                
                # Editable question text
                new_text = st.text_input("Question Text", value=sug.get('text', 'No question'), key=f"ai_gen_text_{i}")
                
                # Editable Type
                type_opts = ["Yes/No", "Multiple Choice", "Free Text"]
                curr_type = sug.get('type', 'Yes/No')
                if curr_type not in type_opts:
                    curr_type = "Yes/No"
                    
                new_type = st.selectbox("Response Type", type_opts, index=type_opts.index(curr_type), key=f"ai_gen_type_{i}")
                
                # Editable Options (if Multiple Choice)
                new_opts = sug.get("options", [])
                if new_type == "Multiple Choice":
                    opts_str = st.text_input("Options (comma separated)", value=", ".join(new_opts), key=f"ai_gen_opts_{i}")
                    new_opts = [o.strip() for o in opts_str.split(",") if o.strip()]
                
                # Update the suggestion in place so the button picks up the latest state
                sug['text'] = new_text
                sug['type'] = new_type
                sug['options'] = new_opts
        
        st.divider()
        st.markdown("### Add Custom Question")
        if st.button("➕ Add Blank Question"):
            st.session_state.ai_suggestions.append({
                "column": "OTHER",
                "text": "New Custom Question",
                "type": "Yes/No",
                "options": []
            })
            st.rerun()
            
        st.divider()
        st.markdown("### Generated Claim Examples (Editable)")
        ai_examples = st.session_state.get("ai_examples", [])
        if not ai_examples:
            st.info("No examples found.")
        updated_ai_examples = []
        for ex_idx, example in enumerate(ai_examples):
            st.markdown(f"**Example {ex_idx+1}**")
            new_ex = {}
            cols = st.columns(3)
            col_counter = 0
            for k, v in example.items():
                with cols[col_counter % 3]:
                    new_ex[k] = st.text_input(k, value=str(v), key=f"ai_ex_{ex_idx}_{k}")
                col_counter += 1
            updated_ai_examples.append(new_ex)
        st.session_state.ai_examples = updated_ai_examples
        
        if st.button("✅ Apply & Save This Questionnaire", use_container_width=True):
                q_builder = QuestionnaireBuilder(selected_concept["id"])
                for sug in st.session_state.ai_suggestions:
                    if isinstance(sug, dict):
                        q_builder.add_question(sug.get("column", "OTHER"), sug.get("text"), sug.get("type"), options=sug.get("options", []))
                q_builder.set_examples(st.session_state.get("ai_examples", []))
                q_builder.save_questionnaire()
                st.session_state.selected_friendly_list = [schema_mgr.get_friendly_name(s["column"]) for s in st.session_state.ai_suggestions if isinstance(s, dict)]
                st.session_state.ai_suggestions = None
                st.session_state.ai_examples = None
                st.rerun()

with tab4:
    st.header("Calibration Quiz")
    
    rules = load_rules(selected_concept["rule_file"])
    
    gen_mode = st.radio("Generation Mode", ["Standard (Rule-based)", "LLM (AI Generated)"], horizontal=True)
    
    if gen_mode == "Standard (Rule-based)":
        generator = SyntheticDataGenerator(rules)
    else:
        generator = LLMSyntheticGenerator(rules)
    
    # Load the saved questionnaire for this concept
    saved_q = QuestionnaireBuilder.load_questionnaire(selected_concept["id"])
    
    # Persistent Quiz Data Logic
    q_builder = QuestionnaireBuilder(selected_concept["id"])
    
    # Auto-load from DB if session state is empty
    if st.session_state.quiz_data is None:
        db_df, db_gt = QuestionnaireBuilder.load_quiz_data(selected_concept["id"])
        if db_df is not None:
            st.session_state.quiz_data = db_df
            st.session_state.ground_truth = db_gt
            st.info("Loaded previously generated quiz data.")

    if st.button("🔄 Generate & Save New Quiz Data", use_container_width=True, type="primary"):
        if gen_mode == "LLM (AI Generated)":
            if not saved_q:
                st.error("Please build a questionnaire first.")
            else:
                cols = [q["column"] for q in saved_q["questions"]]
                with st.spinner("Generating new scenarios..."):
                    df, gt = generator.generate_quiz_data(cols, 5)
                    st.session_state.quiz_data = df
                    st.session_state.ground_truth = gt
                    q_builder.save_quiz_data(df, gt)
        else:
            df, gt = generator.generate_quiz_data(5)
            st.session_state.quiz_data = df
            st.session_state.ground_truth = gt
            q_builder.save_quiz_data(df, gt)
            
        st.session_state.user_responses = {} # Reset answers
        st.success("New data generated and saved!")
        st.rerun()

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
                            # Robust Data Lookup: Try exact internal, then case-insensitive internal, then friendly, then common aliases
                            target_key = orig_col.upper()
                            col_val = "N/A"
                            
                            # Standardize row index for matching
                            row_cols = {str(k).upper().replace(" ", "_"): v for k, v in row.to_dict().items()}
                            friendly_name_upper = friendly_col.upper().replace(" ", "_")
                            
                            # Define Common Aliases for the lookup bridge
                            aliases = {
                                "CLCL_ID": ["CLAIM_ID", "CLAIMID", "IDENTIFIER", "CLAIM_IDENTIFIER"],
                                "IPCD_ID": ["PROC_CODE", "PROCEDURE", "CPT"],
                                "IPCD_MOD1_DER": ["MODIFIER", "MOD", "PROC_MOD", "QX", "QK"],
                                "FROM_DT": ["DOS", "DATE_OF_SERVICE", "SERVICE_DATE"],
                                "PAID_AMT": ["PAID", "AMOUNT", "PAID_AMOUNT"]
                            }
                            
                            if target_key in row_cols:
                                col_val = row_cols[target_key]
                            elif friendly_name_upper in row_cols:
                                col_val = row_cols[friendly_name_upper]
                            else:
                                # Check aliases
                                found_alias = False
                                if target_key in aliases:
                                    for alias in aliases[target_key]:
                                        if alias in row_cols:
                                            col_val = row_cols[alias]
                                            found_alias = True
                                            break
                                
                                if not found_alias:
                                    # Final attempt: partial match
                                    for k, v in row_cols.items():
                                        if target_key in k or k in target_key:
                                            col_val = v
                                            break
                            
                            # Handle empty/null values
                            if pd.isna(col_val) or col_val == "" or col_val is None:
                                col_val = "Record found but value is empty"
                                
                            st.markdown(f"🔍 **Actual Data:** `{col_val}`")
                            ans = st.text_input(q["text"], key=q_key, placeholder="Enter auditor notes/comments here...")
                        
                        row_answers[q["column"]] = ans
                    user_quiz_answers[i] = row_answers
            
            # Diagnostic for User
            with st.expander("🛠️ Quiz Data Diagnostics (Debug)"):
                st.write("Columns available in generated data:")
                st.code(list(st.session_state.quiz_data.columns))
                st.write("Sample row (internal names):")
                st.json(st.session_state.quiz_data.iloc[0].to_dict() if not st.session_state.quiz_data.empty else {})

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
