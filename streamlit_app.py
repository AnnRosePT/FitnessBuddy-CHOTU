"""FitSense AI - Streamlit Web Application
Hosts the full FitSense UI with complete responsive design and interactive controls.
"""
import os
import streamlit as st
import streamlit.components.v1 as components

# Page configuration
st.set_page_config(
    page_title="FitSense — AI Fitness Coach",
    page_icon="💪",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Custom CSS to eliminate Streamlit padding, header, footer, and sidebar so FitSense fills the entire window seamlessly
st.markdown("""
<style>
    /* Hide Streamlit default UI chrome */
    #MainMenu, header, footer, [data-testid="stToolbar"], [data-testid="stSidebar"] {
        display: none !important;
        visibility: hidden !important;
    }
    .stApp {
        background-color: #f6f8f9 !important;
    }
    .block-container {
        padding: 0 !important;
        margin: 0 !important;
        max-width: 100% !important;
    }
    iframe {
        border: none !important;
        width: 100% !important;
        min-height: 100vh !important;
    }
</style>
""", unsafe_allow_html=True)

# Load and render the complete FitSense HTML template
template_path = os.path.join(os.path.dirname(__file__), "physiovision", "templates", "index.html")
if os.path.exists(template_path):
    with open(template_path, "r", encoding="utf-8") as f:
        html_code = f.read()
    components.html(html_code, height=1350, scrolling=True)
else:
    st.error("FitSense index.html template not found.")
