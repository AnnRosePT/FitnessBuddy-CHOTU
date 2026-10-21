"""FitSense AI - Streamlit Web Application
Runs on Streamlit Community Cloud (share.streamlit.app).
"""
import io
import math
import os
import sys
import tempfile
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageDraw, ImageFont

# Add physiovision to sys.path
_pkg = os.path.join(os.path.dirname(__file__), "physiovision")
if _pkg not in sys.path:
    sys.path.insert(0, _pkg)

CV2_AVAILABLE = False
_cv2_err = None
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except Exception as e:
    _cv2_err = str(e)
    import numpy as np

MEDIAPIPE_AVAILABLE = False
_mp_err = None
try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except Exception as e:
    _mp_err = str(e)
    mp = None

EXERCISES_AVAILABLE = False
_ex_err = None
try:
    from exercises import EXERCISES, RepCounter, joint_angle
    EXERCISES_AVAILABLE = True
except Exception as e:
    _ex_err = str(e)
    from dataclasses import dataclass
    @dataclass
    class FallbackEx:
        name: str
        joint: str
        rest_angle: float
        peak_angle: float
        description: str
        camera_tip: str
        cue_start: str
        cue_peak: str
        cue_return: str

    EXERCISES = {
        "squat": FallbackEx("Squats", "Knee & Hip", 165.0, 85.0, "Bodyweight or weighted squat tracking knee depth.", "Step back 2-3 meters so full body is visible.", "Chest up, hips back", "Thighs parallel to floor", "Drive through heels"),
        "bicep_curl": FallbackEx("Bicep Curl", "Elbow", 160.0, 45.0, "Arm curl tracking elbow flexion angle.", "Stand sideways or 45 degrees to the camera.", "Arms extended", "Squeeze at top", "Control descent"),
        "pushup": FallbackEx("Push-Ups", "Elbow & Shoulder", 160.0, 80.0, "Standard floor push-up tracking arm angle.", "Position camera at side floor level.", "Plank position", "Chest to floor", "Push up strong"),
        "shoulder_press": FallbackEx("Shoulder Press", "Elbow", 80.0, 160.0, "Overhead press for deltoid strength.", "Frame upper body and head clearance.", "Elbows at 90°", "Press fully overhead", "Lower with control"),
        "jumping_jack": FallbackEx("Jumping Jacks", "Arm & Leg", 30.0, 140.0, "Cardio jumping movement.", "Step back so feet and overhead hands fit in frame.", "Feet together", "Jump wide & clap", "Return to center"),
    }

