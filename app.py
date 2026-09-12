import json
import os
import random
from datetime import datetime

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

# --- Page Configuration ---
st.set_page_config(
    page_title="Spelling Practice App", page_icon="✏️", layout="centered"
)

# Custom CSS: Reduce top padding, enlarge inputs, and enforce accessible metric colors & mobile layout
st.markdown(
    """
    <style>
    /* Reduce top whitespace and constrain max width for a compact feel */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 1.5rem !important;
        max-width: 650px !important;
    }

    /* Hide top header padding gap */
    div[data-testid="stHeader"] {
        height: 0px !important;
    }

    /* Large, high-visibility text input box */
    div[data-testid="stTextInput"] input {
        font-size: 36px !important;
        font-weight: bold !important;
        text-align: center !important;
        height: 70px !important;
        letter-spacing: 4px !important;
    }

    /* --- SCORE METRIC HIGH-CONTRAST STYLING --- */
    div[data-testid="stMetric"] {
        background-color: #1e293b !important;
        padding: 10px 14px !important;
        border-radius: 10px !important;
        text-align: center !important;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1) !important;
    }

    /* Enforce clear white text for metric labels, numbers, and percentage deltas */
    div[data-testid="stMetric"] label,
    div[data-testid="stMetric"] [data-testid="stMetricValue"],
    div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
        color: #ffffff !important;
        font-weight: bold !important;
    }

    /* --- MOBILE GRID OVERRIDES --- */
    div[data-testid="stHorizontalBlock"] {
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        gap: 6px !important;
        margin-bottom: 6px !important;
    }

    div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
        flex: 1 1 18% !important;
        width: 18% !important;
        min-width: 0 !important;
    }

    div[data-testid="column"] button {
        font-size: 22px !important;
        font-weight: bold !important;
        height: 54px !important;
        padding: 0px !important;
        border-radius: 8px !important;
    }

    /* Larger review screen text */
    .review-user-spelled {
        font-size: 26px !important;
        font-weight: 600 !important;
        margin-top: 12px !important;
        margin-bottom: 8px !important;
    }

    .review-correct-spelled {
        font-size: 28px !important;
        font-weight: bold !important;
        color: #d32f2f !important;
        margin-bottom: 12px !important;
    }

    .review-correct-success {
        font-size: 28px !important;
        font-weight: bold !important;
        color: #2e7d32 !important;
        margin-bottom: 12px !important;
    }
    </style>
""",
    unsafe_allow_html=True,
)

SHEET_ID = "1Un0T57SniiumOozglDfeeYnGMyuZk0F71DlADSDTrZU"


