"""FileWhisperer — Streamlit UI.

Run with:
    streamlit run app.py

This is the only command you need to type. Once it opens in your browser,
everything else — adding documents, asking questions — happens by clicking
and typing in the page, no terminal required. The API key and model are
read silently from .env; there's deliberately no key/model UI for the
person using the app to see or fiddle with.
"""

from __future__ import annotations

import datetime
import html
import os
import tempfile
import time
from pathlib import Path

import streamlit as st

from filewhisperer import FileWhisperer
from filewhisperer import accounts
from filewhisperer.loaders import EmptyDocument, UnsupportedFileType

st.set_page_config(
    page_title="FileWhisperer",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",  # don't start collapsed - keeps the document panel visible
)

# ---------------------------------------------------------------------------
# Visual identity
#
# Streamlit's default look is instantly recognizable as "a Streamlit app."
# Everything below overrides that with a specific palette and type system —
# a document/annotation feel (paper backdrop, ink-teal accent, a serif
# wordmark) rather than generic SaaS-blue-and-rounded-cards, plus proper
# left/right-aligned chat bubbles like a normal chat product. This only
# touches presentation; none of the app's logic changes.
# ---------------------------------------------------------------------------

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,500;0,9..144,600;0,9..144,700;1,9..144,500&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

:root {
    --bg: #14181A;
    --surface: #1D2325;
    --sidebar-bg: #0F1213;
    --border: #2B3335;
    --ink: #F5F7F6;
    --ink-muted: #9AA5A2;
    --accent: #0E7C66;
    --accent-hover: #14997D;
    --accent-soft: #123832;
}

html, body, .stApp {
    background: var(--bg);
    color: var(--ink);
    font-family: 'IBM Plex Sans', -apple-system, sans-serif;
}

/* Streamlit's own footer branding - safe to hide, doesn't affect navigation. */
footer { visibility: hidden; }

h1, h2, h3, h4 {
    font-family: 'Fraunces', Georgia, serif;
    font-weight: 600;
    color: var(--ink);
    letter-spacing: -0.01em;
}

p, span, label, div { color: var(--ink); }

/* --- Sidebar ------------------------------------------------------------ */
[data-testid="stSidebar"] {
    background: var(--sidebar-bg);
    border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] h3 {
    font-size: 1.05rem;
    margin-top: 0.2rem;
    margin-bottom: 0.6rem;
}

/* Sidebar sections (Profile / Documents / Chats) as distinct panels rather
   than one long list divided by plain <hr> lines - each panel is a
   slightly-elevated card against the tinted sidebar background, which
   reads as separate zones at a glance. Uses st.container(key=...), the
   same documented mechanism used elsewhere in this file. */
div[class*="st-key-panel_"] {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 0.85rem 0.9rem 0.6rem 0.9rem;
    margin-bottom: 0.9rem;
}

/* --- Buttons -------------------------------------------------------------*/
.stButton button, [data-testid="stChatInput"] button {
    border-radius: 7px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--ink);
    font-weight: 500;
    transition: border-color 0.15s ease, color 0.15s ease;
}
.stButton button:hover {
    border-color: var(--accent);
    color: var(--accent);
}
[data-testid="stChatInput"] button {
    background: var(--accent);
    border-color: var(--accent);
    color: white;
}
[data-testid="stChatInput"] button:hover {
    background: var(--accent-hover);
    border-color: var(--accent-hover);
}
/* Form submit buttons (Log in / Create account) read as primary actions -
   filled accent, same treatment as the chat send button. */
[data-testid="stFormSubmitButton"] button {
    background: var(--accent);
    border-color: var(--accent);
    color: white;
    font-weight: 600;
}
[data-testid="stFormSubmitButton"] button:hover {
    background: var(--accent-hover);
    border-color: var(--accent-hover);
    color: white;
}

/* --- Auth card (login/signup screen) --------------------------------------
   Uses st.container(key="auth_card") - see the chat-row comment above for
   why this mechanism (not a guessed internal class) is used for custom
   containers. Centered via st.columns in the Python, not CSS margins. */
