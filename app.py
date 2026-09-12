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

# Custom CSS: Clean container styling
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 1.5rem !important;
        max-width: 480px !important;
    }

    div[data-testid="stHeader"] {
        height: 0px !important;
    }

    div[data-testid="stTextInput"] input {
        font-size: 28px !important;
        font-weight: bold !important;
        text-align: center !important;
        height: 50px !important;
        letter-spacing: 3px !important;
    }

    /* --- SCORE METRIC STYLING --- */
    div[data-testid="stMetric"] {
        background-color: #1e293b !important;
        padding: 8px 12px !important;
        border-radius: 8px !important;
        text-align: center !important;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1) !important;
        margin-top: 4px !important;
        margin-bottom: 12px !important;
    }

    div[data-testid="stMetric"] label,
    div[data-testid="stMetric"] [data-testid="stMetricValue"],
    div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
        color: #ffffff !important;
        font-weight: bold !important;
    }

    /* Review Screen typography */
    .review-user-spelled {
        font-size: 22px !important;
        font-weight: 600 !important;
        margin-top: 8px !important;
        margin-bottom: 6px !important;
    }

    .review-correct-spelled {
        font-size: 24px !important;
        font-weight: bold !important;
        color: #d32f2f !important;
        margin-bottom: 10px !important;
    }

    .review-correct-success {
        font-size: 24px !important;
        font-weight: bold !important;
        color: #2e7d32 !important;
        margin-bottom: 10px !important;
    }
    </style>
""",
    unsafe_allow_html=True,
)

SHEET_ID = "1Un0T57SniiumOozglDfeeYnGMyuZk0F71DlADSDTrZU"


# --- Google Sheets Authentication & Data Loading ---
@st.cache_resource
def get_gspread_client():
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
    client = get_gspread_client()
    sheet = client.open_by_key(SHEET_ID).worksheet("spelling_words")
    df = pd.DataFrame(sheet.get_all_records())
    df.columns = [col.strip() for col in df.columns]
    return df


def append_result_to_sheet(batch_id, word, user_input, is_correct):
    try:
        client = get_gspread_client()
        results_sheet = client.open_by_key(SHEET_ID).worksheet("Results")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        results_sheet.append_row(
            [now_str, str(batch_id), word, user_input, str(is_correct)]
        )
    except Exception as e:
        st.error(f"Failed to record result to Google Sheets: {e}")


# --- Text-to-Speech Helper ---
def render_audio_player(text):
    clean_text = text.replace("'", "\\'").replace('"', '\\"')
    html_code = f"""
        <div style="text-align: center; margin-bottom: 10px;">
            <button id="speak-btn" style="
                width: 100%;
                background-color: #ff4b4b;
                color: white;
                border: none;
                padding: 12px 16px;
                font-size: 18px;
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
    st.components.v1.html(html_code, height=60)


