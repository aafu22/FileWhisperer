"""FileWhisperer — Streamlit UI.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import html
import os
import tempfile
import time
from pathlib import Path

import streamlit as st
from streamlit_cookies_manager import CookieManager

from filewhisperer import FileWhisperer
from filewhisperer import accounts
from filewhisperer.loaders import EmptyDocument, UnsupportedFileType


# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="FileWhisperer",
    page_icon="",
    layout="wide",
    initial_sidebar_state="auto",
)

# Persistent browser storage for Remember Me.
# The token itself is random; only its SHA-256 hash is stored server-side in Turso.
cookies = CookieManager()
if not cookies.ready():
    st.stop()

REMEMBER_COOKIE = "filewhisperer_remember"


# ---------------------------------------------------------------------------
# Visual identity
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

html,
body,
.stApp {
    background: var(--bg);
    color: var(--ink);
    font-family: 'IBM Plex Sans', -apple-system, sans-serif;
}

footer {
    visibility: hidden;
}

h1,
h2,
h3,
h4 {
    font-family: 'Fraunces', Georgia, serif;
    font-weight: 600;
    color: var(--ink);
    letter-spacing: -0.01em;
}

p,
span,
label,
div {
    color: var(--ink);
}


/* -----------------------------------------------------------------------
   Sidebar
   ----------------------------------------------------------------------- */

[data-testid="stSidebar"] {
    background: var(--sidebar-bg);
    border-right: 1px solid var(--border);
}

[data-testid="stSidebar"] h3 {
    font-size: 1.05rem;
    margin-top: 0.2rem;
    margin-bottom: 0.6rem;
}

div[class*="st-key-panel_"] {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 0.85rem 0.9rem 0.6rem 0.9rem;
    margin-bottom: 0.9rem;
}


/* -----------------------------------------------------------------------
   Buttons
   ----------------------------------------------------------------------- */

.stButton button,
[data-testid="stChatInput"] button {
    border-radius: 7px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--ink);
    font-weight: 500;
    transition:
        border-color 0.15s ease,
        color 0.15s ease,
        background 0.15s ease;
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


/* -----------------------------------------------------------------------
   Sample quarterly report button
   ----------------------------------------------------------------------- */

div[class*="st-key-sample_report_button"] button {
    background: #0E7C66 !important;
    border-color: #0E7C66 !important;
    color: white !important;
    font-weight: 600 !important;
}

div[class*="st-key-sample_report_button"] button:hover {
    background: #14997D !important;
    border-color: #14997D !important;
    color: white !important;
}


/* -----------------------------------------------------------------------
   Auth card
   ----------------------------------------------------------------------- */

div[class*="st-key-auth_card"] {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 2rem 2rem 1rem 2rem;
    margin-top: 3rem;
    box-shadow:
        0 4px 24px rgba(0, 0, 0, 0.45),
        0 1px 3px rgba(0, 0, 0, 0.3);
}

div[class*="st-key-auth_card"]
[data-testid="stTabs"]
button[role="tab"] {
    font-weight: 500;
    color: var(--ink-muted);
}

div[class*="st-key-auth_card"]
[data-testid="stTabs"]
button[aria-selected="true"] {
    color: var(--accent);
}

div[class*="st-key-auth_card"]
[data-testid="stTabs"]
[data-baseweb="tab-highlight"] {
    background-color: var(--accent) !important;
}


/* -----------------------------------------------------------------------
   Inputs
   ----------------------------------------------------------------------- */

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


/* -----------------------------------------------------------------------
   File uploader
   ----------------------------------------------------------------------- */

[data-testid="stFileUploaderDropzone"] {
    background: var(--surface);
    border: 1.5px dashed var(--border);
    border-radius: 8px;
}

[data-testid="stFileUploaderDropzone"]:hover {
    border-color: var(--accent);
}


/* -----------------------------------------------------------------------
   Alerts
   ----------------------------------------------------------------------- */

[data-testid="stAlert"] {
    border-radius: 8px;
    font-family: 'IBM Plex Sans', sans-serif;
}


/* -----------------------------------------------------------------------
   Chat bubbles
   ----------------------------------------------------------------------- */

.dm-row {
    display: flex;
    margin: 0.5rem 0;
}

.dm-row.user {
    justify-content: flex-end;
}

.dm-row.assistant {
    justify-content: flex-start;
}

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

.dm-bubble.user p,
.dm-bubble.user li,
.dm-bubble.user span {
    color: white;
}

/* Documents attached to a specific user question. */
.dm-attachments {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin-bottom: 0.5rem;
}

.dm-attachment {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    max-width: 100%;
    padding: 0.28rem 0.5rem;
    border: 1px solid rgba(255, 255, 255, 0.22);
    border-radius: 7px;
    background: rgba(0, 0, 0, 0.16);
    color: white !important;
    font-size: 0.76rem;
    line-height: 1.2;
}

.dm-attachment-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 30rem;
    color: white !important;
}

.dm-bubble.assistant {
    background: var(--surface);
    color: var(--ink);
}

.dm-bubble p:first-child {
    margin-top: 0;
}

.dm-bubble p:last-child {
    margin-bottom: 0;
}

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
    background: rgba(255, 255, 255, 0.18);
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

.dm-bubble ul,
.dm-bubble ol {
    margin: 0.3rem 0;
    padding-left: 1.4rem;
}


/* -----------------------------------------------------------------------
   Sidebar rows
   ----------------------------------------------------------------------- */

div[class*="st-key-chatrow_"],
div[class*="st-key-docrow_"] {
    border-radius: 8px;
    padding: 2px 4px;
    transition: background 0.15s ease;
}

div[class*="st-key-chatrow_"]:hover,
div[class*="st-key-docrow_"]:hover {
    background: var(--accent-soft);
}

div[class*="st-key-chatedit_"],
div[class*="st-key-chatdel_"],
div[class*="st-key-docactions_"] {
    opacity: 0;
    transition: opacity 0.15s ease;
}

div[class*="st-key-chatrow_"]:hover
div[class*="st-key-chatedit_"],
div[class*="st-key-chatrow_"]:hover
div[class*="st-key-chatdel_"],
div[class*="st-key-docrow_"]:hover
div[class*="st-key-docactions_"] {
    opacity: 1;
}

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

div[class*="st-key-panel_profile"] .stButton button {
    padding: 0.35rem 0.5rem;
    font-size: 0.85rem;
    white-space: nowrap;
}


/* -----------------------------------------------------------------------
   Header
   ----------------------------------------------------------------------- */

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
    background: linear-gradient(
        90deg,
        var(--accent) 0%,
        var(--border) 55%
    );
    border: none;
    margin: 0 0 1.4rem 0;
}


/* -----------------------------------------------------------------------
   Document cards
   ----------------------------------------------------------------------- */

.dm-doc-card {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    padding: 0.5rem 0.6rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    margin-bottom: 0.4rem;
    min-width: 0;
}

.dm-doc-card .glyph {
    font-size: 1.05rem;
    color: var(--accent);
    flex-shrink: 0;
}

.dm-doc-card .meta {
    line-height: 1.25;
    overflow: hidden;
    min-width: 0;
}

.dm-doc-card .fname {
    font-weight: 500;
    font-size: 0.88rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.dm-doc-card .fsize {
    font-size: 0.76rem;
    color: var(--ink-muted);
}

.dm-doc-card:hover {
    border-color: var(--accent);
    transform: translateY(-1px);
}


/* -----------------------------------------------------------------------
   Auth
   ----------------------------------------------------------------------- */

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


/* -----------------------------------------------------------------------
   Sources
   ----------------------------------------------------------------------- */

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


/* -----------------------------------------------------------------------
   Quick start
   ----------------------------------------------------------------------- */

.fw-question-label {
    color: #9ca3af;
    font-size: 15px;
    font-weight: 600;
    margin: 34px 0 16px 0;
}


/* -----------------------------------------------------------------------
   Responsive
   ----------------------------------------------------------------------- */

@media (max-width: 900px) {

    .dm-bubble {
        max-width: 90%;
    }

    .dm-sources {
        max-width: 90%;
    }

}

/* -----------------------------------------------------------------------
   Mobile
   ----------------------------------------------------------------------- */

@media (max-width: 768px) {

    [data-testid="stMainBlockContainer"] {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }

    [data-testid="stSidebar"] {
        width: min(88vw, 360px) !important;
    }

    [data-testid="stSidebar"] > div:first-child {
        padding-left: 0.75rem;
        padding-right: 0.75rem;
    }

    div[class*="st-key-panel_"] {
        padding: 0.7rem 0.75rem 0.55rem 0.75rem;
        margin-bottom: 0.7rem;
        border-radius: 10px;
    }

    .dm-header {
        gap: 0.35rem;
        margin-top: 0.4rem;
    }

    .dm-header .mark,
    .dm-header .word {
        font-size: 1.85rem;
    }

    .dm-tagline {
        font-size: 0.88rem;
        line-height: 1.45;
        max-width: 100%;
    }

    .dm-rule {
        margin-bottom: 1rem;
    }

    .fw-question-label {
        font-size: 0.9rem;
        margin-top: 1.5rem;
        margin-bottom: 0.75rem;
    }

    .stButton button {
        min-height: 44px !important;
        font-size: 0.92rem;
    }

    div[class*="st-key-suggest_"] button {
        min-height: 46px !important;
    }

    .dm-bubble {
        max-width: 94%;
        padding: 0.55rem 0.75rem;
        font-size: 0.92rem;
    }

    .dm-sources {
        max-width: 94%;
    }

    [data-testid="stChatInput"] {
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
    }

    [data-testid="stChatInput"] textarea {
        font-size: 0.92rem !important;
    }

    [data-testid="stChatInput"] button {
        min-width: 44px !important;
        min-height: 44px !important;
    }

    [data-testid="stFileUploaderDropzone"] {
        padding: 0.65rem !important;
    }

    div[class*="st-key-sample_report_button"] button {
        min-height: 46px !important;
    }
}


/* --- Compact document actions --- */
div[class*="st-key-docactions_"] {
    opacity: 1 !important;
}
div[class*="st-key-docactions_"] [data-testid="stHorizontalBlock"] {
    gap: 0.2rem !important;
}
div[class*="st-key-docactions_"] .stButton button {
    width: 2rem !important;
    min-width: 2rem !important;
    height: 2rem !important;
    min-height: 2rem !important;
    padding: 0 !important;
    border-radius: 7px !important;
    border: 1px solid transparent !important;
    background: transparent !important;
    color: var(--ink-muted) !important;
    font-size: 0.9rem !important;
}
div[class*="st-key-docactions_"] .stButton button:hover {
    background: var(--accent-soft) !important;
    border-color: var(--border) !important;
    color: var(--ink) !important;
}

</style>
"""

