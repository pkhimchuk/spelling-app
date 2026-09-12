import json
import os
import random
from datetime import datetime

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="Spelling Practice App",
    page_icon="✏️",
    layout="centered",
)

# =========================================================
# CUSTOM CSS
# =========================================================

st.markdown(
    """
    <style>

    /* =====================================================
       GENERAL APP
       ===================================================== */

    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 1.5rem !important;
        max-width: 480px !important;
    }

    div[data-testid="stHeader"] {
        height: 0 !important;
    }


    /* =====================================================
       SPELLING INPUT
       ===================================================== */

    div[data-testid="stTextInput"] input {
        font-size: 28px !important;
        font-weight: bold !important;
        text-align: center !important;
        height: 50px !important;
        letter-spacing: 3px !important;
    }


    /* =====================================================
       SCORE
       ===================================================== */

    div[data-testid="stMetric"] {
        background-color: #1e293b !important;
        padding: 8px 12px !important;
        border-radius: 8px !important;
        text-align: center !important;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1) !important;
        margin-top: 4px !important;
        margin-bottom: 12px !important;
    }

    div[data-testid="stMetric"] label,
    div[data-testid="stMetric"] [data-testid="stMetricValue"],
    div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
        color: white !important;
        font-weight: bold !important;
    }


    /* =====================================================
       CUSTOM LETTER KEYBOARD

       IMPORTANT:
       This keyboard does NOT use st.columns().
       It is a genuine CSS grid.
       ===================================================== */

    .spelling-keyboard-wrapper {
        width: 100%;
        display: flex;
        justify-content: center;
        box-sizing: border-box;
        padding: 4px 0 8px 0;
    }

    .spelling-keyboard {
        display: grid;

        /* EXACTLY 5 TILES PER ROW */
        grid-template-columns: repeat(5, 52px);

        gap: 8px;

        justify-content: center;
        align-content: start;

        width: max-content;
        max-width: 100%;

        box-sizing: border-box;
    }


    /* =====================================================
       INDIVIDUAL LETTER TILE
       ===================================================== */

    .spelling-key {
        width: 52px !important;
        min-width: 52px !important;
        max-width: 52px !important;

        height: 48px !important;
        min-height: 48px !important;
        max-height: 48px !important;

        box-sizing: border-box !important;

        margin: 0 !important;
        padding: 0 !important;

        display: flex;
        align-items: center;
        justify-content: center;

        border: 1px solid #cbd5e1;
        border-radius: 8px;

        background: #f8fafc;
        color: #0f172a;

        font-family: inherit;
        font-size: 18px;
        font-weight: 700;

        box-shadow: 0 2px 0 #94a3b8;

        cursor: pointer;

        -webkit-tap-highlight-color: transparent;

        user-select: none;

        transition:
            transform 0.05s ease,
            box-shadow 0.05s ease,
            background-color 0.1s ease;
    }

    .spelling-key:hover {
        background: #ffffff;
    }

    .spelling-key:active {
        transform: translateY(2px);
        box-shadow: none;
    }


    /* =====================================================
       USED LETTER
       ===================================================== */

    .spelling-key.used {
        background: #e2e8f0;
        color: #94a3b8;

        border-color: #cbd5e1;

        box-shadow: none;

        opacity: 0.35;

        cursor: default;
    }


    /* =====================================================
       MOBILE

       Still 5 columns.
       Tiles remain compact.
       ===================================================== */

    @media (max-width: 600px) {

        .block-container {
            padding-left: 12px !important;
            padding-right: 12px !important;
        }

        .spelling-keyboard {
            grid-template-columns: repeat(5, 48px);
            gap: 6px;
        }

        .spelling-key {
            width: 48px !important;
            min-width: 48px !important;
            max-width: 48px !important;

            height: 46px !important;
            min-height: 46px !important;
            max-height: 46px !important;

            font-size: 17px;
        }
    }


    /* =====================================================
       VERY SMALL PHONES

       5 x 44px still fits comfortably.
       ===================================================== */

    @media (max-width: 350px) {

        .spelling-keyboard {
            grid-template-columns: repeat(5, 44px);
            gap: 5px;
        }

        .spelling-key {
            width: 44px !important;
            min-width: 44px !important;
            max-width: 44px !important;

            height: 44px !important;
            min-height: 44px !important;
            max-height: 44px !important;

            font-size: 16px;
        }
    }


    /* =====================================================
       REVIEW SCREEN
       ===================================================== */

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

# =========================================================
# GOOGLE SHEETS
# =========================================================

SHEET_ID = "1Un0T57SniiumOozglDfeeYnGMyuZk0F71DlADSDTrZU"


@st.cache_resource
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    try:

        if "gcp_service_account" in st.secrets:
            creds_dict = json.loads(
                st.secrets["gcp_service_account"]
            )

            creds = Credentials.from_service_account_info(
                creds_dict,
                scopes=scopes,
            )

            return gspread.authorize(creds)

    except Exception:
        pass

    # Local development

    creds_path = os.path.join(
        os.path.dirname(__file__),
        "credentials.json",
    )

    creds = Credentials.from_service_account_file(
        creds_path,
        scopes=scopes,
    )

    return gspread.authorize(creds)


@st.cache_data(ttl=60)
def load_spelling_data():
    client = get_gspread_client()

    sheet = client.open_by_key(
        SHEET_ID
    ).worksheet("spelling_words")

    df = pd.DataFrame(
        sheet.get_all_records()
    )

    df.columns = [
        str(col).strip()
        for col in df.columns
    ]

    return df


def append_result_to_sheet(
        batch_id,
        word,
        user_input,
        is_correct,
):
    try:

        client = get_gspread_client()

        results_sheet = client.open_by_key(
            SHEET_ID
        ).worksheet("Results")

        now_str = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        results_sheet.append_row(
            [
                now_str,
                str(batch_id),
                word,
                user_input,
                str(is_correct),
            ]
        )

    except Exception as e:

        st.error(
            f"Failed to record result to Google Sheets: {e}"
        )


# =========================================================
# TEXT TO SPEECH
# =========================================================

def render_audio_player(text):
    clean_text = (
        text
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace('"', '\\"')
        .replace("\n", " ")
    )

    html_code = f"""
    <div style="
        text-align: center;
        margin-bottom: 10px;
    ">

        <button
            id="speak-btn"
            style="
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
            "
        >
            🔊 Read Word Aloud
        </button>

    </div>

    <script>

    function speakWord() {{

        if ('speechSynthesis' in window) {{

            window.speechSynthesis.cancel();

            var msg =
                new SpeechSynthesisUtterance(
                    '{clean_text}'
                );

            msg.rate = 0.85;
            msg.lang = 'en-US';

            window.speechSynthesis.speak(msg);
        }}
    }}

    document
        .getElementById('speak-btn')
        .addEventListener(
            'click',
            speakWord
        );

    window.addEventListener(
        'load',
        function() {{
            speakWord();
        }}
    );

    </script>
    """

    st.components.v1.html(
        html_code,
        height=60,
    )


# =========================================================
# INCORRECT ANSWER ANIMATION
# =========================================================

def trigger_poop_rain():
    js_code = """
    <script>

    (function() {

        var parentDoc =
            window.parent.document;

        var body =
            parentDoc.body;

        var overlay =
            parentDoc.createElement('div');

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

                var poop =
                    parentDoc.createElement('div');

                poop.innerText = '💩';

                poop.style.position = 'absolute';

                poop.style.fontSize =
                    (Math.random() * 20 + 25) + 'px';

                poop.style.left =
                    (Math.random() * 90 + 5) + 'vw';

                poop.style.bottom = '-60px';

                poop.style.transition =
                    'transform ' +
                    (2 + Math.random() * 1.5) +
                    's ease-out, opacity 2.5s ease-out';

                overlay.appendChild(poop);

                setTimeout(function() {

                    var xShift =
                        (Math.random() - 0.5) * 250;

                    var yShift = -110;

                    var rot =
                        (Math.random() - 0.5) * 720;

                    poop.style.transform =
                        'translate(' +
                        xShift +
                        'px, ' +
                        yShift +
                        'vh) rotate(' +
                        rot +
                        'deg)';

                    poop.style.opacity = '0';

                }, index * 50);

            })(i);
        }

        body.appendChild(overlay);

        setTimeout(
            function() {
                overlay.remove();
            },
            4000
        );

    })();

    </script>
    """

    st.components.v1.html(
        js_code,
        height=0,
        width=0,
    )


# =========================================================
# LOAD DATA
# =========================================================

try:

    df = load_spelling_data()

except Exception as e:

    st.error(
        "Error connecting to Google Sheets. "
        f"Check credentials/permissions. ({e})"
    )

    st.stop()

# =========================================================
# TITLE
# =========================================================

st.title("✏️ Spelling Practice")

# =========================================================
# BATCH SELECTION
# =========================================================

unique_batches = sorted(
    df["Batch"]
    .astype(str)
    .unique()
)

selected_batch = st.selectbox(
    "Select Batch ID:",
    unique_batches,
)

# =========================================================
# INITIALISE SESSION
# =========================================================

if (
        "current_batch" not in st.session_state
        or st.session_state.current_batch != selected_batch
):
    st.session_state.current_batch = selected_batch

    batch_df = df[
        df["Batch"].astype(str)
        == selected_batch
        ]

    st.session_state.word_queue = (
        batch_df.to_dict("records")
    )

    random.shuffle(
        st.session_state.word_queue
    )

    st.session_state.current_word_data = None

    st.session_state.user_input = ""

    st.session_state.used_indices = []

    st.session_state.submitted = False

    st.session_state.is_correct = False

    st.session_state.correct_count = 0

    st.session_state.total_count = 0

# =========================================================
# SCORE
# =========================================================

total = st.session_state.get(
    "total_count",
    0,
)

correct = st.session_state.get(
    "correct_count",
    0,
)

if total > 0:

    pct = f"{int(correct / total * 100)}%"

else:

    pct = "0%"

st.metric(
    label="Session Score",
    value=f"{correct} / {total}",
    delta=pct,
)


# =========================================================
# NEXT WORD
# =========================================================

def next_word():
    if not st.session_state.word_queue:
        batch_df = df[
            df["Batch"].astype(str)
            == st.session_state.current_batch
            ]

        st.session_state.word_queue = (
            batch_df.to_dict("records")
        )

        random.shuffle(
            st.session_state.word_queue
        )

    st.session_state.current_word_data = (
        st.session_state.word_queue.pop(0)
    )

    word = str(
        st.session_state.current_word_data["Word"]
    ).strip()

    # Keep the original position of each letter.
    #
    # This is important for words with duplicate
    # letters such as APPLE.

    letters = list(
        enumerate(word.lower())
    )

    random.shuffle(letters)

    st.session_state.scrambled_letters = letters

    st.session_state.used_indices = []

    st.session_state.user_input = ""

    st.session_state.submitted = False

    st.session_state.is_correct = False


# =========================================================
# GET FIRST WORD
# =========================================================

if st.session_state.current_word_data is None:
    next_word()

# =========================================================
# CURRENT WORD
# =========================================================

current_item = (
    st.session_state.current_word_data
)

target_word = str(
    current_item["Word"]
).strip()

phrase = (
    f"Your next word is {target_word}, "
    f"as in {current_item['AsIn']}"
)

# =========================================================
# AUDIO
# =========================================================

render_audio_player(
    phrase
)

st.markdown("---")

# =========================================================
# INPUT PHASE
# =========================================================

if not st.session_state.submitted:

    st.subheader("Your Input:")

    # -----------------------------------------------------
    # DISPLAY USER'S SPELLING
    # -----------------------------------------------------

    st.text_input(
        label="Spelled word",
        value=st.session_state.user_input,
        disabled=True,
        label_visibility="collapsed",
    )

    st.write("**Tap letters to spell:**")

    # =====================================================
    # LETTER KEYBOARD
    #
    # This is deliberately NOT made with st.columns().
    #
    # We create one Streamlit button per letter inside
    # a fixed-width container.
    # =====================================================

    scrambled = (
        st.session_state.scrambled_letters
    )

    NUM_COLS = 5

    # -----------------------------------------------------
    # IMPORTANT:
    #
    # We use a fixed-width Streamlit container.
    # Each row is still made with Streamlit buttons, but
    # CSS forces the buttons themselves to be 52px/48px.
    #
    # No global stHorizontalBlock rules are used.
    # -----------------------------------------------------

    keyboard_html = """
    <div class="spelling-keyboard-wrapper">
        <div class="spelling-keyboard">
    """

    # We don't put the buttons themselves into the HTML
    # because Streamlit needs to receive the clicks.
    #
    # The HTML below is only the visual wrapper.

    st.markdown(
        keyboard_html,
        unsafe_allow_html=True,
    )

    # -----------------------------------------------------
    # Render rows.
    #
    # Each row has up to 5 letters.
    # -----------------------------------------------------

    for row_start in range(
            0,
            len(scrambled),
            NUM_COLS,
    ):

        chunk = scrambled[
            row_start:
            row_start + NUM_COLS
        ]

        # Use Streamlit columns only INSIDE this controlled
        # keyboard area.
        #
        # The CSS below forces each one to remain 52px.
        #
        # Empty columns are added so the last row doesn't
        # stretch.

        cols = st.columns(
            NUM_COLS,
            gap=None,
        )

        for col_idx in range(NUM_COLS):

            with cols[col_idx]:

                if col_idx < len(chunk):

                    orig_idx, char = chunk[col_idx]

                    is_used = (
                            orig_idx
                            in st.session_state.used_indices
                    )

                    if st.button(
                            char.upper(),

                            key=(
                                    f"letter_"
                                    f"{orig_idx}_"
                                    f"{row_start + col_idx}"
                            ),

                            disabled=is_used,

                            use_container_width=True,
                    ):
                        st.session_state.user_input += char

                        st.session_state.used_indices.append(
                            orig_idx
                        )

                        st.rerun()

    # Close the visual wrapper.

    st.markdown(
        """
        </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div style='margin-top: 10px;'></div>",
        unsafe_allow_html=True,
    )

    # =====================================================
    # ERASE / SUBMIT
    # =====================================================

    col_erase, col_submit = st.columns(
        2,
        gap="small",
    )

    with col_erase:

        if st.button(
                "⌫ Erase",
                use_container_width=True,
        ):

            if st.session_state.user_input:

                st.session_state.user_input = (
                    st.session_state.user_input[:-1]
                )

                if st.session_state.used_indices:
                    st.session_state.used_indices.pop()

                st.rerun()

    with col_submit:

        if st.button(
                "✅ Submit",

                disabled=(
                        len(
                            st.session_state.user_input
                        ) == 0
                ),

                use_container_width=True,
        ):

            st.session_state.submitted = True

            is_correct = (
                    st.session_state.user_input
                    .strip()
                    .lower()
                    ==
                    target_word.lower()
            )

            st.session_state.is_correct = (
                is_correct
            )

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


# =========================================================
# REVIEW PHASE
# =========================================================

else:

    # -----------------------------------------------------
    # CORRECT ANSWER
    # -----------------------------------------------------

    if st.session_state.is_correct:

        st.balloons()

        st.success(
            "🎉 **Awesome job! "
            "That is spelled correctly!**"
        )

        st.markdown(
            (
                "<div class='review-correct-success'>"
                f"Word: {target_word}"
                "</div>"
            ),
            unsafe_allow_html=True,
        )


    # -----------------------------------------------------
    # INCORRECT ANSWER
    # -----------------------------------------------------

    else:

        trigger_poop_rain()

        st.error(
            "❌ **Not quite!**"
        )

        st.markdown(
            (
                "<div class='review-user-spelled'>"
                "You spelled: "
                f"<code>{st.session_state.user_input}</code>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )

        st.markdown(
            (
                "<div class='review-correct-spelled'>"
                f"Correct spelling: {target_word}"
                "</div>"
            ),
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # -----------------------------------------------------
    # NEXT WORD
    # -----------------------------------------------------

    if st.button(
            "➡️ Next Word",
            type="primary",
            use_container_width=True,
    ):
        next_word()

        st.rerun()