# --- Visual Animation Helper for Incorrect Selection ---
def trigger_poop_rain():
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

                for (var i = 0; i < 20; i++) {
                    (function(index) {
                        var poop = parentDoc.createElement('div');
                        poop.innerText = '💩';
                        poop.style.position = 'absolute';
                        poop.style.fontSize = (Math.random() * 20 + 25) + 'px';
                        poop.style.left = (Math.random() * 90 + 5) + 'vw';
                        poop.style.bottom = '-60px';
                        poop.style.transition = 'transform ' + (2 + Math.random() * 1.5) + 's ease-out, opacity 2.5s ease-out';
                        overlay.appendChild(poop);

                        setTimeout(function() {
                            var xShift = (Math.random() - 0.5) * 250;
                            var yShift = -110;
                            var rot = (Math.random() - 0.5) * 720;
                            poop.style.transform = 'translate(' + xShift + 'px, ' + yShift + 'vh) rotate(' + rot + 'deg)';
                            poop.style.opacity = '0';
                        }, index * 50);
                    })(i);
                }

                body.appendChild(overlay);
                setTimeout(function() { overlay.remove(); }, 4000);
            })();
        </script>
    """
    st.components.v1.html(js_code, height=0, width=0)


# --- Native HTML/JS Touch Keyboard Component ---
def render_letter_keyboard(scrambled_letters, used_indices):
    tiles_data = [
        {
            "orig_idx": idx,
            "char": char.upper(),
            "used": idx in used_indices,
        }
        for idx, char in scrambled_letters
    ]
    tiles_json = json.dumps(tiles_data)

    component_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            margin: 0;
            padding: 4px;
            background: transparent;
        }}
        .keyboard-grid {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            justify-content: center;
            margin-bottom: 12px;
        }}
        .tile {{
            flex: 1 1 18%;
            max-width: 19%;
            height: 48px;
            font-size: 20px;
            font-weight: 700;
            border-radius: 8px;
            border: 1px solid #cbd5e1;
            background-color: #f8fafc;
            color: #0f172a;
            box-shadow: 0 2px 0 #94a3b8;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            user-select: none;
            -webkit-tap-highlight-color: transparent;
            transition: transform 0.05s ease;
        }}
        .tile:active:not(.disabled) {{
            transform: translateY(2px);
            box-shadow: 0 0 0 #94a3b8;
        }}
        .tile.disabled {{
            background-color: #e2e8f0;
            color: #94a3b8;
            border-color: #cbd5e1;
            box-shadow: none;
            opacity: 0.35;
            cursor: default;
            pointer-events: none;
        }}
        .actions-container {{
            display: flex;
            gap: 8px;
            width: 100%;
        }}
        .action-btn {{
            flex: 1;
            height: 46px;
            font-size: 16px;
            font-weight: bold;
            border-radius: 8px;
            border: 1px solid #cbd5e1;
            background-color: #ffffff;
            color: #0f172a;
            cursor: pointer;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            display: flex;
            align-items: center;
            justify-content: center;
            -webkit-tap-highlight-color: transparent;
        }}
        .action-btn.submit {{
            background-color: #ff4b4b;
            color: white;
            border: none;
        }}
        .action-btn:active {{
            opacity: 0.8;
        }}
    </style>
    </head>
    <body>

    <div class="keyboard-grid" id="grid"></div>

    <div class="actions-container">
        <button class="action-btn" onclick="triggerAction('erase')">⌫ Erase</button>
        <button class="action-btn submit" onclick="triggerAction('submit')">✅ Submit</button>
    </div>

    <script>
        const tiles = {tiles_json};
        const grid = document.getElementById('grid');

        function render() {{
            grid.innerHTML = '';
            tiles.forEach(t => {{
                const btn = document.createElement('div');
                btn.className = 'tile' + (t.used ? ' disabled' : '');
                btn.innerText = t.char;
                if (!t.used) {{
                    btn.onclick = () => {{
                        window.parent.location.search = '?action=tap&char=' + encodeURIComponent(t.char.toLowerCase()) + '&idx=' + t.orig_idx;
                    }};
                }}
                grid.appendChild(btn);
            }});
        }}

        function triggerAction(act) {{
            window.parent.location.search = '?action=' + act;
        }}

        render();
    </script>
    </body>
    </html>
    """
    num_rows = (len(scrambled_letters) + 4) // 5
    total_height = num_rows * 54 + 65
    st.components.v1.html(component_html, height=total_height)


# --- Load Data ---
try:
    df = load_spelling_data()
except Exception as e:
    st.error(
        f"Error connecting to Google Sheets. Check credentials/permissions. ({e})"
    )
    st.stop()

st.title("✏️ Spelling Practice")

# --- Batch Selection & Score ---
unique_batches = sorted(df["Batch"].astype(str).unique())
selected_batch = st.selectbox("Select Batch ID:", unique_batches)

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

total = st.session_state.get("total_count", 0)
correct = st.session_state.get("correct_count", 0)
pct = f"{int(correct / total * 100)}%" if total > 0 else "0%"
st.metric(label="Session Score", value=f"{correct} / {total}", delta=pct)


def next_word():
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


if st.session_state.current_word_data is None:
    next_word()

current_item = st.session_state.current_word_data
target_word = str(current_item["Word"]).strip()

# --- Process Query Params from HTML Keyboard Component ---
params = st.query_params
if "action" in params:
    action = params["action"]
    if action == "tap":
        char = params.get("char", "")
        idx_str = params.get("idx", "-1")
        try:
            orig_idx = int(idx_str)
            if orig_idx not in st.session_state.used_indices:
                st.session_state.user_input += char
                st.session_state.used_indices.append(orig_idx)
        except ValueError:
            pass
    elif action == "erase":
        if st.session_state.user_input:
            st.session_state.user_input = st.session_state.user_input[:-1]
            if st.session_state.used_indices:
                st.session_state.used_indices.pop()
    elif action == "submit":
        if len(st.session_state.user_input) > 0 and not st.session_state.submitted:
            st.session_state.submitted = True
            is_correct = (
                    st.session_state.user_input.strip().lower()
                    == target_word.lower()
            )
            st.session_state.is_correct = is_correct

            st.session_state.total_count += 1
            if is_correct:
                st.session_state.correct_count += 1

            append_result_to_sheet(
                selected_batch,
                target_word,
                st.session_state.user_input,
                is_correct,
            )
    st.query_params.clear()
    st.rerun()

phrase = f"Your next word is {target_word}, as in {current_item['AsIn']}"
render_audio_player(phrase)

st.markdown("---")

# ---------------------------------------------------------
# PHASE 1: INPUT PHASE
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
    render_letter_keyboard(
        st.session_state.scrambled_letters, st.session_state.used_indices
    )

# ---------------------------------------------------------
# PHASE 2: REVIEW PHASE
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