st.markdown(
    CUSTOM_CSS,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Accounts / Remember Me
# ---------------------------------------------------------------------------

accounts.init_db()
st.caption(f"backend={'turso' if os.getenv('TURSO_DATABASE_URL') else 'sqlite'} · url_set={bool(os.getenv('TURSO_DATABASE_URL'))} · token_set={bool(os.getenv('TURSO_AUTH_TOKEN'))}")

@st.cache_resource
def _cleanup_expired_tokens_once() -> bool:
    accounts.cleanup_expired_tokens()
    return True

_cleanup_expired_tokens_once()

SIGNUP_CODE = os.environ.get(
    "FILEWHISPERER_SIGNUP_CODE",
    os.environ.get("DOCUMIND_SIGNUP_CODE", ""),
).strip()

# 30-day Remember Me.
# The browser keeps the random token in a persistent cookie. Turso stores only
# the token hash and enforces the 30-day expiry.
REMEMBER_ME_SECONDS = 30 * 24 * 60 * 60


def get_remember_token_from_browser() -> str | None:
    """Read the persistent login token from the browser cookie."""
    try:
        token = cookies.get(REMEMBER_COOKIE)
        return token.strip() if isinstance(token, str) and token.strip() else None
    except Exception:
        return None


def set_remember_token_in_browser(token: str) -> None:
    """Persist the remember-me token in the browser."""
    if not token:
        return
    cookies[REMEMBER_COOKIE] = token
    cookies.save()


def delete_remember_token_from_browser() -> None:
    """Remove the remember-me token from the browser."""
    try:
        if cookies.get(REMEMBER_COOKIE) is not None:
            del cookies[REMEMBER_COOKIE]
            cookies.save()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Authentication state
# ---------------------------------------------------------------------------

if "user_id" not in st.session_state:
    st.session_state.user_id = None

if "username" not in st.session_state:
    st.session_state.username = None

if "remember_token" not in st.session_state:
    st.session_state.remember_token = None


# ---------------------------------------------------------------------------
# Restore Remember Me session
# ---------------------------------------------------------------------------

if st.session_state.user_id is None:

    remember_token = get_remember_token_from_browser()

    if remember_token:
        try:
            session = accounts.authenticate_remember_token(
                remember_token
            )

            if session:
                (
                    st.session_state.user_id,
                    st.session_state.username,
                ) = session
                st.session_state.remember_token = remember_token

        except Exception as e:
            st.error(f"Remember-me restore failed: {e!r}")


# ---------------------------------------------------------------------------
# Login / Signup
# ---------------------------------------------------------------------------

if st.session_state.user_id is None:

    left_pad, card_col, right_pad = st.columns(
        [1, 1.3, 1]
    )

    with card_col:

        with st.container(
            key="auth_card"
        ):

            st.markdown(
                """
                <div class="auth-title">
                    <span class="mark">File</span> Whisperer
                </div>

                <div class="auth-subtitle">
                    Your documents. One conversation.
                </div>

                <div class="auth-private">
                    Upload files, ask questions, and get answers
                    grounded in your documents.
                </div>

                <div class="auth-pills">
                    <span class="auth-pill">PDF</span>
                    <span class="auth-pill">DOCX</span>
                    <span class="auth-pill">CSV</span>
                    <span class="auth-pill">XLSX</span>
                    <span class="auth-pill">TXT</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            login_tab, signup_tab = st.tabs(
                ["Log in", "Sign up"]
            )

            # Login
            with login_tab:

                with st.form(
                    "login_form"
                ):

                    li_username = st.text_input(
                        "Username",
                        placeholder="Enter your username",
                        key="li_username",
                    )

                    li_password = st.text_input(
                        "Password",
                        type="password",
                        placeholder="Enter your password",
                        key="li_password",
                    )

                    remember_me = st.checkbox(
                        "Remember me for 30 days",
                        value=True,
                        key="remember_me",
                    )

                    if st.form_submit_button(
                        "Log in",
                        use_container_width=True,
                    ):

                        try:

                            user_id = accounts.authenticate(
                                li_username,
                                li_password,
                            )

                            st.session_state.user_id = user_id

                            st.session_state.username = (
                                li_username.strip()
                            )

                            if remember_me:

                                token = (
                                    accounts.create_remember_token(
                                        user_id
                                    )
                                )

                                st.session_state.remember_token = token

                                set_remember_token_in_browser(
                                    token
                                )

                            else:
                                st.session_state.remember_token = None

                                delete_remember_token_from_browser()


                        except accounts.InvalidCredentials as e:

                            st.error(
                                str(e)
                            )

            # Signup
            with signup_tab:

                with st.form(
                    "signup_form"
                ):

                    su_username = st.text_input(
                        "Choose a username",
                        placeholder="Pick a username",
                        key="su_username",
                    )

                    su_password = st.text_input(
                        "Choose a password",
                        type="password",
                        placeholder="At least 8 characters",
                        key="su_password",
                    )

                    su_password2 = st.text_input(
                        "Confirm password",
                        type="password",
                        placeholder="Re-enter your password",
                        key="su_password2",
                    )

                    su_code = (
                        st.text_input(
                            "Invite code",
                            type="password",
                            key="su_code",
                        )
                        if SIGNUP_CODE
                        else None
                    )

                    if st.form_submit_button(
                        "Create account",
                        use_container_width=True,
                    ):

                        if (
                            SIGNUP_CODE
                            and su_code != SIGNUP_CODE
                        ):

                            st.error(
                                "Incorrect invite code."
                            )

                        elif su_password != su_password2:

                            st.error(
                                "Passwords don't match."
                            )

                        elif len(su_password) < 8:

                            st.error(
                                "Password should be at least "
                                "8 characters."
                            )

                        else:

                            try:

                                user_id = accounts.create_user(
                                    su_username,
                                    su_password,
                                )

                                st.session_state.user_id = user_id

                                st.session_state.username = (
                                    su_username.strip()
                                )

                                token = (
                                    accounts.create_remember_token(
                                        user_id
                                    )
                                )

                                st.session_state.remember_token = token

                                set_remember_token_in_browser(
                                    token
                                )

                                # The V2 cookie component triggers the rerun
                                # after the browser has completed the operation.

                            except (
                                accounts.UsernameTaken,
                                ValueError,
                            ) as e:

                                st.error(
                                    str(e)
                                )

    st.stop()


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

def render_header() -> None:

    st.markdown(
        """
        <div class="dm-header">
            <span class="mark">File</span>
            <span class="word">Whisperer</span>
        </div>

        <div class="dm-tagline">
            Turn your files into conversations —
            with answers grounded in your documents.
        </div>

        <hr class="dm-rule" />
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Chat bubble
# ---------------------------------------------------------------------------

def render_bubble(
    role: str,
    content: str,
    sources: list | None = None,
    attachments: list[str] | None = None,
) -> None:
    """Render one chat bubble.

    Documents are shown on the *user* message that asked about them, rather
    than as one global attachment/source strip above the conversation.
    ``attachments`` is a snapshot saved with that individual message, so
    opening an old chat does not make old questions appear to use documents
    that were uploaded later.
    """

    css_role = (
        "user"
        if role == "user"
        else "assistant"
    )

    attachment_html = ""

    if css_role == "user" and attachments:
        chips = []

        seen = set()

        for name in attachments:
            if not name or name in seen:
                continue

            seen.add(name)
            safe_name = html.escape(str(name))

            chips.append(
                '<span class="dm-attachment">'
                '<span>📄</span>'
                f'<span class="dm-attachment-name">{safe_name}</span>'
                '</span>'
            )

        if chips:
            attachment_html = (
                '<div class="dm-attachments">'
                + "".join(chips)
                + '</div>'
            )

    st.markdown(
        f'<div class="dm-row {css_role}">'
        f'<div class="dm-bubble {css_role}">'
        f'{attachment_html}'
        f'{content}'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Cached remote database reads
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60, show_spinner=False)
def _cached_list_chats(user_id: int):
    return accounts.list_chats(user_id)


@st.cache_data(ttl=60, show_spinner=False)
def _cached_list_chat_documents(chat_id: str, user_id: int):
    return accounts.list_chat_documents(chat_id, user_id)


def _refresh_remote_caches() -> None:
    _cached_list_chats.clear()
    _cached_list_chat_documents.clear()

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "dm" not in st.session_state:
    st.session_state.dm = FileWhisperer()

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None

if "renaming_chat_id" not in st.session_state:
    st.session_state.renaming_chat_id = None

if "viewing_document_name" not in st.session_state:
    st.session_state.viewing_document_name = None


dm: FileWhisperer = st.session_state.dm


# ---------------------------------------------------------------------------
# Chat-scoped document management
# ---------------------------------------------------------------------------

SUPPORTED_FILE_TYPES = [
    "txt",
    "md",
    "csv",
    "json",
    "log",
    "pdf",
    "docx",
    "xlsx",
]


def reset_document_manager() -> None:
    """Start a clean document scope for a new/current chat."""
    st.session_state.dm = FileWhisperer()


def ensure_current_chat(name: str | None = None) -> str:
    """Create a chat row when a document or message needs a chat scope."""
    chat_id = st.session_state.current_chat_id

    if chat_id:
        return chat_id

    chat_id = accounts.save_chat(
        st.session_state.user_id,
        st.session_state.chat_history,
        name=name,
    )
    st.session_state.current_chat_id = chat_id
    return chat_id


def load_chat_documents(chat_id: str) -> None:
    """Rebuild the in-memory RAG index from documents saved for this chat."""
    reset_document_manager()

    documents = _cached_list_chat_documents(chat_id, st.session_state.user_id)

    for stored in documents:
        suffix = Path(stored.filename).suffix

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=suffix,
        ) as tmp:
            tmp.write(stored.data)
            tmp_path = tmp.name

        try:
            st.session_state.dm.add_document(
                tmp_path,
                display_name=stored.filename,
            )
        except Exception as e:
            st.sidebar.warning(
                f'Couldn\'t reload "{stored.filename}": {e}'
            )
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass


def ingest_uploaded_file(
    uploaded_file,
    chat_id: str,
) -> bool:
    """Ingest an uploaded file into the current chat and persist its bytes."""
    data = uploaded_file.getvalue()
    suffix = Path(uploaded_file.name).suffix

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=suffix,
    ) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        st.session_state.dm.add_document(
            tmp_path,
            display_name=uploaded_file.name,
        )

        _refresh_remote_caches()
        accounts.save_chat_document(
            chat_id=chat_id,
            user_id=st.session_state.user_id,
            filename=uploaded_file.name,
            file_type=uploaded_file.type or "",
            data=data,
        )

        return True

    except UnsupportedFileType as e:
        st.sidebar.warning(str(e))
        return False

    except EmptyDocument as e:
        st.sidebar.warning(str(e))
        return False

    except Exception as e:
        st.sidebar.error(
            f'Couldn\'t read "{uploaded_file.name}": {e}'
        )
        return False

    finally:
        for _ in range(3):
            try:
                Path(tmp_path).unlink(missing_ok=True)
                break
            except PermissionError:
                time.sleep(0.2)


