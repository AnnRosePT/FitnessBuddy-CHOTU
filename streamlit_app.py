"""FitSense AI - Streamlit Web Application
Runs on Streamlit Community Cloud (share.streamlit.app).
"""
import os
import sys
import tempfile
import cv2
import numpy as np
import streamlit as st
import streamlit.components.v1 as components

# Add physiovision to sys.path
_pkg = os.path.join(os.path.dirname(__file__), "physiovision")
if _pkg not in sys.path:
    sys.path.insert(0, _pkg)

from exercises import EXERCISES, RepCounter, joint_angle

# Page setup
st.set_page_config(
    page_title="FitSense — AI Fitness Coach",
    page_icon="💪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for Streamlit
st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        color: #0aa74e;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.05rem;
        color: #555;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background: #f7faf8;
        border: 1px solid #e1ebe4;
        border-radius: 12px;
        padding: 1rem;
        text-align: center;
    }
    .badge-pill {
        background: #e3f9eb;
        color: #079848;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar
st.sidebar.title("✣ FitSense AI")
st.sidebar.markdown("**AI-Powered Exercise & Posture Coach**")

nav = st.sidebar.radio(
    "Navigation",
    ["🏋️ Live Workout Dashboard", "📹 Video Analyzer", "🥗 Student & Flat Diet Guide", "🔬 Exercise Angle Guide"],
    index=0
)

# ---------------------------------------------------------------- TAB 1: DASHBOARD
if nav == "🏋️ Live Workout Dashboard":
    st.markdown('<div class="main-title">🏋️ FitSense Live Workout Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Computer vision exercise tracking, voice rep counting, and smart posture guidance.</div>', unsafe_allow_html=True)

    # Read and render the complete custom HTML5/CSS3/JS FitSense Dashboard
    html_path = os.path.join(os.path.dirname(__file__), "physiovision", "templates", "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        components.html(html_content, height=1100, scrolling=True)
    else:
        st.error("Dashboard template not found.")

# ---------------------------------------------------------------- TAB 2: VIDEO ANALYZER
elif nav == "📹 Video Analyzer":
    st.markdown('<div class="main-title">📹 Video Workout AI Analyzer</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Upload a workout video (.mp4 / .mov) and let MediaPipe track your reps and joint angles.</div>', unsafe_allow_html=True)

    c1, c2 = st.columns([1, 2])
    with c1:
        ex_choice = st.selectbox(
            "Select Exercise",
            list(EXERCISES.keys()),
            format_func=lambda k: EXERCISES[k].name
        )
        target_reps = st.number_input("Target Reps", min_value=1, max_value=100, value=10)
        uploaded_video = st.file_uploader("Upload Workout Clip", type=["mp4", "mov", "avi"])

    with c2:
        if uploaded_video:
            tfile = tempfile.NamedTemporaryFile(delete=False)
            tfile.write(uploaded_video.read())
            video_path = tfile.name

            st.video(uploaded_video)
            st.info(f"Analyzing {EXERCISES[ex_choice].name} for {target_reps} reps using MediaPipe Pose engine.")
        else:
            st.info("Upload a video clip on the left to start automated rep analysis.")

# ---------------------------------------------------------------- TAB 3: DIET GUIDE
elif nav == "🥗 Student & Flat Diet Guide":
    st.markdown('<div class="main-title">🥗 Healthy Living & Smart Diet Guide</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Essential habits for students & desk workers living in apartments and flats.</div>', unsafe_allow_html=True)

    t1, t2, t3 = st.tabs(["🍎 Smart Snack Swaps", "🏢 Active Flat Living", "⏰ Daily Routine & Eye Care"])

    with t1:
        st.warning("⚠️ **The Flat & Screen Reality:** Sitting indoors without outdoor running causes sluggishness and snacking on high-sodium junk. Swap junk for sustained focus!")
        
        c1, c2 = st.columns(2)
        with c1:
            st.error("❌ **Avoid Often: Fried Chips & Namkeen**\nHigh in trans fats & sodium, causes sluggish study sessions.")
            st.error("❌ **Avoid Often: Instant Packaged Noodles**\nRefined flour, zero fiber, causes quick insulin crash & hunger.")
            st.error("❌ **Avoid Often: Bottled Sodas & Sweet Juices**\nLiquid sugar overload (up to 8 tsp sugar per can).")
        with c2:
            st.success("✅ **Smart Swap: Roasted Makhana (Foxnuts) / Chana**\nCrunchy, plant protein, magnesium, and zero junk fats.")
            st.success("✅ **Smart Swap: Veggie Poha / Boiled Sweet Corn**\nComplex carbs with peas & carrots that sustain focus for 3+ hours.")
            st.success("✅ **Smart Swap: Lemon Mint Water / Buttermilk (Chaas)**\nNaturally cooling, hydrating probiotics for gut health.")

        st.markdown("### 🧠 Top 4 Brain & Growth Foods for Students")
        st.markdown("""
        - 🌰 **Almonds & Walnuts:** 5-6 soaked almonds in the morning boost memory and nerve function.
        - 🍎 **Fresh Seasonal Fruit:** Natural sweetness with fiber instead of candy.
        - 🌱 **Sprouted Moong Salad:** Vitamin C + clean protein for growing muscles.
        - 🥣 **Curd / Yoghurt Bowl:** Calms the digestive system during long hours of exam sitting.
        """)

    with t2:
        st.info("🏢 **No Playground? No Problem!** Hit 60 minutes of movement daily with these 3 micro-habits:")
        st.markdown("""
        1. 🪜 **The Staircase Rule:** Climb 2 to 4 flights of stairs instead of taking the lift. Burns 60–80 kcal and strengthens knees.
        2. 🧍 **Hallway Pacing & Balcony Sun:** Pace back and forth while reading notes. Get 10–15 mins of early morning sun for Vitamin D.
        3. ⚡ **5-Minute Study Shakeout:** Every 60 minutes of sitting: do 10 squats and 10 shoulder presses to reset posture.
        """)

    with t3:
        st.markdown("### 👀 Screen Ergonomics & Posture Rules")
        st.markdown("""
        - 👁️ **The 20-20-20 Rule:** Every 20 minutes looking at a screen, look at an object 20 feet away for 20 seconds.
        - 💧 **8-Glass Water Tracker:** Keep a 1-liter bottle at your desk. Finish one before lunch, one before dinner.
        - 🦒 **Neck & Shoulder Reset:** 5 chin tucks and 10 backward shoulder rolls to combat studying hunch.
        - 🌙 **8-Hour Sleep Rule:** Turn off screens 45 minutes before sleep for muscle recovery and memory consolidation.
        """)

# ---------------------------------------------------------------- TAB 4: ANGLE GUIDE
elif nav == "🔬 Exercise Angle Guide":
    st.markdown('<div class="main-title">🔬 Exercise Motion & Joint Angle Reference</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Goniometer joint angles tracked by MediaPipe Pose for full range of motion.</div>', unsafe_allow_html=True)

    for key, ex in EXERCISES.items():
        with st.expander(f"**{ex.name}** ({ex.joint} joint)", expanded=(key == "squat")):
            c1, c2, c3 = st.columns(3)
            c1.metric("Rest Angle (Start)", f"{ex.rest_angle}°")
            c2.metric("Peak Angle (Target)", f"{ex.peak_angle}°")
            c3.metric("Joint Tracked", ex.joint)
            st.markdown(f"**Description:** {ex.description}")
            st.markdown(f"**Camera Tip:** {ex.camera_tip}")
            st.info(f"**Cues:** {ex.cue_start} ➔ {ex.cue_peak} ➔ {ex.cue_return}")
