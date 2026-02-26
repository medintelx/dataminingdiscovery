import streamlit as st

def apply_custom_css():
    st.markdown("""
        <style>
        .main {
            background-color: #f8f9fa;
        }
        .stButton>button {
            width: 100%;
            border-radius: 5px;
            height: 3em;
            background-color: #007bff;
            color: white;
            font-weight: bold;
        }
        .stButton>button:hover {
            background-color: #0056b3;
            color: white;
        }
        .card {
            padding: 20px;
            border-radius: 10px;
            background-color: white;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        .metric-card {
            text-align: center;
            padding: 15px;
            border-radius: 8px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .success-banner {
            padding: 10px;
            border-radius: 5px;
            background-color: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .error-banner {
            padding: 10px;
            border-radius: 5px;
            background-color: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        </style>
    """, unsafe_allow_html=True)

def render_header(title, subtitle):
    st.markdown(f"# {title}")
    st.markdown(f"### {subtitle}")
    st.divider()

def render_concept_card(concept):
    with st.container():
        st.markdown(f"""
            <div class="card">
                <h4>{concept['name']}</h4>
                <p>{concept['description']}</p>
            </div>
        """, unsafe_allow_html=True)

def show_score(percentage):
    color = "#28a745" if percentage >= 80 else "#ffc107" if percentage >= 50 else "#dc3545"
    st.markdown(f"""
        <div class="metric-card" style="background: {color};">
            <h2>Final Score: {percentage:.1f}%</h2>
        </div>
    """, unsafe_allow_html=True)