def load_sample_report() -> None:
    """Create a chat containing the bundled sample quarterly report."""
    sample_dir = Path("sample_documents")

    if not sample_dir.exists():
        st.sidebar.error("Sample document folder not found.")
        return

    preferred_sample = sample_dir / "Sample_Quarterly_Report.md"

    if preferred_sample.exists():
        sample_path = preferred_sample
    else:
        supported_extensions = {
            ".pdf",
            ".md",
            ".txt",
            ".docx",
            ".csv",
            ".xlsx",
        }

        sample_files = sorted(
            file
            for file in sample_dir.iterdir()
            if file.is_file()
            and file.suffix.lower() in supported_extensions
        )

        if not sample_files:
            st.sidebar.error(
                "No sample document found in sample_documents."
            )
            return

        sample_path = sample_files[0]

    # Always create a fresh sample-report chat. This keeps the sample isolated
    # from the user's other conversations.
    st.session_state.chat_history = []
    st.session_state.current_chat_id = accounts.save_chat(
        st.session_state.user_id,
        [],
        name="Sample Quarterly Report",
    )

    reset_document_manager()

    try:
        with st.spinner("Loading sample quarterly report…"):
            with open(sample_path, "rb") as f:
                data = f.read()

            suffix = sample_path.suffix

            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=suffix,
            ) as tmp:
                tmp.write(data)
                tmp_path = tmp.name

            try:
                st.session_state.dm.add_document(
                    tmp_path,
                    display_name=sample_path.name,
                )
            finally:
                try:
                    Path(tmp_path).unlink(missing_ok=True)
                except Exception:
                    pass

            _refresh_remote_caches()
        accounts.save_chat_document(
                chat_id=st.session_state.current_chat_id,
                user_id=st.session_state.user_id,
                filename=sample_path.name,
                file_type="text/markdown",
                data=data,
            )

        st.rerun()

    except Exception as e:
        st.sidebar.error(
            f"Couldn't load sample report: {e}"
        )


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"

    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"

    return f"{num_bytes / (1024 * 1024):.1f} MB"