div[class*="st-key-auth_card"] {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 2rem 2rem 1rem 2rem;
    margin-top: 3rem;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.45), 0 1px 3px rgba(0, 0, 0, 0.3);
}
div[class*="st-key-auth_card"] [data-testid="stTabs"] button[role="tab"] {
    font-weight: 500;
    color: var(--ink-muted);
}
div[class*="st-key-auth_card"] [data-testid="stTabs"] button[aria-selected="true"] {
    color: var(--accent);
}
/* Best-effort: colors the active-tab underline too. Not load-bearing - if
   this selector doesn't match, the tab text color change above still
   makes the active tab clear on its own. */
div[class*="st-key-auth_card"] [data-testid="stTabs"] [data-baseweb="tab-highlight"] {
    background-color: var(--accent) !important;
}

/* --- Inputs ---------------------------------------------------------------*/
[data-testid="stTextInput"] input,
[data-testid="stChatInput"] textarea {
    border-radius: 7px !important;
    border: 1px solid var(--border) !important;
    background: var(--surface) !important;
    font-family: 'IBM Plex Sans', sans-serif;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stChatInput"] textarea:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 1px var(--accent) !important;
}

/* --- File uploader ----------------------------------------------------- */
[data-testid="stFileUploaderDropzone"] {
    background: var(--surface);
    border: 1.5px dashed var(--border);
    border-radius: 8px;
}
[data-testid="stFileUploaderDropzone"]:hover {
    border-color: var(--accent);
}

/* --- Alerts (success/info/warning/error) --------------------------------*/
[data-testid="stAlert"] {
    border-radius: 8px;
    font-family: 'IBM Plex Sans', sans-serif;
}

/* --- Chat bubbles: fully custom markup (see render_bubble()) -------------
   Earlier versions tried to style Streamlit's built-in chat_message
   component via its internal CSS classes - that broke three times in a
   row (avatar icons, then bubble alignment, then bubble color) because
   those internals aren't a stable target across Streamlit versions. This
   builds the bubble markup ourselves instead, so nothing here depends on
   guessing Streamlit's implementation details. */
.dm-row {
    display: flex;
    margin: 0.5rem 0;
}
.dm-row.user { justify-content: flex-end; }
.dm-row.assistant { justify-content: flex-start; }

.dm-bubble {
    max-width: 78%;
    border-radius: 14px;
    padding: 0.55rem 0.85rem;
    border: 1px solid var(--border);
}
.dm-bubble.user {
    background: var(--accent);
    border-color: var(--accent);
    color: white;
}
.dm-bubble.user p, .dm-bubble.user li, .dm-bubble.user span {
    color: white;
}
.dm-bubble.assistant {
    background: var(--surface);
    color: var(--ink);
}
.dm-bubble p:first-child { margin-top: 0; }
.dm-bubble p:last-child { margin-bottom: 0; }

/* --- Rich content inside bubbles: tables, code blocks, lists ------------- */
.dm-bubble table {
    border-collapse: collapse;
    width: 100%;
    font-size: 0.92rem;
    margin: 0.4rem 0;
}
.dm-bubble th {
    background: var(--accent-soft);
    color: var(--ink);
    text-align: left;
    padding: 0.4rem 0.6rem;
    border: 1px solid var(--border);
    font-weight: 600;
}
.dm-bubble td {
    padding: 0.4rem 0.6rem;
    border: 1px solid var(--border);
}
.dm-bubble code {
    background: var(--sidebar-bg);
    color: var(--accent-hover);
    border-radius: 4px;
    padding: 0.1rem 0.35rem;
    font-size: 0.88em;
}
.dm-bubble.user code {
    background: rgba(255,255,255,0.18);
    color: white;
}
.dm-bubble pre {
    background: #0C0F0E;
    border-radius: 8px;
    padding: 0.8rem 1rem;
    overflow-x: auto;
}
.dm-bubble pre code {
    background: transparent;
    color: #E7F2EE;
    padding: 0;
}
.dm-bubble ul, .dm-bubble ol {
    margin: 0.3rem 0;
    padding-left: 1.4rem;
}

