import json
import os
import random
from datetime import datetime

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

SHEET_ID = "1Un0T57SniiumOozglDfeeYnGMyuZk0F71DlADSDTrZU"
RESULT_COLUMNS = ["Timestamp", "Batch ID", "Word", "User Input", "Correct"]

st.set_page_config(
    page_title="Spelling Practice App",
    page_icon="✏️",
    layout="centered",
)

st.markdown(
    """
    <style>
    .block-container {
        max-width: 480px !important;
        padding-top: 1rem !important;
        padding-bottom: 1.5rem !important;
    }

    div[data-testid="stHeader"] {
        height: 0 !important;
    }

    div[data-testid="stTextInput"] input {
        font-size: 28px !important;
        font-weight: 700 !important;
        text-align: center !important;
        height: 50px !important;
        letter-spacing: 3px !important;
    }

    div[data-testid="stMetric"] {
        background: #1e293b !important;
        padding: 8px 12px !important;
        border-radius: 8px !important;
        text-align: center !important;
        margin: 4px 0 12px !important;
    }

    div[data-testid="stMetric"] label,
    div[data-testid="stMetric"] [data-testid="stMetricValue"],
    div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
        color: white !important;
        font-weight: 700 !important;
    }

    @media (max-width: 600px) {
        .block-container {
            padding-left: 12px !important;
            padding-right: 12px !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


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
                creds_dict,
                scopes=scopes,
            )
            return gspread.authorize(creds)
    except Exception:
        pass

    credentials_file = os.path.join(os.path.dirname(__file__), "credentials.json")
    creds = Credentials.from_service_account_file(
        credentials_file,
        scopes=scopes,
    )
    return gspread.authorize(creds)


@st.cache_data(ttl=60)
def load_spelling_data():
    sheet = get_gspread_client().open_by_key(SHEET_ID).worksheet("spelling_words")
    df = pd.DataFrame(sheet.get_all_records())
    df.columns = [str(column).strip() for column in df.columns]

    required = {"Batch", "Word", "AsIn"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"spelling_words is missing required columns: {', '.join(sorted(missing))}"
        )

    df["Batch"] = df["Batch"].astype(str).str.strip()
    df["Word"] = df["Word"].astype(str).str.strip()
    df["AsIn"] = df["AsIn"].fillna("").astype(str).str.strip()
    return df


def append_result_to_sheet(batch_id, word, user_input, is_correct):
    try:
        results_sheet = get_gspread_client().open_by_key(SHEET_ID).worksheet("Results")
        results_sheet.append_row(
            [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                str(batch_id),
                str(word),
                str(user_input),
                str(bool(is_correct)),
            ]
        )
        load_results_data.clear()
    except Exception as exc:
        st.error(f"Failed to record result to Google Sheets: {exc}")


@st.cache_data(ttl=15)
def load_results_data():
    sheet = get_gspread_client().open_by_key(SHEET_ID).worksheet("Results")
    values = sheet.get_all_values()

    if not values:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    rows = values[1:]
    data = []
    for row in rows:
        row = row + [""] * (5 - len(row))
        data.append(row[:5])

    df = pd.DataFrame(data, columns=RESULT_COLUMNS)

    for column in ["Batch ID", "Word", "User Input"]:
        df[column] = df[column].fillna("").astype(str).str.strip()

    df["Correct"] = (
        df["Correct"]
        .astype(str)
        .str.strip()
        .str.lower()
        .isin({"true", "1", "yes", "y", "correct"})
    )

    return df


def word_priority_stats(batch_id):
    results = load_results_data()
    if results.empty:
        return {}

    batch_results = results[results["Batch ID"] == str(batch_id)]
    if batch_results.empty:
        return {}

    stats = {}
    for word, group in batch_results.groupby("Word"):
        total = len(group)
        correct = int(group["Correct"].sum())
        incorrect_share = 1 - (correct / total)
        stats[word.lower()] = {
            "total": total,
            "correct": correct,
            "incorrect_share": incorrect_share,
        }
    return stats


def build_word_queue(batch_df, batch_id):
    stats = word_priority_stats(batch_id)
    words = batch_df.to_dict("records")
    weighted_words = []

    for item in words:
        word = str(item["Word"]).strip()
        word_stats = stats.get(word.lower())

        if word_stats is None or word_stats["total"] == 0:
            # Unanswered words still get a meaningful chance to appear.
            weight = 2.0
        else:
            # More incorrect answers => higher priority.
            # Minimum weight keeps even consistently-correct words in rotation.
            weight = 1.0 + (4.0 * word_stats["incorrect_share"])

        weighted_words.append((item, weight))

    queue = []
    remaining = weighted_words.copy()

    while remaining:
        items = [item for item, _ in remaining]
        weights = [weight for _, weight in remaining]
        chosen = random.choices(items, weights=weights, k=1)[0]
        queue.append(chosen)
        remaining.pop(items.index(chosen))

    return queue


def reset_practice(batch_id, df):
    batch_df = df[df["Batch"].astype(str) == str(batch_id)]

    if batch_df.empty:
        st.error("This batch contains no words.")
        return

    st.session_state.current_batch = str(batch_id)
    st.session_state.word_queue = build_word_queue(batch_df, batch_id)
    st.session_state.current_word_data = None
    st.session_state.used_indices = []
    st.session_state.user_input = ""
    st.session_state.submitted = False
    st.session_state.is_correct = False
    st.session_state.play_result_animation = False
    st.session_state.correct_count = 0
    st.session_state.total_count = 0


def next_word(df):
    if not st.session_state.word_queue:
        batch_id = st.session_state.current_batch
        batch_df = df[df["Batch"].astype(str) == str(batch_id)]
        st.session_state.word_queue = build_word_queue(batch_df, batch_id)

    st.session_state.current_word_data = st.session_state.word_queue.pop(0)
    word = str(st.session_state.current_word_data["Word"]).strip()

    letters = list(enumerate(word.lower()))
    random.shuffle(letters)

    st.session_state.scrambled_letters = letters
    st.session_state.used_indices = []
    st.session_state.user_input = ""
    st.session_state.submitted = False
    st.session_state.is_correct = False


def render_audio_player(text):
    safe_text = json.dumps(str(text).replace("\n", " "))

    html = f"""
    <div style="text-align:center;margin-bottom:10px;">
        <button id="speak-btn"
                style="width:100%;padding:10px 14px;border:0;border-radius:8px;
                       background:#ff4b4b;color:white;font-size:17px;font-weight:700;
                       cursor:pointer;">
            🔊 Read Word Aloud
        </button>
    </div>

    <script>
    const text = {safe_text};

    function speakWord() {{
        if (!("speechSynthesis" in window)) return;

        window.speechSynthesis.cancel();

        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 0.85;
        utterance.lang = "en-US";
        window.speechSynthesis.speak(utterance);
    }}

    document.getElementById("speak-btn").addEventListener("click", speakWord);

    // iPad/iPhone Safari may require a user gesture before allowing
    // speechSynthesis to continue working automatically. Unlock it once
    // on the parent page, then automatically speak each newly shown word.
    function unlockSpeech() {{
        if (!window.speechSynthesis) return;
        try {{
            const unlock = new SpeechSynthesisUtterance("");
            unlock.volume = 0;
            unlock.rate = 10;
            window.speechSynthesis.cancel();
            window.speechSynthesis.speak(unlock);
            sessionStorage.setItem("spelling_speech_unlocked", "1");
        }} catch (e) {{
            // Ignore browsers that do not permit the unlock call.
        }}
    }}

    function speechIsUnlocked() {{
        try {{
            return sessionStorage.getItem("spelling_speech_unlocked") === "1";
        }} catch (e) {{
            return false;
        }}
    }}

    function installSpeechUnlock() {{
        const parentDoc = window.parent && window.parent.document;
        if (!parentDoc) return;

        const unlock = () => {{
            unlockSpeech();
            parentDoc.removeEventListener("pointerdown", unlock, true);
            parentDoc.removeEventListener("touchstart", unlock, true);
            parentDoc.removeEventListener("click", unlock, true);
        }};

        parentDoc.addEventListener("pointerdown", unlock, true);
        parentDoc.addEventListener("touchstart", unlock, true);
        parentDoc.addEventListener("click", unlock, true);
    }}

    function autoSpeak() {{
        if (!speechIsUnlocked()) return;
        setTimeout(speakWord, 200);
    }}

    installSpeechUnlock();
    window.addEventListener("load", autoSpeak);
    setTimeout(autoSpeak, 500);
    </script>
    """

    st.components.v1.html(html, height=58)


def trigger_poop_rain():
    st.components.v1.html(
        """
        <script>
        const parentDoc = window.parent.document;
        const overlay = parentDoc.createElement("div");

        Object.assign(overlay.style, {
            position: "fixed",
            top: "0",
            left: "0",
            width: "100vw",
            height: "100vh",
            pointerEvents: "none",
            zIndex: "999999",
            overflow: "hidden",
        });

        for (let i = 0; i < 20; i++) {
            const poop = parentDoc.createElement("div");
            poop.innerText = "💩";

            Object.assign(poop.style, {
                position: "absolute",
                fontSize: `${Math.random() * 20 + 25}px`,
                left: `${Math.random() * 90 + 5}vw`,
                bottom: "-60px",
                transition: "transform 2s ease-out, opacity 2.5s ease-out",
            });

            overlay.appendChild(poop);

            setTimeout(() => {
                const x = (Math.random() - 0.5) * 250;
                const rotation = (Math.random() - 0.5) * 720;
                poop.style.transform = `translate(${x}px, -110vh) rotate(${rotation}deg)`;
                poop.style.opacity = "0";
            }, i * 50);
        }

        parentDoc.body.appendChild(overlay);
        setTimeout(() => overlay.remove(), 4000);
        </script>
        """,
        height=0,
        width=0,
    )


def show_results():
    st.subheader("Results")

    try:
        results = load_results_data()
    except Exception as exc:
        st.error(f"Could not load Results: {exc}")
        return

    if results.empty:
        st.info("There are no recorded answers yet.")
        return

    batches = sorted(results["Batch ID"].dropna().unique(), key=str)
    selected_batch = st.selectbox("Select Batch ID", batches, key="results_batch")

    batch = results[results["Batch ID"] == selected_batch].copy()

    summary = (
        batch.groupby("Word", as_index=False)
        .agg(
            correct=("Correct", "sum"),
            total=("Correct", "size"),
        )
    )
    summary["correct_share"] = summary["correct"] / summary["total"]
    summary["Correct share"] = summary["correct_share"].map(
        lambda value: f"{value:.0%}"
    )
    summary["Answers"] = summary.apply(
        lambda row: f"{int(row['correct'])} / {int(row['total'])}",
        axis=1,
    )

    total_answers = len(batch)
    total_correct = int(batch["Correct"].sum())
    batch_share = total_correct / total_answers if total_answers else 0

    c1, c2 = st.columns(2)
    c1.metric("Correct", f"{total_correct} / {total_answers}")
    c2.metric("Correct share", f"{batch_share:.0%}")

    display = summary.rename(columns={"Word": "Word"})[
        ["Word", "Correct share", "Answers"]
    ].sort_values(["Correct share", "Word"], ascending=[True, True])

    st.dataframe(display, use_container_width=True, hide_index=True)


# Load spelling list once for both tabs.
try:
    df = load_spelling_data()
except Exception as exc:
    st.error(
        "Error connecting to Google Sheets. "
        f"Check credentials/permissions. ({exc})"
    )
    st.stop()

st.title("✏️ Spelling Practice")

practice_tab, results_tab = st.tabs(["Practice", "Results"])

with practice_tab:
    unique_batches = sorted(df["Batch"].astype(str).unique())

    if not unique_batches:
        st.warning("No spelling batches were found.")
        st.stop()

    selected_batch = st.selectbox("Select Batch ID", unique_batches)

    if (
        "current_batch" not in st.session_state
        or st.session_state.current_batch != selected_batch
    ):
        reset_practice(selected_batch, df)

    total = st.session_state.get("total_count", 0)
    correct = st.session_state.get("correct_count", 0)
    pct = correct / total if total else 0

    st.metric(
        "Session Score",
        f"{correct} / {total}",
        f"{pct:.0%}",
    )

    if st.session_state.current_word_data is None:
        next_word(df)

    current_item = st.session_state.current_word_data
    target_word = str(current_item["Word"]).strip()
    phrase = f"Your next word is {target_word}, as in {current_item['AsIn']}"

    render_audio_player(phrase)
    st.divider()

    if not st.session_state.submitted:
        st.subheader("Your Input")

        st.text_input(
            "Spelled word",
            value=st.session_state.user_input,
            disabled=True,
            label_visibility="collapsed",
        )
        st.write("**Tap letters to spell:**")

        scrambled = st.session_state.scrambled_letters
        num_cols = 5

        for row_start in range(0, len(scrambled), num_cols):
            chunk = scrambled[row_start : row_start + num_cols]
            cols = st.columns(num_cols, gap="small")

            for col_idx, col in enumerate(cols):
                if col_idx >= len(chunk):
                    continue

                orig_idx, char = chunk[col_idx]
                is_used = orig_idx in st.session_state.used_indices

                with col:
                    if st.button(
                        char.upper(),
                        key=f"letter_{orig_idx}_{row_start + col_idx}",
                        disabled=is_used,
                        use_container_width=True,
                    ):
                        st.session_state.user_input += char
                        st.session_state.used_indices.append(orig_idx)
                        st.rerun()

        erase_col, submit_col = st.columns(2)

        with erase_col:
            if st.button(
                "⌫ Erase",
                disabled=not st.session_state.user_input,
                use_container_width=True,
            ):
                st.session_state.user_input = st.session_state.user_input[:-1]
                if st.session_state.used_indices:
                    st.session_state.used_indices.pop()
                st.rerun()

        with submit_col:
            if st.button(
                "✅ Submit",
                disabled=not st.session_state.user_input,
                use_container_width=True,
            ):
                is_correct = (
                    st.session_state.user_input.strip().lower()
                    == target_word.lower()
                )

                st.session_state.submitted = True
                st.session_state.is_correct = is_correct
                st.session_state.play_result_animation = True
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

    else:
        play_animation = st.session_state.get("play_result_animation", False)
        if st.session_state.is_correct:
            if play_animation:
                st.balloons()
            st.success("🎉 **Awesome job! That is spelled correctly!**")
            st.markdown(
                f"<div style='font-size:24px;font-weight:700;'>Word: {target_word}</div>",
                unsafe_allow_html=True,
            )
        else:
            if play_animation:
                trigger_poop_rain()
            st.error("❌ **Not quite!**")
            st.markdown(
                f"You spelled: <code>{st.session_state.user_input}</code>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div style='font-size:24px;font-weight:700;color:#d32f2f;'>"
                f"Correct spelling: {target_word}</div>",
                unsafe_allow_html=True,
            )

        # Result animations are one-shot. This prevents them from replaying
        # when another tab or filter causes Streamlit to rerun the app.
        if play_animation:
            st.session_state.play_result_animation = False

        st.divider()

        if st.button(
            "➡️ Next Word",
            type="primary",
            use_container_width=True,
        ):
            next_word(df)
            st.rerun()

with results_tab:
    show_results()