def render_document_viewer(chat_id: str | None) -> None:
    """Show the selected chat document in the main panel."""
    filename = st.session_state.get("viewing_document_name")
    if not chat_id or not filename:
        return

    documents = _cached_list_chat_documents(chat_id, st.session_state.user_id)
    document = next(
        (item for item in documents if item.filename == filename),
        None,
    )

    if document is None:
        st.session_state.viewing_document_name = None
        return

    st.markdown(
        f'<div class="dm-doc-viewer-title">📄 {html.escape(document.filename)}</div>',
        unsafe_allow_html=True,
    )

    close_col, download_col = st.columns([1, 1])
    with close_col:
        if st.button("Close file", key=f"close_view_{chat_id}_{filename}"):
            st.session_state.viewing_document_name = None
            st.rerun()

    with download_col:
        st.download_button(
            "Download file",
            data=document.data,
            file_name=document.filename,
            mime=document.file_type or "application/octet-stream",
            key=f"download_view_{chat_id}_{filename}",
            use_container_width=True,
        )

    suffix = Path(document.filename).suffix.lower()

    if suffix == ".pdf":
        try:
            st.pdf(document.data)
        except Exception:
            st.info("PDF preview isn't available in this Streamlit build. Use Download file to open it.")
    else:
        loaded = st.session_state.dm.documents.get(document.filename)
        text_content = loaded.text if loaded else ""
        if text_content.strip():
            st.text_area(
                "File contents",
                value=text_content,
                height=500,
                disabled=True,
                label_visibility="collapsed",
            )
        else:
            st.info("This file was uploaded, but no readable text was extracted from it.")


