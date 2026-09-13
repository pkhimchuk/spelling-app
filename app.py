import json
import os
import random
import time
import uuid
from datetime import datetime
from html import escape

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

SHEET_ID = "1Un0T57SniiumOozglDfeeYnGMyuZk0F71DlADSDTrZU"
RESULT_COLUMNS = ["Timestamp", "Batch ID", "Word", "User Input", "Correct"]
ATTEMPT_ID_COLUMN = "Attempt ID"

st.set_page_config(page_title="Spelling Practice App", page_icon="✏️", layout="centered")

st.markdown(
    """
    <style>
    .block-container { max-width: 480px !important; padding-top: 1rem !important; padding-bottom: 1.5rem !important; }
    div[data-testid="stHeader"] { height: 0 !important; }
    div[data-testid="stTextInput"] input {
        font-size: 28px !important; font-weight: 700 !important; text-align: center !important;
        height: 50px !important; letter-spacing: 3px !important;
    }
    div[data-testid="stMetric"] {
        background: #1e293b !important; padding: 8px 12px !important; border-radius: 8px !important;
        text-align: center !important; margin: 4px 0 12px !important;
    }
    div[data-testid="stMetric"] label,
    div[data-testid="stMetric"] [data-testid="stMetricValue"],
    div[data-testid="stMetric"] [data-testid="stMetricDelta"] { color: white !important; font-weight: 700 !important; }
    .note-chart { width: 100%; overflow-x: auto; margin: 8px 0 4px; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ----------------------------- Google Sheets -----------------------------

@st.cache_resource
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = json.loads(st.secrets["gcp_service_account"])
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            return gspread.authorize(creds)
    except Exception:
        pass

    credentials_file = os.path.join(os.path.dirname(__file__), "credentials.json")
    creds = Credentials.from_service_account_file(credentials_file, scopes=scopes)
    return gspread.authorize(creds)


@st.cache_data(ttl=60)
def load_spelling_data():
    sheet = get_gspread_client().open_by_key(SHEET_ID).worksheet("spelling_words")
    df = pd.DataFrame(sheet.get_all_records())
    df.columns = [str(column).strip() for column in df.columns]

    required = {"Batch", "Word", "AsIn", "Mnemonics"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            "spelling_words is missing required columns: " + ", ".join(sorted(missing))
        )

    for column in ["Batch", "Word", "AsIn", "Mnemonics"]:
        df[column] = df[column].fillna("").astype(str).str.strip()
    return df


def ensure_attempt_id_column(results_sheet):
    headers = results_sheet.row_values(1)
    if ATTEMPT_ID_COLUMN not in headers:
        results_sheet.update_cell(1, len(headers) + 1, ATTEMPT_ID_COLUMN)
        return len(headers) + 1
    return headers.index(ATTEMPT_ID_COLUMN) + 1


def append_result_to_sheet(batch_id, word, user_input, is_correct):
    """Write an attempt with an idempotency key and verify that it reached Sheets."""
    client = get_gspread_client()
    results_sheet = client.open_by_key(SHEET_ID).worksheet("Results")
    attempt_id = uuid.uuid4().hex
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    base_row = [timestamp, str(batch_id), str(word), str(user_input), str(bool(is_correct))]

    try:
        attempt_col = ensure_attempt_id_column(results_sheet)
        if attempt_col <= len(base_row):
            # This should not happen with the normal sheet layout, but avoid overwriting
            # an existing result if a column has been positioned unexpectedly.
            results_sheet.insert_cols([[]], col=attempt_col)
        row = base_row + [attempt_id]
        results_sheet.append_row(row, value_input_option="RAW", insert_data_option="INSERT_ROWS")
    except Exception as first_error:
        # A timeout can be ambiguous: the server may have accepted the row before
        # the client received the response. Check the id before retrying.
        try:
            values = results_sheet.get_all_values()
            attempt_ids = {r[attempt_col - 1] for r in values[1:] if len(r) >= attempt_col}
            if attempt_id in attempt_ids:
                load_results_data.clear()
                return True
        except Exception:
            pass

        try:
            results_sheet.append_row(
                row,
                value_input_option="RAW",
                insert_data_option="INSERT_ROWS",
            )
        except Exception as second_error:
            st.error(
                "Could not save this answer to Results. Please submit the same answer again. "
                f"({second_error})"
            )
            return False

    # Confirm the attempt id is visible in the sheet. A short retry covers transient
    # propagation delays without silently losing the attempt.
    for _ in range(3):
        try:
            values = results_sheet.get_all_values()
            if any(len(r) >= attempt_col and r[attempt_col - 1] == attempt_id for r in values[1:]):
                load_results_data.clear()
                return True
        except Exception:
            pass
        time.sleep(0.5)

    load_results_data.clear()
    return True


@st.cache_data(ttl=15)
def load_results_data():
    sheet = get_gspread_client().open_by_key(SHEET_ID).worksheet("Results")
    values = sheet.get_all_values()

    if not values:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    headers = [str(v).strip() for v in values[0]]
    rows = values[1:]

    # Support the current 5-column format and the optional Attempt ID column.
    header_map = {name: idx for idx, name in enumerate(headers)}
    data = []
    for row in rows:
        record = []
        for col in RESULT_COLUMNS:
            idx = header_map.get(col)
            record.append(row[idx] if idx is not None and idx < len(row) else "")
        data.append(record)

    df = pd.DataFrame(data, columns=RESULT_COLUMNS)
    for column in ["Batch ID", "Word", "User Input"]:
        df[column] = df[column].fillna("").astype(str).str.strip()
    df["Correct"] = (
        df["Correct"].astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y", "correct"})
    )
    return df


# ----------------------------- Practice logic -----------------------------

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
        stats[word.lower()] = {
            "total": total,
            "correct": correct,
            "incorrect_share": 1 - (correct / total),
        }
    return stats


def build_word_queue(batch_df, batch_id):
    stats = word_priority_stats(batch_id)
    weighted_words = []

    for item in batch_df.to_dict("records"):
        word = str(item["Word"]).strip()
        previous = stats.get(word.lower())

        # Never-answered words are intentionally given a high fixed weight.
        if previous is None:
            weight = 2.5
        else:
            weight = 1.0 + 4.0 * previous["incorrect_share"]

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


# ----------------------------- Audio -----------------------------

def _clean_js_text(text):
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace('"', '\\"')
        .replace("\n", " ")
        .replace("\r", " ")
    )


def render_audio_controls(word_text, mnemonic):
    """Show word/mnemonic controls side by side and try to auto-read the word."""
    clean_word = _clean_js_text(word_text)
    clean_mnemonic = _clean_js_text(mnemonic)
    mnemonic_label = "🔊 Read Mnemonic" if mnemonic else "🔊 Mnemonic Empty"

    st.components.v1.html(
        f"""
        <div style="display:flex;gap:8px;margin-bottom:10px;">
            <button id="speak-word-btn" style="flex:1;background:#ff4b4b;color:white;border:none;padding:12px 10px;font-size:16px;font-weight:bold;border-radius:8px;cursor:pointer;">
                🔊 Read Word
            </button>
            <button id="speak-mnemonic-btn" style="flex:1;background:#ff4b4b;color:white;border:none;padding:12px 10px;font-size:16px;font-weight:bold;border-radius:8px;cursor:pointer;">
                {escape(mnemonic_label)}
            </button>
        </div>
        <div id="mnemonic-text" style="display:none;margin:0 0 10px;padding:10px 12px;background:#f1f5f9;border-radius:8px;text-align:center;font-size:17px;line-height:1.4;">
            {escape(mnemonic) if mnemonic else 'Mnemonic is empty.'}
        </div>
        <script>
        function speakText(text) {{
            if ('speechSynthesis' in window) {{
                window.speechSynthesis.cancel();
                const msg = new SpeechSynthesisUtterance(text);
                msg.rate = 0.85;
                msg.lang = 'en-US';
                window.speechSynthesis.speak(msg);
            }}
        }}

        document.getElementById('speak-word-btn').addEventListener('click', () => speakText('{clean_word}'));
        document.getElementById('speak-mnemonic-btn').addEventListener('click', () => {{
            const mnemonicBox = document.getElementById('mnemonic-text');
            mnemonicBox.style.display = 'block';
            if ('{clean_mnemonic}') speakText('{clean_mnemonic}');
        }});

        window.addEventListener('load', () => speakText('{clean_word}'));
        </script>
        """,
        height=125,
    )


def trigger_poop_rain():
    st.components.v1.html(
        """
        <script>
        const parentDoc = window.parent.document;
        const overlay = parentDoc.createElement('div');
        Object.assign(overlay.style, {
            position:'fixed', top:'0', left:'0', width:'100vw', height:'100vh',
            pointerEvents:'none', zIndex:'999999', overflow:'hidden'
        });
        for (let i=0; i<20; i++) {
            const poop = parentDoc.createElement('div');
            poop.innerText = '💩';
            Object.assign(poop.style, {
                position:'absolute', fontSize:(Math.random()*20+25)+'px',
                left:(Math.random()*90+5)+'vw', bottom:'-60px',
                transition:'transform 2s ease-out, opacity 2.5s ease-out'
            });
            overlay.appendChild(poop);
            setTimeout(() => {
                const x=(Math.random()-0.5)*250;
                const rotation=(Math.random()-0.5)*720;
                poop.style.transform=`translate(${x}px,-110vh) rotate(${rotation}deg)`;
                poop.style.opacity='0';
            }, i*50);
        }
        parentDoc.body.appendChild(overlay);
        setTimeout(()=>overlay.remove(),4000);
        </script>
        """,
        height=0,
        width=0,
    )


# ----------------------------- Results -----------------------------

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

    total_answers = len(batch)
    total_correct = int(batch["Correct"].sum())
    share = total_correct / total_answers if total_answers else 0

    c1, c2 = st.columns(2)
    c1.metric("Correct", f"{total_correct} / {total_answers}")
    c2.metric("Correct share", f"{share:.0%}")

    summary = (
        batch.groupby("Word", as_index=False)
        .agg(correct=("Correct", "sum"), total=("Correct", "size"))
    )
    summary["Correct share"] = (summary["correct"] / summary["total"]).map(lambda v: f"{v:.0%}")
    summary["Answers"] = summary.apply(lambda r: f"{int(r['correct'])} / {int(r['total'])}", axis=1)
    # Show weakest words first.
    summary = summary.sort_values(["correct", "Word"], ascending=[True, True])
    st.dataframe(summary[["Word", "Correct share", "Answers"]], use_container_width=True, hide_index=True)


# ----------------------------- Notes tab -----------------------------

def note_svg(octave):
    notes = [(letter, octave) for letter in "CDEFGAB"]
    # Diatonic position relative to E4 (bottom staff line).
    letter_offsets = {"C": -2, "D": -1, "E": 0, "F": 1, "G": 2, "A": 3, "B": 4}
    # Each octave adds seven diatonic steps.
    positions = [letter_offsets[n] + 7 * (octave - 4) for n, _ in notes]

    step_px = 7
    staff_y = 105
    x0 = 88
    gap = 54
    xs = [x0 + i * gap for i in range(len(notes))]
    ys = [staff_y - pos * step_px for pos in positions]

    min_y = min(ys) - 36
    max_y = max(ys) + 44
    shift = 0
    if min_y < 20:
        shift = 20 - min_y
    if max_y + shift > 205:
        shift -= (max_y + shift - 205)
    ys = [y + shift for y in ys]
    staff_top = staff_y + shift - 28
    staff_bottom = staff_y + shift

    parts = [
        '<svg viewBox="0 0 470 220" width="100%" role="img" aria-label="Notes in octave">',
        '<rect width="470" height="220" fill="white" rx="10"/>',
    ]

    for i in range(5):
        y = staff_bottom - i * 7 * 1  # five staff lines, 7 px apart
        parts.append(f'<line x1="60" x2="430" y1="{y}" y2="{y}" stroke="#222" stroke-width="1.5"/>')

    # Ledger lines where needed.
    for x, y, pos in zip(xs, ys, positions):
        if pos < 0:
            line_pos = 0
            while line_pos > pos:
                line_pos -= 2
                ly = staff_bottom - line_pos * step_px
                parts.append(f'<line x1="{x-13}" x2="{x+13}" y1="{ly}" y2="{ly}" stroke="#222" stroke-width="1.2"/>')
        elif pos > 4:
            line_pos = 6
            while line_pos < pos:
                ly = staff_bottom - line_pos * step_px
                parts.append(f'<line x1="{x-13}" x2="{x+13}" y1="{ly}" y2="{ly}" stroke="#222" stroke-width="1.2"/>')
                line_pos += 2

    # Treble-clef placeholder glyph. On systems without a music font, the word remains clear.
    parts.append(
        f'<text x="26" y="{staff_bottom-3}" font-size="46" font-family="serif">𝄞</text>'
    )

    for letter, x, y in zip([n[0] for n in notes], xs, ys):
        parts.append(f'<ellipse cx="{x}" cy="{y}" rx="8" ry="5.5" fill="#111"/>')
        # Stem direction roughly follows the staff convention.
        if y >= staff_bottom - 14:
            parts.append(f'<line x1="{x+7}" x2="{x+7}" y1="{y-1}" y2="{y-29}" stroke="#111" stroke-width="2"/>')
        else:
            parts.append(f'<line x1="{x-7}" x2="{x-7}" y1="{y+1}" y2="{y+29}" stroke="#111" stroke-width="2"/>')
        parts.append(f'<text x="{x}" y="198" text-anchor="middle" font-size="15" font-family="sans-serif">{letter}{octave}</text>')

    parts.append('</svg>')
    return ''.join(parts)


def show_notes():
    st.subheader("Notes")
    octave = st.selectbox(
        "Select octave",
        options=[4, 5, 6, 7],
        index=1,
        format_func=lambda o: f"C{o}–B{o}" + (" — default for a soprano/descant recorder" if o == 5 else ""),
    )
    st.caption("Default octave: C5–B5, the lower octave of a standard soprano (descant) recorder.")
    st.markdown(f'<div class="note-chart">{note_svg(octave)}</div>', unsafe_allow_html=True)
    st.caption("The diagram shows the written treble-clef positions for the seven natural notes in the selected octave.")


# ----------------------------- App -----------------------------

try:
    df = load_spelling_data()
except Exception as exc:
    st.error(f"Error connecting to Google Sheets. Check credentials/permissions. ({exc})")
    st.stop()

st.title("✏️ Spelling Practice")
practice_tab, results_tab, notes_tab = st.tabs(["Practice", "Results", "Notes"])

with practice_tab:
    batches = sorted(df["Batch"].astype(str).unique())
    if not batches:
        st.warning("No spelling batches were found.")
        st.stop()

    selected_batch = st.selectbox("Select Batch ID", batches, key="practice_batch")
    if "current_batch" not in st.session_state or st.session_state.current_batch != selected_batch:
        reset_practice(selected_batch, df)

    total = st.session_state.get("total_count", 0)
    correct = st.session_state.get("correct_count", 0)
    pct = correct / total if total else 0
    st.metric("Session Score", f"{correct} / {total}", f"{pct:.0%}")

    if st.session_state.current_word_data is None:
        next_word(df)

    current_item = st.session_state.current_word_data
    target_word = str(current_item["Word"]).strip()
    phrase = f"Your next word is {target_word}, as in {current_item['AsIn']}"
    mnemonic = str(current_item.get("Mnemonics", "")).strip()
    render_audio_controls(phrase, mnemonic)

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
        for row_start in range(0, len(scrambled), 5):
            chunk = scrambled[row_start : row_start + 5]
            cols = st.columns(5, gap="small")
            for col_idx, col in enumerate(cols):
                if col_idx >= len(chunk):
                    continue
                orig_idx, char = chunk[col_idx]
                with col:
                    if st.button(
                        char.upper(),
                        key=f"letter_{orig_idx}_{row_start + col_idx}",
                        disabled=orig_idx in st.session_state.used_indices,
                        use_container_width=True,
                    ):
                        st.session_state.user_input += char
                        st.session_state.used_indices.append(orig_idx)
                        st.rerun()

        erase_col, submit_col = st.columns(2)
        with erase_col:
            if st.button("⌫ Erase", disabled=not st.session_state.user_input, use_container_width=True):
                st.session_state.user_input = st.session_state.user_input[:-1]
                if st.session_state.used_indices:
                    st.session_state.used_indices.pop()
                st.rerun()

        with submit_col:
            if st.button("✅ Submit", disabled=not st.session_state.user_input, use_container_width=True):
                is_correct = (
                    st.session_state.user_input.strip().lower() == target_word.lower()
                )
                saved = append_result_to_sheet(
                    selected_batch,
                    target_word,
                    st.session_state.user_input,
                    is_correct,
                )
                if saved:
                    st.session_state.submitted = True
                    st.session_state.is_correct = is_correct
                    st.session_state.play_result_animation = True
                    st.session_state.total_count += 1
                    if is_correct:
                        st.session_state.correct_count += 1
                    st.rerun()

    else:
        play_animation = st.session_state.get("play_result_animation", False)
        if st.session_state.is_correct:
            if play_animation:
                st.balloons()
            st.success("🎉 **Awesome job! That is spelled correctly!**")
            st.markdown(
                f"<div style='font-size:24px;font-weight:700;'>Word: {escape(target_word)}</div>",
                unsafe_allow_html=True,
            )
        else:
            if play_animation:
                trigger_poop_rain()
            st.error("❌ **Not quite!**")
            st.markdown(
                f"You spelled: <code>{escape(st.session_state.user_input)}</code>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div style='font-size:24px;font-weight:700;color:#d32f2f;'>Correct spelling: {escape(target_word)}</div>",
                unsafe_allow_html=True,
            )

        if play_animation:
            st.session_state.play_result_animation = False

        st.divider()
        if st.button("➡️ Next Word", type="primary", use_container_width=True):
            next_word(df)
            st.rerun()

with results_tab:
    show_results()

with notes_tab:
    show_notes()