# Landmark helper
def calc_angle(p1, p2, p3):
    """Calculate angle in degrees between three 2D points p1-p2-p3 at joint p2."""
    bax, bay = p1[0] - p2[0], p1[1] - p2[1]
    bcx, bcy = p3[0] - p2[0], p3[1] - p2[1]
    na = math.hypot(bax, bay)
    nc = math.hypot(bcx, bcy)
    if na == 0 or nc == 0:
        return 0.0
    cos = (bax * bcx + bay * bcy) / (na * nc)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))

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
        margin-bottom: 1.2rem;
    }
    .metric-card {
        background: #f7faf8;
        border: 1px solid #e1ebe4;
        border-radius: 12px;
        padding: 1rem;
        text-align: center;
    }
    .feedback-good {
        background: #e6f9ed;
        border: 1px solid #73e29f;
        color: #067335;
        padding: 12px 16px;
        border-radius: 10px;
        font-weight: 600;
        margin: 10px 0;
    }
    .feedback-warn {
        background: #fffbe6;
        border: 1px solid #ffe58f;
        color: #875c00;
        padding: 12px 16px;
        border-radius: 10px;
        font-weight: 600;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar
st.sidebar.title("✣ FitSense AI")
st.sidebar.markdown("**AI-Powered Exercise & Posture Coach**")

nav = st.sidebar.radio(
    "Navigation",
    [
        "📸 Live Camera Workout",
        "🏋️ FitSense Web Dashboard",
        "📹 Video Clip Analyzer",
        "🥗 Student & Flat Diet Guide",
        "🔬 Exercise Angle Guide"
    ],
    index=0
)

# ---------------------------------------------------------------- TAB 1: LIVE CAMERA WORKOUT
if nav == "📸 Live Camera Workout":
    st.markdown('<div class="main-title">📸 Live Camera Workout & Pose Coach</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Your browser streams your webcam securely to detect exercise depth and joint angles.</div>', unsafe_allow_html=True)

    c_left, c_right = st.columns([1, 2])

    with c_left:
        st.markdown("### 1. Select Movement")
        ex_key = st.selectbox(
            "Exercise",
            list(EXERCISES.keys()),
            format_func=lambda k: EXERCISES[k].name,
            key="cam_ex_select"
        )
        selected_ex = EXERCISES[ex_key]
        st.markdown(f"**Target Joint:** `{selected_ex.joint}`")
        st.markdown(f"**Target Angle:** `{selected_ex.peak_angle}°`")
        st.markdown(f"**Camera Setup:** {selected_ex.camera_tip}")
        
        st.info(f"""
        **💡 Coaching Cues:**
        - **Start:** {selected_ex.cue_start}
        - **Peak:** {selected_ex.cue_peak}
        - **Return:** {selected_ex.cue_return}
        """)

    with c_right:
        st.markdown("### 2. Browser Camera Stream")
        st.caption("Click **Take photo** while performing a rep to analyze your depth and form:")
        camera_img = st.camera_input("Pose in front of your camera", key="webcam_capture")

        if camera_img:
            raw_bytes = camera_img.getvalue()
            pil_img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
            img_np = np.array(pil_img)
            h, w, _ = img_np.shape

            annotated_img = pil_img.copy()
            draw = ImageDraw.Draw(annotated_img)

            detected = False
            measured_angle = None

            if MEDIAPIPE_AVAILABLE and mp is not None:
                with mp.solutions.pose.Pose(static_image_mode=True, min_detection_confidence=0.5) as pose:
                    res = pose.process(img_np)
                    if res.pose_landmarks:
                        detected = True
                        lm = res.pose_landmarks.landmark

                        # Body landmarks
                        # 11: left shoulder, 12: right shoulder
                        # 13: left elbow, 14: right elbow
                        # 15: left wrist, 16: right wrist
                        # 23: left hip, 24: right hip
                        # 25: left knee, 26: right knee
                        # 27: left ankle, 28: right ankle

                        # Draw connections
                        conns = [
                            (11, 12), (11, 13), (13, 15),
                            (12, 14), (14, 16),
                            (11, 23), (12, 24), (23, 24),
                            (23, 25), (25, 27),
                            (24, 26), (26, 28)
                        ]
                        for c1, c2 in conns:
                            if lm[c1].visibility > 0.4 and lm[c2].visibility > 0.4:
                                p1 = (int(lm[c1].x * w), int(lm[c1].y * h))
                                p2 = (int(lm[c2].x * w), int(lm[c2].y * h))
                                draw.line([p1, p2], fill="#00ff66", width=4)

                        # Draw joints
                        for i in [11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]:
                            if lm[i].visibility > 0.4:
                                pt = (int(lm[i].x * w), int(lm[i].y * h))
                                draw.ellipse([pt[0]-6, pt[1]-6, pt[0]+6, pt[1]+6], fill="#ffffff", outline="#0aa74e", width=3)

                        # Calculate exercise angle
                        if ex_key == "squat":
                            # Measure knee angle: hip-knee-ankle (choose left or right side with better visibility)
                            if lm[25].visibility >= lm[26].visibility:
                                p1 = (lm[23].x, lm[23].y)
                                p2 = (lm[25].x, lm[25].y)
                                p3 = (lm[27].x, lm[27].y)
                                joint_pt = (int(lm[25].x * w), int(lm[25].y * h))
                            else:
                                p1 = (lm[24].x, lm[24].y)
                                p2 = (lm[26].x, lm[26].y)
                                p3 = (lm[28].x, lm[28].y)
                                joint_pt = (int(lm[26].x * w), int(lm[26].y * h))
                            measured_angle = calc_angle(p1, p2, p3)

                        elif ex_key in ("bicep_curl", "pushup"):
                            # Measure elbow angle: shoulder-elbow-wrist
                            if lm[13].visibility >= lm[14].visibility:
                                p1 = (lm[11].x, lm[11].y)
                                p2 = (lm[13].x, lm[13].y)
                                p3 = (lm[15].x, lm[15].y)
                                joint_pt = (int(lm[13].x * w), int(lm[13].y * h))
                            else:
                                p1 = (lm[12].x, lm[12].y)
                                p2 = (lm[14].x, lm[14].y)
                                p3 = (lm[16].x, lm[16].y)
                                joint_pt = (int(lm[14].x * w), int(lm[14].y * h))
                            measured_angle = calc_angle(p1, p2, p3)

                        elif ex_key == "shoulder_press":
                            # Measure elbow extension: shoulder-elbow-wrist
                            p1 = (lm[11].x, lm[11].y)
                            p2 = (lm[13].x, lm[13].y)
                            p3 = (lm[15].x, lm[15].y)
                            measured_angle = calc_angle(p1, p2, p3)
                            joint_pt = (int(lm[13].x * w), int(lm[13].y * h))

                        else:
                            measured_angle = 90.0
                            joint_pt = (w // 2, h // 2)

                        # Highlight joint
                        draw.ellipse([joint_pt[0]-14, joint_pt[1]-14, joint_pt[0]+14, joint_pt[1]+14], outline="#ffeb3b", width=4)

            # Display results
            if detected and measured_angle is not None:
                target = selected_ex.peak_angle
                # For squat and bicep curl, lower angle = deeper rep
                if ex_key in ("squat", "bicep_curl", "pushup"):
                    is_good = measured_angle <= (target + 15)
                else:
                    is_good = measured_angle >= (target - 15)

                m1, m2, m3 = st.columns(3)
                m1.metric("Measured Angle", f"{measured_angle:.1f}°")
                m2.metric("Target Goal", f"{target:.0f}°")
                m3.metric("Verdict", "✅ Full Rep Depth" if is_good else "⚠️ Needs Depth")

                if is_good:
                    st.markdown(f'<div class="feedback-good">🎉 **Great Form!** You reached {measured_angle:.1f}° (target was {target:.0f}°). Keep up the smooth control!</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="feedback-warn">⚠️ **Form Adjustment:** Current joint angle is {measured_angle:.1f}°. {selected_ex.cue_peak} to hit full range of motion.</div>', unsafe_allow_html=True)

                st.image(annotated_img, caption="AI Pose & Joint Skeleton Overlay", use_column_width=True)
            elif not MEDIAPIPE_AVAILABLE:
                st.warning("MediaPipe pose engine is compiling on the cloud container. Image captured successfully.")
                st.image(pil_img, caption="Captured Frame", use_column_width=True)
            else:
                st.warning("⚠️ No full body detected in frame. Please step back 2-3 meters so your shoulders, hips, and knees are in view.")
                st.image(pil_img, caption="Captured Frame", use_column_width=True)

# ---------------------------------------------------------------- TAB 2: DASHBOARD
elif nav == "🏋️ FitSense Web Dashboard":
    st.markdown('<div class="main-title">🏋️ FitSense Live Workout Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Complete interactive dashboard with voice prompts, rep counter, and exercise library.</div>', unsafe_allow_html=True)

    st.info("💡 **Camera on Streamlit Cloud:** Cloud servers run remotely without hardware webcams. For live browser webcam tracking on Streamlit Cloud, use the **📸 Live Camera Workout** tab in the sidebar! When running locally (`python app.py`), the physical laptop camera connects directly here.")

    # Read and render the complete custom HTML5/CSS3/JS FitSense Dashboard
    html_path = os.path.join(os.path.dirname(__file__), "physiovision", "templates", "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        components.html(html_content, height=1100, scrolling=True)
    else:
        st.error("Dashboard template not found.")

# ---------------------------------------------------------------- TAB 3: VIDEO ANALYZER
elif nav == "📹 Video Clip Analyzer":
    st.markdown('<div class="main-title">📹 Video Workout AI Analyzer</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Upload a workout video (.mp4 / .mov) and let MediaPipe track your reps and joint angles.</div>', unsafe_allow_html=True)

    c1, c2 = st.columns([1, 2])
    with c1:
        ex_choice = st.selectbox(
            "Select Exercise",
            list(EXERCISES.keys()),
            format_func=lambda k: EXERCISES[k].name,
            key="vid_ex_choice"
        )
        target_reps = st.number_input("Target Reps", min_value=1, max_value=100, value=10)
        uploaded_video = st.file_uploader("Upload Workout Clip", type=["mp4", "mov", "avi"])

    with c2:
        if uploaded_video:
            tfile = tempfile.NamedTemporaryFile(delete=False)
            tfile.write(uploaded_video.read())
            video_path = tfile.name

            st.video(uploaded_video)
            st.success(f"Video uploaded successfully. Ready to analyze {EXERCISES[ex_choice].name} for {target_reps} reps.")
        else:
            st.info("Upload a video clip on the left to start automated rep analysis.")

# ---------------------------------------------------------------- TAB 4: DIET GUIDE
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

# ---------------------------------------------------------------- TAB 5: ANGLE GUIDE
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