/* --- Sidebar list rows (chats, documents): hover reveals actions --------
   Uses st.container(key=...), which Streamlit documents as generating a
   stable "st-key-<name>" class - unlike the chat-bubble internals earlier
   in this file, this is an officially supported styling hook, not a
   guess at implementation details. */
div[class*="st-key-chatrow_"], div[class*="st-key-docrow_"] {
    border-radius: 8px;
    padding: 2px 4px;
    transition: background 0.15s ease;
}
div[class*="st-key-chatrow_"]:hover, div[class*="st-key-docrow_"]:hover {
    background: var(--accent-soft);
}
div[class*="st-key-chatedit_"], div[class*="st-key-chatdel_"], div[class*="st-key-docactions_"] {
    opacity: 0;
    transition: opacity 0.15s ease;
}
div[class*="st-key-chatrow_"]:hover div[class*="st-key-chatedit_"],
div[class*="st-key-chatrow_"]:hover div[class*="st-key-chatdel_"],
div[class*="st-key-docrow_"]:hover div[class*="st-key-docactions_"] {
    opacity: 1;
}
/* The row's own open/select button should look like a plain list item,
   not a bordered button, so only the row background (above) shows on
   hover - the button itself shouldn't visibly compete with it. Targets
   its own explicit container key rather than a fragile first-child
   guess about Streamlit's internal DOM nesting. */