# --- Google Sheets Authentication & Data Loading ---
@st.cache_resource
def get_gspread_client():
    """Authenticates with Google Sheets using Streamlit Secrets or local credentials."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = json.loads(st.secrets["gcp_service_account"])
            creds = Credentials.from_service_account_info(
                creds_dict, scopes=scopes
            )
            return gspread.authorize(creds)
    except Exception:
        pass

    creds_path = os.path.join(os.path.dirname(__file__), "credentials.json")
    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    return gspread.authorize(creds)


@st.cache_data(ttl=60)
def load_spelling_data():
    """Loads the words table from Google Sheets."""
    client = get_gspread_client()
    sheet = client.open_by_key(SHEET_ID).worksheet("spelling_words")
    df = pd.DataFrame(sheet.get_all_records())
    df.columns = [col.strip() for col in df.columns]
    return df


def append_result_to_sheet(batch_id, word, user_input, is_correct):
    """Appends student attempt into the 'Results' sheet tab."""
    try:
        client = get_gspread_client()
        results_sheet = client.open_by_key(SHEET_ID).worksheet("Results")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        results_sheet.append_row(
            [now_str, str(batch_id), word, user_input, str(is_correct)]
        )
    except Exception as e:
        st.error(f"Failed to record result to Google Sheets: {e}")


# --- Text-to-Speech Helper (iPad / iOS Native Click Listener) ---
def render_audio_player(text):
    """Renders an interactive audio button that executes speech synthesis natively on touch."""
    clean_text = text.replace("'", "\\'").replace('"', '\\"')

    html_code = f"""
        <div style="text-align: center; margin-bottom: 10px;">
            <button id="speak-btn" style="
                width: 100%;
                background-color: #ff4b4b;
                color: white;
                border: none;
                padding: 14px 20px;
                font-size: 20px;
                font-weight: bold;
                border-radius: 8px;
                cursor: pointer;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            ">
                🔊 Read Word Aloud
            </button>
        </div>
        <script>
            function speakWord() {{
                if ('speechSynthesis' in window) {{
                    window.speechSynthesis.cancel();
                    var msg = new SpeechSynthesisUtterance('{clean_text}');
                    msg.rate = 0.85;
                    msg.lang = 'en-US';
                    window.speechSynthesis.speak(msg);
                }}
            }}

            document.getElementById('speak-btn').addEventListener('click', speakWord);

            window.addEventListener('load', function() {{
                speakWord();
            }});
        </script>
    """
    st.components.v1.html(html_code, height=65)


# --- Visual Animation Helper for Incorrect Selection ---
def trigger_poop_rain():
    """Launches animated floating poop emojis when a selection is incorrect."""
    js_code = """
        <script>
            (function() {
                var parentDoc = window.parent.document;
                var body = parentDoc.body;

                var overlay = parentDoc.createElement('div');
                overlay.style.position = 'fixed';
                overlay.style.top = '0';
                overlay.style.left = '0';
                overlay.style.width = '100vw';
                overlay.style.height = '100vh';
                overlay.style.pointerEvents = 'none';
                overlay.style.zIndex = '999999';
                overlay.style.overflow = 'hidden';

                for (var i = 0; i < 25; i++) {
                    (function(index) {
                        var poop = parentDoc.createElement('div');
                        poop.innerText = '💩';
                        poop.style.position = 'absolute';
                        poop.style.fontSize = (Math.random() * 25 + 30) + 'px';
                        poop.style.left = (Math.random() * 90 + 5) + 'vw';
                        poop.style.bottom = '-60px';
                        poop.style.transition = 'transform ' + (2 + Math.random() * 1.5) + 's ease-out, opacity 2.5s ease-out';

                        overlay.appendChild(poop);

                        setTimeout(function() {
                            var xShift = (Math.random() - 0.5) * 300;
                            var yShift = -110;
                            var rot = (Math.random() - 0.5) * 720;
                            poop.style.transform = 'translate(' + xShift + 'px, ' + yShift + 'vh) rotate(' + rot + 'deg)';
                            poop.style.opacity = '0';
                        }, index * 50);
                    })(i);
                }

                body.appendChild(overlay);
                setTimeout(function() {
                    overlay.remove();
                }, 4000);
            })();
        </script>
    """
    st.components.v1.html(js_code, height=0, width=0)


# --- Load Data ---
try:
    df = load_spelling_data()
except Exception as e:
    st.error(
        f"Error connecting to Google Sheets. Check credentials/permissions. ({e})"
    )
    st.stop()

# --- App UI & Logic ---
st.title("✏️ Spelling Practice App")

# 1. Batch Selection & Session Score Display
unique_batches = sorted(df["Batch"].astype(str).unique())

col_batch, col_score = st.columns([3, 2])
with col_batch:
    selected_batch = st.selectbox("Select Batch ID:", unique_batches)

# Reset state when switching batches
if (
        "current_batch" not in st.session_state
        or st.session_state.current_batch != selected_batch
):
    st.session_state.current_batch = selected_batch
    batch_df = df[df["Batch"].astype(str) == selected_batch]
    st.session_state.word_queue = batch_df.to_dict("records")
    random.shuffle(st.session_state.word_queue)
    st.session_state.current_word_data = None
    st.session_state.user_input = ""
    st.session_state.used_indices = []
    st.session_state.submitted = False
    st.session_state.is_correct = False
    st.session_state.correct_count = 0
    st.session_state.total_count = 0

with col_score:
    total = st.session_state.get("total_count", 0)
    correct = st.session_state.get("correct_count", 0)
    pct = f"{int(correct / total * 100)}%" if total > 0 else "0%"
    st.metric(label="Session Score", value=f"{correct} / {total}", delta=pct)


def next_word():
    """Selects the next word in random order, loops indefinitely, and prepares letters."""
    if not st.session_state.word_queue:
        batch_df = df[df["Batch"].astype(str) == st.session_state.current_batch]
        st.session_state.word_queue = batch_df.to_dict("records")
        random.shuffle(st.session_state.word_queue)

    st.session_state.current_word_data = st.session_state.word_queue.pop(0)
    word = str(st.session_state.current_word_data["Word"]).strip()

    letters = list(enumerate(word.lower()))
    random.shuffle(letters)
    st.session_state.scrambled_letters = letters
    st.session_state.used_indices = []
    st.session_state.user_input = ""
    st.session_state.submitted = False
    st.session_state.is_correct = False


# Initialize first word
if st.session_state.current_word_data is None:
    next_word()

current_item = st.session_state.current_word_data
target_word = str(current_item["Word"]).strip()
phrase = f"Your next word is {target_word}, as in {current_item['AsIn']}"

# Render iPad-compatible native audio trigger button
render_audio_player(phrase)

st.markdown("---")

# ---------------------------------------------------------
# PHASE 1: INPUT PHASE (User taps letters and submits)
# ---------------------------------------------------------
if not st.session_state.submitted:
    st.subheader("Your Input:")
    st.text_input(
        label="Spelled word",
        value=st.session_state.user_input,
        disabled=True,
        label_visibility="collapsed",
    )

    st.write("**Tap letters to spell:**")

    # Render letters in 5-column chunked rows
    NUM_COLS = 5
    scrambled = st.session_state.scrambled_letters

    for row_start in range(0, len(scrambled), NUM_COLS):
        chunk = scrambled[row_start: row_start + NUM_COLS]
        cols = st.columns(NUM_COLS)
        for col_idx, (orig_idx, char) in enumerate(chunk):
            is_used = orig_idx in st.session_state.used_indices
            with cols[col_idx]:
                if st.button(
                        char.upper(),
                        key=f"btn_{orig_idx}_{row_start + col_idx}",
                        disabled=is_used,
                        use_container_width=True,
                ):
                    st.session_state.user_input += char
                    st.session_state.used_indices.append(orig_idx)
                    st.rerun()

    st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)

    col_erase, col_submit = st.columns(2)
    with col_erase:
        if st.button("⌫ Erase", use_container_width=True):
            if st.session_state.user_input:
                st.session_state.user_input = st.session_state.user_input[:-1]
                if st.session_state.used_indices:
                    st.session_state.used_indices.pop()
                st.rerun()

    with col_submit:
        if st.button(
                "✅ Submit",
                disabled=len(st.session_state.user_input) == 0,
                use_container_width=True,
        ):
            st.session_state.submitted = True
            is_correct = (
                    st.session_state.user_input.strip().lower()
                    == target_word.lower()
            )
            st.session_state.is_correct = is_correct

            # Update score counter
            st.session_state.total_count += 1
            if is_correct:
                st.session_state.correct_count += 1

            append_result_to_sheet(
                selected_batch,
                target_word,
                st.session_state.user_input,
                is_correct,
            )
            st.rerun()

# ---------------------------------------------------------
# PHASE 2: REVIEW PHASE (Shows feedback & pauses for Next Word)
# ---------------------------------------------------------
else:
    if st.session_state.is_correct:
        st.balloons()
        st.success("🎉 **Awesome job! That is spelled correctly!**")
        st.markdown(
            f"<div class='review-correct-success'>Word: {target_word}</div>",
            unsafe_allow_html=True,
        )
    else:
        trigger_poop_rain()
        st.error("❌ **Not quite!**")
        st.markdown(
            f"<div class='review-user-spelled'>You spelled: <code>{st.session_state.user_input}</code></div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div class='review-correct-spelled'>Correct spelling: {target_word}</div>",
            unsafe_allow_html=True,
        )

    st.markdown("---")

    if st.button("➡️ Next Word", type="primary", use_container_width=True):
        next_word()
        st.rerun()