import sys
import os

print(f"Executable: {sys.executable}")
print(f"Version: {sys.version}")
print(f"Path: {sys.path}")

try:
    import openai
    print(f"OpenAI Version: {openai.__version__}")
    print(f"OpenAI File: {openai.__file__}")
except ImportError:
    print("OpenAI is NOT installed in this environment.")

try:
    import streamlit
    print(f"Streamlit Version: {streamlit.__version__}")
except ImportError:
    print("Streamlit is NOT installed in this environment.")