div[class*="st-key-chatopen_"] button {
    border-color: transparent;
    background: transparent;
    text-align: left;
    justify-content: flex-start;
    font-weight: 400;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
div[class*="st-key-chatopen_"] button:hover {
    border-color: transparent;
    background: transparent;
}
/* Rename/delete icon buttons: small, subtle until hovered. min-width is
   explicitly overridden - Streamlit's default button min-width is wider
   than a single emoji needs, which was the main cause of these getting
   squeezed against neighboring content in a narrow column. */
div[class*="st-key-chatedit_"] .stButton button,
div[class*="st-key-chatdel_"] .stButton button,
div[class*="st-key-docactions_"] .stButton button {
    border-color: transparent;
    background: transparent;
    padding: 0.15rem 0.25rem;
    min-width: 2rem;
    width: 100%;
}
div[class*="st-key-chatedit_"] .stButton button:hover,
div[class*="st-key-chatdel_"] .stButton button:hover,
div[class*="st-key-docactions_"] .stButton button:hover {
    background: var(--surface);
    border-color: var(--border);
}

/* Log out button: enough padding reduction to comfortably fit "Log out"
   in a narrower column without wrapping or clipping. */
div[class*="st-key-panel_profile"] .stButton button {
    padding: 0.35rem 0.5rem;
    font-size: 0.85rem;
    white-space: nowrap;
}

/* --- Custom header block (see render_header()) ---------------------------*/
.dm-header {
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    margin-bottom: 0.1rem;
}
.dm-header .mark {
    font-family: 'Fraunces', Georgia, serif;
    font-style: italic;
    font-weight: 600;
    font-size: 2.1rem;
    color: var(--accent);
}
.dm-header .word {
    font-family: 'Fraunces', Georgia, serif;
    font-weight: 600;
    font-size: 2.1rem;
    color: var(--ink);
}
.dm-tagline {
    color: var(--ink-muted);
    font-size: 0.95rem;
    margin-top: -0.3rem;
    margin-bottom: 0.6rem;
}
.dm-rule {
    height: 2px;
    background: linear-gradient(90deg, var(--accent) 0%, var(--border) 55%);
    border: none;
    margin: 0 0 1.4rem 0;
}

/* --- Document list cards in sidebar ---------------------------------------*/
.dm-doc-card {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    padding: 0.5rem 0.6rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    margin-bottom: 0.4rem;
}
.dm-doc-card .glyph { font-size: 1.05rem; color: var(--accent); }
.dm-doc-card .meta { line-height: 1.25; overflow: hidden; }
.dm-doc-card .fname {
    font-weight: 500;
    font-size: 0.88rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.dm-doc-card .fsize { font-size: 0.76rem; color: var(--ink-muted); }
.dm-doc-card:hover { border-color: var(--accent); transform: translateY(-1px); }

/* --- Auth / product intro ------------------------------------------------ */
.auth-title {
    text-align: center;
    font-family: 'Fraunces', Georgia, serif;
    font-size: 2.35rem;
    font-weight: 600;
    line-height: 1.05;
    margin-bottom: 0.55rem;
}
.auth-subtitle {
    text-align: center;
    color: var(--ink-muted);
    font-size: 1rem;
    line-height: 1.5;
    margin: 0 auto 0.35rem auto;
    max-width: 30rem;
}
.auth-private {
    text-align: center;
    color: var(--ink-muted);
    font-size: 0.78rem;
    margin-bottom: 1.25rem;
}
.auth-pills {
    display: flex;
    justify-content: center;
    flex-wrap: wrap;
    gap: 0.45rem;
    margin: 0 0 1.2rem 0;
}
.auth-pill {
    border: 1px solid var(--border);
    background: var(--sidebar-bg);
    border-radius: 999px;
    padding: 0.3rem 0.6rem;
    color: var(--ink-muted);
    font-size: 0.75rem;
}
.auth-footnote {
    text-align: center;
    color: var(--ink-muted);
    font-size: 0.78rem;
    margin-top: 0.8rem;
}

/* --- Source citations ---------------------------------------------------- */
.dm-sources {
    max-width: 78%;
    margin: -0.15rem 0 0.7rem 0;
    color: var(--ink-muted);
    font-size: 0.75rem;
}
.dm-source {
    display: inline-block;
    margin: 0.18rem 0.35rem 0.18rem 0;
    padding: 0.25rem 0.45rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--sidebar-bg);
}

/* --- Main upload panel --------------------------------------------------- */
.dm-upload-label {
    color: var(--ink-muted);
    font-size: 0.78rem;
    margin-bottom: 0.25rem;
}

/* --- Profile popover ----------------------------------------------------- */
div[class*="st-key-panel_profile"] .stPopover button {
    width: 100%;
}

/* Keep sidebar compact on smaller screens. */
@media (max-width: 900px) {
    .dm-bubble { max-width: 90%; }
    .dm-sources { max-width: 90%; }
}
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Accounts: sign up / log in.
#
# Real per-user accounts, backed by a local SQLite file (filewhisperer/accounts.py)
# - passwords are hashed (PBKDF2, stdlib only, no third-party auth
# dependency), never stored in plaintext. Chat history auto-saves per
# account as you go, so logging back in later shows your own past chats,
# not anyone else's.
#
# Optional: set FILEWHISPERER_SIGNUP_CODE in .env to require an invite code to
# create a NEW account (existing accounts can still log in without it).
# This is what protects your API key from strangers on a public URL -
# share the signup code only with people you want to have access.
# ---------------------------------------------------------------------------

accounts.init_db()
accounts.cleanup_expired_tokens()

SIGNUP_CODE = os.environ.get("FILEWHISPERER_SIGNUP_CODE", os.environ.get("DOCUMIND_SIGNUP_CODE", "")).strip()
REMEMBER_COOKIE_NAME = "filewhisperer_remember"
REMEMBER_ME_SECONDS = 30 * 24 * 60 * 60
COOKIE_SECURE = os.environ.get("FILEWHISPERER_COOKIE_SECURE", os.environ.get("DOCUMIND_COOKIE_SECURE", "false")).strip().lower() in {"1", "true", "yes", "on"}


def set_remember_cookie(token: str) -> None:
    """Persist the token on the top-level app origin using the browser cookie API."""
    import streamlit.components.v1 as components
    secure_flag = "; Secure" if COOKIE_SECURE else ""
    cookie = f"{REMEMBER_COOKIE_NAME}={token}; Max-Age={REMEMBER_ME_SECONDS}; Path=/; SameSite=Lax{secure_flag}"
    components.html(
        f"<script>window.parent.document.cookie = {cookie!r};</script>",
        height=0, width=0,
    )


def delete_remember_cookie() -> None:
    """Remove the remember-me token from the top-level app origin."""
    import streamlit.components.v1 as components
    components.html(
        f"<script>window.parent.document.cookie = {REMEMBER_COOKIE_NAME}=; Max-Age=0; Path=/; SameSite=Lax;</script>",
        height=0, width=0,
    )

if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "username" not in st.session_state:
    st.session_state.username = None

# Restore the login from the persistent cookie BEFORE rendering the login
# page. On Streamlit >= 1.42, this is synchronous because the cookie arrived
# with the initial HTTP request.
if st.session_state.user_id is None:
    try:
        remember_token = None
        if hasattr(st, "context"):
            remember_token = st.context.cookies.get(REMEMBER_COOKIE_NAME)

        if remember_token:
            session = accounts.authenticate_remember_token(remember_token)
            if session:
                st.session_state.user_id, st.session_state.username = session
    except Exception:
        # A bad/missing cookie must never block the normal login screen.
        pass

if st.session_state.user_id is None:
    left_pad, card_col, right_pad = st.columns([1, 1.3, 1])
    with card_col:
        with st.container(key="auth_card"):
            st.markdown(
                '<div class="auth-title"><span class="mark">File</span> Whisperer</div>'
                '<div class="auth-subtitle">Your documents. One conversation.</div>'
                '<div class="auth-private">Upload files, ask questions, and get answers grounded in your documents.</div>'
                '<div class="auth-pills">'
                '<span class="auth-pill">PDF</span><span class="auth-pill">DOCX</span>'
                '<span class="auth-pill">CSV</span><span class="auth-pill">XLSX</span>'
                '<span class="auth-pill">TXT</span>'
                '</div>',
                unsafe_allow_html=True,
            )

            login_tab, signup_tab = st.tabs(["Log in", "Sign up"])

            with login_tab:
                with st.form("login_form"):
                    li_username = st.text_input("Username", placeholder="Enter your username", key="li_username")
                    li_password = st.text_input("Password", type="password", placeholder="Enter your password", key="li_password")
                    remember_me = st.checkbox(
                        "Remember me for 30 days",
                        value=True,
                        key="remember_me",
                    )
                    if st.form_submit_button("Log in", use_container_width=True):
                        try:
                            user_id = accounts.authenticate(li_username, li_password)
                            st.session_state.user_id = user_id
                            st.session_state.username = li_username.strip()

                            if remember_me:
                                token = accounts.create_remember_token(user_id)
                                set_remember_cookie(token)

                            st.rerun()
                        except accounts.InvalidCredentials as e:
                            st.error(str(e))

            with signup_tab:
                with st.form("signup_form"):
                    su_username = st.text_input("Choose a username", placeholder="Pick a username", key="su_username")
                    su_password = st.text_input("Choose a password", type="password", placeholder="At least 8 characters", key="su_password")
                    su_password2 = st.text_input("Confirm password", type="password", placeholder="Re-enter your password", key="su_password2")
                    su_code = st.text_input("Invite code", type="password", key="su_code") if SIGNUP_CODE else None
                    if st.form_submit_button("Create account", use_container_width=True):
                        if SIGNUP_CODE and su_code != SIGNUP_CODE:
                            st.error("Incorrect invite code.")
                        elif su_password != su_password2:
                            st.error("Passwords don't match.")
                        elif len(su_password) < 8:
                            st.error("Password should be at least 8 characters.")
                        else:
                            try:
                                user_id = accounts.create_user(su_username, su_password)
                                st.session_state.user_id = user_id
                                st.session_state.username = su_username.strip()

                                token = accounts.create_remember_token(user_id)
                                set_remember_cookie(token)
                                st.rerun()
                            except (accounts.UsernameTaken, ValueError) as e:
                                st.error(str(e))

    st.stop()  # halt here - nothing below this line renders until logged in


def render_header() -> None:
    st.markdown(
        """
        <div class="dm-header"><span class="mark">File</span><span class="word">Whisperer</span></div>
        <div class="dm-tagline">Turn your files into conversations — with answers grounded in your documents.</div>
        <hr class="dm-rule" />
        """,
        unsafe_allow_html=True,
    )


def render_bubble(role: str, content: str, sources: list | None = None) -> None:
    """Render a chat bubble plus optional document source chips."""
    css_role = "user" if role == "user" else "assistant"
    st.markdown(
        f'<div class="dm-row {css_role}"><div class="dm-bubble {css_role}">\n\n{content}\n\n</div></div>',
        unsafe_allow_html=True,
    )
    if sources and css_role == "assistant":
        def field(source, name, default=None):
            # A source is a Chunk object on the very first render (straight
            # from dm.ask_with_sources()) but a plain dict on every render
            # after that - it gets saved to chat_history/the database as a
            # dict, then reloaded as one on every subsequent rerun. Reading
            # both the same way here is what keeps the citation correct
            # beyond that first render, instead of silently falling back to
            # a generic placeholder the moment the page redraws.
            if isinstance(source, dict):
                return source.get(name, default)
            return getattr(source, name, default)

        unique = []
        seen = set()
        for source in sources:
            key = (field(source, "doc_name", ""), field(source, "page"))
            if key not in seen:
                seen.add(key)
                unique.append(source)
        chips = []
        for source in unique:
            doc_name = html.escape(field(source, "doc_name", "Document"))
            page = field(source, "page")
            page_text = f" · {html.escape(str(page))}" if page else ""
            chips.append(f'<span class="dm-source">📄 {doc_name}{page_text}</span>')
        st.markdown(f'<div class="dm-sources"><strong>Sources</strong> &nbsp; ' + "".join(chips) + '</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session state setup — Streamlit reruns this whole script on every
# interaction, so anything that needs to persist (the assistant, chat
# history, which files we've already processed) has to live in
# st.session_state rather than as a normal variable.
# ---------------------------------------------------------------------------

if "dm" not in st.session_state:
    st.session_state.dm = FileWhisperer()  # picks up OPENROUTER_API_KEY / OPENROUTER_MODEL from .env

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []  # [{"role": "user"|"assistant", "content": str}]

if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None  # None until the first message auto-saves it

if "renaming_chat_id" not in st.session_state:
    st.session_state.renaming_chat_id = None

if "processed_files" not in st.session_state:
    st.session_state.processed_files = set()  # (name, size) pairs already loaded

dm: FileWhisperer = st.session_state.dm


def add_uploaded_file(uploaded_file) -> None:
    """Save a Streamlit UploadedFile to a temp path and load it through the
    existing filewhisperer loaders, so the loading/chunking logic stays exactly
    the same as the CLI version."""
    key = (uploaded_file.name, uploaded_file.size)
    if key in st.session_state.processed_files:
        return

    suffix = Path(uploaded_file.name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name

    try:
        dm.add_document(tmp_path, display_name=uploaded_file.name)
        st.session_state.processed_files.add(key)
    except UnsupportedFileType as e:
        st.sidebar.warning(str(e))
    except EmptyDocument as e:
        st.sidebar.warning(str(e))
    except Exception as e:
        st.sidebar.error(f"Couldn't read \"{uploaded_file.name}\": {e}")
    finally:
        for _ in range(3):
            try:
                Path(tmp_path).unlink(missing_ok=True)
                break
            except PermissionError:
                time.sleep(0.2)  # something briefly still had it open; give it a moment


def format_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.1f} MB"


# ---------------------------------------------------------------------------
# Sidebar — documents only. No API key / model controls: those are read
# silently from .env so the person using the app never has to see or think
# about backend configuration, the same way ChatGPT doesn't show you which
# model or credentials are running underneath.
# ---------------------------------------------------------------------------

def render_documents_section(key_prefix: str, show_heading: bool = True) -> None:
    """Render a clear upload action and compact document cards."""
    if show_heading:
        st.markdown("### Documents")
        st.caption("Add files to ask questions grounded in them.")
    st.markdown('<div class="dm-upload-label">Add documents</div>', unsafe_allow_html=True)
    uploaded_files = st.file_uploader(
        "Add documents",
        type=["txt", "md", "csv", "json", "log", "pdf", "docx", "xlsx"],
        accept_multiple_files=True,
        key=f"{key_prefix}_uploader",
        label_visibility="collapsed",
    )
    if uploaded_files:
        for f in uploaded_files:
            if (f.name, f.size) in st.session_state.processed_files:
                continue
            with st.spinner(f'Reading "{f.name}"… (scanned PDFs can take a bit longer)'):
                add_uploaded_file(f)

    if dm.documents:
        for name, doc_size in [(n, len(d.text)) for n, d in dm.documents.items()]:
            safe_name = html.escape(name)
            suffix = Path(name).suffix.replace('.', '').upper() or 'FILE'
            with st.container(key=f"docrow_{key_prefix}_{name}"):
                card_col, btn_col = st.columns([5, 1])
                with card_col:
                    st.markdown(
                        f'<div class="dm-doc-card"><span class="glyph">📄</span>'
                        f'<div class="meta"><div class="fname">{safe_name}</div>'
                        f'<div class="fsize">{suffix} · {format_size(doc_size)} of text</div></div></div>',
                        unsafe_allow_html=True,
                    )
                with btn_col:
                    with st.container(key=f"docactions_{key_prefix}_{name}"):
                        if st.button("🗑", key=f"{key_prefix}_remove_{name}", help="Remove document"):
                            dm.remove_document(name)
                            st.rerun()
    else:
        st.caption("No documents yet.")


with st.sidebar:
    with st.container(key="panel_profile"):
        st.markdown(f"**👤 {html.escape(st.session_state.username)}**")
        with st.popover("Account & settings", use_container_width=True):
            st.caption("Signed in as")
            st.markdown(f"**{html.escape(st.session_state.username)}**")
            st.divider()
            st.caption("Remember Me is active for up to 30 days when enabled at login.")
            if st.button("Log out", use_container_width=True, key="profile_logout"):
                remember_token = st.context.cookies.get(REMEMBER_COOKIE_NAME) if hasattr(st, "context") else None
                if remember_token:
                    accounts.revoke_remember_token(remember_token)
                delete_remember_cookie()
                st.session_state.user_id = None
                st.session_state.username = None
                st.session_state.chat_history = []
                st.session_state.current_chat_id = None
                st.session_state.processed_files = set()
                st.rerun()

    with st.container(key="panel_documents"):
        render_documents_section("sidebar")

    with st.container(key="panel_chats"):
        if st.button("+ New chat", use_container_width=True):
            st.session_state.chat_history = []
            st.session_state.current_chat_id = None
            st.rerun()

        saved_chats = accounts.list_chats(st.session_state.user_id)
        if saved_chats:
            st.markdown("### Chats")
            for c in saved_chats:
                if st.session_state.renaming_chat_id == c.id:
                    new_name = st.text_input(
                        "Rename", value=c.name, key=f"rename_input_{c.id}", label_visibility="collapsed"
                    )
                    rc1, rc2 = st.columns(2)
                    with rc1:
                        if st.button("Save name", key=f"rename_save_{c.id}", use_container_width=True):
                            accounts.rename_chat(c.id, st.session_state.user_id, new_name)
                            st.session_state.renaming_chat_id = None
                            st.rerun()
                    with rc2:
                        if st.button("Cancel", key=f"rename_cancel_{c.id}", use_container_width=True):
                            st.session_state.renaming_chat_id = None
                            st.rerun()
                else:
                    with st.container(key=f"chatrow_{c.id}"):
                        name_col, edit_col, del_col = st.columns([5, 1, 1], vertical_alignment="center")
                        with name_col:
                            with st.container(key=f"chatopen_{c.id}"):
                                label = c.name + (" •" if c.id == st.session_state.current_chat_id else "")
                                if st.button(label, key=f"open_{c.id}", use_container_width=True, help="Open this chat"):
                                    loaded = accounts.load_chat(c.id, st.session_state.user_id)
                                    if loaded is not None:
                                        st.session_state.chat_history = loaded.messages
                                        st.session_state.current_chat_id = loaded.id
                                        st.rerun()
                        with edit_col:
                            with st.container(key=f"chatedit_{c.id}"):
                                if st.button("✎", key=f"edit_{c.id}", help="Rename"):
                                    st.session_state.renaming_chat_id = c.id
                                    st.rerun()
                        with del_col:
                            with st.container(key=f"chatdel_{c.id}"):
                                if st.button("🗑", key=f"del_{c.id}", help="Delete"):
                                    accounts.delete_chat(c.id, st.session_state.user_id)
                                    if st.session_state.current_chat_id == c.id:
                                        st.session_state.current_chat_id = None
                                    st.rerun()

    if not dm.has_api_key():
        st.caption("⚠️ No API key found in .env — the assistant won't be able to respond yet.")

# ---------------------------------------------------------------------------
# Main panel — chat
# ---------------------------------------------------------------------------

render_header()

for msg in st.session_state.chat_history:
    render_bubble(msg["role"], msg["content"], msg.get("sources"))


def handle_question(q: str) -> None:
    """Answer a question and persist both the conversation and its sources."""
    render_bubble("user", q)

    if not dm.has_api_key():
        answer = (
            "This assistant isn't connected yet — an API key needs to be added to "
            "the .env file before I can respond. (See the README's setup section.)"
        )
        sources = []
    else:
        with st.spinner("Thinking…"):
            api_history = [
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.chat_history
            ]
            try:
                answer, sources = dm.ask_with_sources(q, history=api_history)
            except RuntimeError as e:
                answer, sources = str(e), []
            except Exception as e:
                answer, sources = f"Something went wrong calling the model: {e}", []

    render_bubble("assistant", answer, sources)

    source_data = []
    seen = set()
    for source in sources:
        item = {"doc_name": source.doc_name, "page": source.page}
        key = (item["doc_name"], item["page"])
        if key not in seen:
            seen.add(key)
            source_data.append(item)

    st.session_state.chat_history.append({"role": "user", "content": q})
    st.session_state.chat_history.append({
        "role": "assistant",
        "content": answer,
        "sources": source_data,
    })

    st.session_state.current_chat_id = accounts.save_chat(
        st.session_state.user_id,
        st.session_state.chat_history,
        chat_id=st.session_state.current_chat_id,
    )

    # Without this, the answer above was rendered inline mid-script using
    # state captured *before* this function ran - so anything drawn earlier
    # in this same run (like the "Start with a question" suggestion
    # buttons, drawn while chat_history was still empty) stays on screen
    # next to the brand-new answer instead of being replaced by it. A
    # rerun forces a clean pass where that earlier block correctly sees
    # the now-updated chat_history and skips itself.
    st.rerun()


# First-use empty state: plain text, nothing else.
if not st.session_state.chat_history and not dm.documents:
    st.markdown("## Welcome to FileWhisperer")

elif not st.session_state.chat_history and dm.documents:
    st.caption("Start with a question about your documents")
    suggestions = [
        "Summarize this document",
        "What are the key points?",
        "Any important numbers or dates?",
    ]
    suggestion_cols = st.columns(len(suggestions))
    clicked_suggestion = None
    for col, suggestion in zip(suggestion_cols, suggestions):
        with col:
            if st.button(suggestion, key=f"suggest_{suggestion}", use_container_width=True):
                clicked_suggestion = suggestion
    if clicked_suggestion:
        handle_question(clicked_suggestion)

question = st.chat_input("Ask anything about your documents…")
if question:
    handle_question(question)