def render_chat_documents(
    chat_id: str | None,
    *,
    sidebar: bool = False,
) -> None:
    """Render the files belonging only to the currently open chat."""
    if not chat_id:
        if sidebar:
            st.caption("No documents attached to this chat yet.")
        return

    documents = _cached_list_chat_documents(chat_id, st.session_state.user_id)

    if sidebar:
        st.markdown("### Documents")
        if not documents:
            st.caption("No documents attached to this chat yet.")
            return

        for document in documents:
            safe_name = html.escape(document.filename)
            suffix = (
                Path(document.filename)
                .suffix
                .replace(".", "")
                .upper()
                or "FILE"
            )

            with st.container(
                key=f"docrow_{chat_id}_{document.filename}"
            ):
                card_col, actions_col = st.columns([4.8, 1.6])

                with card_col:
                    st.markdown(
                        f'<div class="dm-doc-card">'
                        f'<span class="glyph">📄</span>'
                        f'<div class="meta">'
                        f'<div class="fname">{safe_name}</div>'
                        f'<div class="fsize">'
                        f'{suffix} · {format_size(document.size_bytes)}'
                        f'</div>'
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                with actions_col:
                    with st.container(
                        key=f"docactions_{chat_id}_{document.filename}"
                    ):
                        view_col, delete_col = st.columns(2, gap="small")

                        with view_col:
                            if st.button(
                                "◉",
                                key=f"view_{chat_id}_{document.filename}",
                                help="View file",
                            ):
                                st.session_state.viewing_document_name = document.filename
                                st.rerun()

                        with delete_col:
                            if st.button(
                                "🗑",
                                key=f"remove_{chat_id}_{document.filename}",
                                help="Delete file",
                            ):
                                accounts.delete_chat_document(
                                    chat_id,
                                    st.session_state.user_id,
                                    document.filename,
                                )
                                _refresh_remote_caches()
                                if (
                                    st.session_state.viewing_document_name
                                    == document.filename
                                ):
                                    st.session_state.viewing_document_name = None
                                reset_document_manager()
                                load_chat_documents(chat_id)
                                st.rerun()

        return

    # Main-panel attachment strip.
    if not documents:
        return

    chips = []

    for document in documents:
        safe_name = html.escape(document.filename)
        chips.append(
            f'<span class="dm-source">📄 {safe_name}</span>'
        )

    st.markdown(
        '<div class="dm-sources" style="max-width:100%; margin-bottom:1rem;">'
        '<strong>In this chat</strong> &nbsp;'
        + "".join(chips)
        + "</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:

    # Account
    with st.container(key="panel_profile"):
        st.markdown(
            f"**👤 {html.escape(st.session_state.username)}**"
        )

        with st.popover(
            "Account & settings",
            use_container_width=True,
        ):
            st.caption("Signed in as")
            st.markdown(
                f"**{html.escape(st.session_state.username)}**"
            )

            st.divider()

            st.caption(
                "Remember Me is active for up to "
                "30 days when enabled at login."
            )

            if st.button(
                "Log out",
                use_container_width=True,
                key="profile_logout",
            ):
                remember_token = st.session_state.remember_token

                if not remember_token:
                    remember_token = get_remember_token_from_browser()

                if remember_token:
                    accounts.revoke_remember_token(remember_token)

                delete_remember_token_from_browser()

                st.session_state.user_id = None
                st.session_state.username = None
                st.session_state.remember_token = None
                st.session_state.chat_history = []
                st.session_state.current_chat_id = None
                reset_document_manager()

                st.stop()

    # Chat controls
    with st.container(key="panel_chats"):

        if st.button(
            "+ New chat",
            use_container_width=True,
            key="new_chat",
        ):
            st.session_state.chat_history = []
            st.session_state.current_chat_id = None
            reset_document_manager()
            st.rerun()

        st.markdown("### Chats")

        saved_chats = _cached_list_chats(st.session_state.user_id)

        if saved_chats:
            for c in saved_chats:

                if st.session_state.renaming_chat_id == c.id:
                    new_name = st.text_input(
                        "Rename",
                        value=c.name,
                        key=f"rename_input_{c.id}",
                        label_visibility="collapsed",
                    )

                    rc1, rc2 = st.columns(2)

                    with rc1:
                        if st.button(
                            "Save name",
                            key=f"rename_save_{c.id}",
                            use_container_width=True,
                        ):
                            _refresh_remote_caches()
                            accounts.rename_chat(
                                c.id,
                                st.session_state.user_id,
                                new_name,
                            )
                            st.session_state.renaming_chat_id = None
                            st.rerun()

                    with rc2:
                        if st.button(
                            "Cancel",
                            key=f"rename_cancel_{c.id}",
                            use_container_width=True,
                        ):
                            st.session_state.renaming_chat_id = None
                            st.rerun()

                else:
                    with st.container(key=f"chatrow_{c.id}"):
                        name_col, edit_col, del_col = st.columns(
                            [5, 1, 1],
                            vertical_alignment="center",
                        )

                        with name_col:
                            with st.container(key=f"chatopen_{c.id}"):
                                label = (
                                    c.name
                                    + (
                                        " •"
                                        if c.id
                                        == st.session_state.current_chat_id
                                        else ""
                                    )
                                )

                                if st.button(
                                    label,
                                    key=f"open_{c.id}",
                                    use_container_width=True,
                                    help="Open this chat",
                                ):
                                    loaded = accounts.load_chat(
                                        c.id,
                                        st.session_state.user_id,
                                    )

                                    if loaded is not None:
                                        st.session_state.chat_history = (
                                            loaded.messages
                                        )
                                        st.session_state.current_chat_id = (
                                            loaded.id
                                        )
                                        load_chat_documents(loaded.id)
                                        st.rerun()

                        with edit_col:
                            with st.container(key=f"chatedit_{c.id}"):
                                if st.button(
                                    "✎",
                                    key=f"edit_{c.id}",
                                    help="Rename",
                                ):
                                    st.session_state.renaming_chat_id = c.id
                                    st.rerun()

                        with del_col:
                            with st.container(key=f"chatdel_{c.id}"):
                                if st.button(
                                    "🗑",
                                    key=f"del_{c.id}",
                                    help="Delete",
                                ):
                                    _refresh_remote_caches()
                                    accounts.delete_chat(
                                        c.id,
                                        st.session_state.user_id,
                                    )

                                    if (
                                        st.session_state.current_chat_id
                                        == c.id
                                    ):
                                        st.session_state.current_chat_id = None
                                        st.session_state.chat_history = []
                                        reset_document_manager()

                                    st.rerun()

        else:
            st.caption("No chats yet.")

    # Documents belonging only to the current chat.
    with st.container(key="panel_documents"):
        render_chat_documents(
            st.session_state.current_chat_id,
            sidebar=True,
        )

        st.markdown("---")

        with st.container(key="sample_report_button"):
            if st.button(
                "Try sample quarterly report",
                use_container_width=True,
                key="sample_report",
            ):
                load_sample_report()

    if not dm.has_api_key():
        st.caption(
            "⚠️ No API key found. "
            "The assistant won't be able to respond yet."
        )


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

render_header()

# Show a document when the user clicks "View" in the sidebar.
if st.session_state.viewing_document_name:
    render_document_viewer(st.session_state.current_chat_id)
    st.stop()

# Documents are displayed on the individual user messages that reference
# them, ChatGPT-style. There is intentionally no global attachment strip here.


# ---------------------------------------------------------------------------
# Existing chat history
# ---------------------------------------------------------------------------

for msg in st.session_state.chat_history:
    render_bubble(
        msg["role"],
        msg["content"],
        msg.get("sources"),
        msg.get("attachments"),
    )


# ---------------------------------------------------------------------------
# Handle question
# ---------------------------------------------------------------------------

def handle_question(
    q: str,
    document_names: list[str] | None = None,
) -> None:
    q = q.strip()

    if not q:
        return

    # Always reconcile the in-memory document index with the documents saved
    # for this chat. This matters when files were attached in separate chat
    # submissions: the database is the source of truth, so a second upload
    # can never be silently omitted from a later question.
    current_dm = st.session_state.dm

    if st.session_state.current_chat_id:
        stored_documents = _cached_list_chat_documents(st.session_state.current_chat_id, st.session_state.user_id)
        stored_names = {d.filename for d in stored_documents}
        loaded_names = set(current_dm.documents.keys())

        if stored_names != loaded_names:
            previous_focus = current_dm.active_document
            load_chat_documents(st.session_state.current_chat_id)
            current_dm = st.session_state.dm

            if previous_focus in current_dm.documents:
                current_dm.active_document = previous_focus

    # Use the reconciled manager from this point onward.
    dm = current_dm

    if not dm.has_api_key():
        answer = (
            "This assistant isn't connected yet — "
            "an API key needs to be added before "
            "I can respond."
        )
        sources = []

    else:
        with st.spinner("Thinking…"):
            api_history = [
                {
                    "role": m["role"],
                    "content": m["content"],
                }
                for m in st.session_state.chat_history
            ]

            try:
                answer, sources = dm.ask_with_sources(
                    q,
                    history=api_history,
                    document_names=document_names,
                )

            except RuntimeError as e:
                answer = str(e)
                sources = []

            except Exception as e:
                answer = (
                    "Something went wrong calling "
                    f"the model: {e}"
                )
                sources = []

    # Use the documents that actually supplied retrieved context for this
    # question. This makes the attachment shown on the user bubble precise:
    # a later-uploaded document will not retroactively appear on old messages.
    attachment_names = []
    source_data = []
    seen = set()

    for source in sources:
        if isinstance(source, dict):
            doc_name = source.get("doc_name")
            page = source.get("page")
        else:
            doc_name = getattr(source, "doc_name", None)
            page = getattr(source, "page", None)

        if doc_name and doc_name not in attachment_names:
            attachment_names.append(doc_name)

        item = {
            "doc_name": doc_name,
            "page": page,
        }

        key = (
            item["doc_name"],
            item["page"],
        )

        if key not in seen:
            seen.add(key)
            source_data.append(item)

    user_message = {
        "role": "user",
        "content": q,
    }

    if attachment_names:
        user_message["attachments"] = attachment_names

    st.session_state.chat_history.append(user_message)

    st.session_state.chat_history.append(
        {
            "role": "assistant",
            "content": answer,
            "sources": source_data,
        }
    )

    # Render after the response is known so the user's bubble can contain the
    # exact files used for that question. The following rerun then renders the
    # same attachment from persisted chat history.
    render_bubble(
        "user",
        q,
        attachments=attachment_names,
    )

    render_bubble(
        "assistant",
        answer,
        source_data,
    )

    st.session_state.current_chat_id = accounts.save_chat(
        st.session_state.user_id,
        st.session_state.chat_history,
        chat_id=st.session_state.current_chat_id,
    )

    st.rerun()


# ---------------------------------------------------------------------------
# Quick-start interface
# ---------------------------------------------------------------------------

if not st.session_state.chat_history:

    if dm.documents:
        st.markdown(
            '<div class="fw-question-label">'
            'Start with a question about your documents'
            '</div>',
            unsafe_allow_html=True,
        )

        suggestions = [
            "Summarize this document",
            "What are the key points?",
            "Any important numbers or dates?",
        ]

        suggestion_cols = st.columns(3)
        clicked_suggestion = None

        for col, suggestion in zip(
            suggestion_cols,
            suggestions,
        ):
            with col:
                if st.button(
                    suggestion,
                    key=f"suggest_{suggestion}",
                    use_container_width=True,
                ):
                    clicked_suggestion = suggestion

        if clicked_suggestion:
            handle_question(clicked_suggestion)

    else:
        st.markdown(
            '<div class="fw-question-label">'
            'Attach one or more documents below to get started'
            '</div>',
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Chat input with native multi-file attachments
# ---------------------------------------------------------------------------

submission = st.chat_input(
    "Ask anything about your documents...",
    accept_file="multiple",
    file_type=SUPPORTED_FILE_TYPES,
    key="chat_input",
)

if submission:
    submitted_files = list(
        getattr(submission, "files", []) or []
    )
    question = (
        getattr(submission, "text", "") or ""
    ).strip()
    loaded_names = []
    upload_note = question.lower().strip().replace("’", "'")
    upload_only_phrases = {
        "here's the second",
        "here is the second",
        "here's the file",
        "here is the file",
        "here's the document",
        "here is the document",
        "uploaded",
        "uploaded it",
        "there it is",
    }

    if submitted_files:
        chat_id = ensure_current_chat()

        loaded_names = []

        with st.spinner(
            f"Reading {len(submitted_files)} "
            f"document{'s' if len(submitted_files) != 1 else ''}…"
        ):
            for uploaded_file in submitted_files:
                if ingest_uploaded_file(uploaded_file, chat_id):
                    loaded_names.append(uploaded_file.name)

        if loaded_names:
            # A newly uploaded file should never remain trapped inside an
            # earlier single-document focus. The next question should be
            # allowed to search the complete set of files in this chat.
            st.session_state.dm.clear_document_scope()

            # If the user only attached a file and wrote a short note such
            # as "here's the second", don't send that note to the LLM as if
            # it were a document question. Just record the upload and wait
            # for the actual question.
            if upload_note in upload_only_phrases:
                user_message = {
                    "role": "user",
                    "content": question,
                    "attachments": loaded_names,
                }
                st.session_state.chat_history.append(user_message)
                st.session_state.current_chat_id = accounts.save_chat(
                    st.session_state.user_id,
                    st.session_state.chat_history,
                    chat_id=st.session_state.current_chat_id,
                )
                st.rerun()

        if loaded_names and not question:
            st.rerun()

    if question and not (
        submitted_files
        and question.lower().strip().replace("’", "'")
        in upload_only_phrases
    ):
        handle_question(
            question,
            document_names=loaded_names or None,
        )