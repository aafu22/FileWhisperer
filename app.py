"""FileWhisperer — Streamlit UI.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import html
import logging
import os
import re
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path

import streamlit as st
import extra_streamlit_components as stx

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

/*
   CookieManager receives browser cookies asynchronously. On a refresh the
   first Streamlit render can therefore briefly think the user is logged out
   before CookieManager triggers the rerun that restores the session.

   Delay only the *visual* reveal of the login card. This leaves the working
   authentication/session code untouched, but prevents the login form from
   flashing for users whose remembered session is about to be restored.
*/
@keyframes fwAuthReveal {
    from { opacity: 0; visibility: hidden; }
    to   { opacity: 1; visibility: visible; }
}

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

/* Compact mobile chat actions. Desktop keeps the inline edit/delete icons. */
div[class*="st-key-chatmobilemenu_"],
div[class*="st-key-chatmobileactions_"] {
    display: none;
}

div[class*="st-key-chatmobilemenu_"] .stButton button {
    border-color: transparent;
    background: transparent;
    padding: 0.15rem 0.2rem;
    min-width: 2rem;
    font-size: 1.35rem;
    line-height: 1;
}

div[class*="st-key-chatmobilemenu_"] .stButton button:hover {
    background: var(--surface);
    border-color: var(--border);
}

div[class*="st-key-chatmobileactions_"] {
    margin: -0.15rem 0 0.35rem 0;
    padding: 0.35rem 0.4rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface);
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

    /* Main content */
    [data-testid="stMainBlockContainer"] {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }

    /* Mobile sidebar */
    [data-testid="stSidebar"] {
        width: min(88vw, 360px) !important;
    }

    [data-testid="stSidebar"] > div:first-child {
        padding-left: 0.75rem;
        padding-right: 0.75rem;
    }

    /* Sidebar cards */
    div[class*="st-key-panel_"] {
        padding: 0.7rem 0.75rem 0.55rem 0.75rem;
        margin-bottom: 0.7rem;
        border-radius: 10px;
    }

    /* Header */
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

    /* Quick start */
    .fw-question-label {
        font-size: 0.9rem;
        margin-top: 1.5rem;
        margin-bottom: 0.75rem;
    }

    /* Touch-friendly buttons */
    .stButton button {
        min-height: 44px !important;
        font-size: 0.92rem;
    }

    /* On mobile, replace the separate edit/delete icons with one menu. */
    div[class*="st-key-chatedit_"],
    div[class*="st-key-chatdel_"] {
        display: none !important;
    }

    div[class*="st-key-chatmobilemenu_"] {
        display: block !important;
        opacity: 1 !important;
    }

    div[class*="st-key-chatmobileactions_"] {
        display: block;
    }

    div[class*="st-key-chatmobileactions_"] .stButton button {
        min-height: 40px !important;
        font-size: 0.9rem;
    }

    /* Quick-start buttons */
    div[class*="st-key-suggest_"] button {
        min-height: 46px !important;
    }

    /* Chat */
    .dm-bubble {
        max-width: 94%;
        padding: 0.55rem 0.75rem;
        font-size: 0.92rem;
    }

    .dm-sources {
        max-width: 94%;
    }

    /* Chat input */
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

    /* File uploader */
    [data-testid="stFileUploaderDropzone"] {
        padding: 0.65rem !important;
    }

    /* Sidebar sample button */
    div[class*="st-key-sample_report_button"] button {
        min-height: 46px !important;
    }
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
accounts.cleanup_expired_tokens()

SIGNUP_CODE = os.environ.get(
    "FILEWHISPERER_SIGNUP_CODE",
    os.environ.get("DOCUMIND_SIGNUP_CODE", ""),
).strip()

REMEMBER_COOKIE_NAME = "filewhisperer_remember"
REMEMBER_ME_SECONDS = 30 * 24 * 60 * 60

COOKIE_SECURE = os.environ.get(
    "FILEWHISPERER_COOKIE_SECURE",
    os.environ.get("DOCUMIND_COOKIE_SECURE", "false"),
).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def get_cookie_manager():
    """Return one persistent CookieManager instance for the app."""
    return stx.CookieManager(key="filewhisperer_cookie_manager")


cookie_manager = get_cookie_manager()

def queue_remember_cookie(token: str) -> None:
    """Queue the remember-me cookie to be written on the NEXT script run.

    Calling cookie_manager.set() and then st.rerun() in the same run means
    the component is torn down before the browser executes it, so the
    cookie never gets written. Queueing lets the next run render the
    component and leave it alone long enough to do its job.
    """
    st.session_state["_pending_cookie_set"] = token


def queue_delete_remember_cookie() -> None:
    """Queue removal of the remember-me cookie for the next script run."""
    st.session_state["_pending_cookie_delete"] = True


def flush_pending_cookie_ops() -> None:
    """Render the cookie component(s) for any queued set/delete."""
    token = st.session_state.pop("_pending_cookie_set", None)
    if token:
        cookie_manager.set(
            cookie=REMEMBER_COOKIE_NAME,
            val=token,
            key="remember_cookie_set",
            path="/",
            max_age=REMEMBER_ME_SECONDS,
            secure=COOKIE_SECURE,
            same_site="lax",
        )

    if st.session_state.pop("_pending_cookie_delete", False):
        cookie_manager.delete(
            cookie=REMEMBER_COOKIE_NAME,
            key="remember_cookie_delete",
        )


# ---------------------------------------------------------------------------
# Authentication state
# ---------------------------------------------------------------------------

if "user_id" not in st.session_state:
    st.session_state.user_id = None

if "username" not in st.session_state:
    st.session_state.username = None


flush_pending_cookie_ops()


# ---------------------------------------------------------------------------
# Restore Remember Me session
# ---------------------------------------------------------------------------

if st.session_state.user_id is None:

    try:
        # Read the cookie synchronously from the request that loaded this page.
        # CookieManager is still used for setting/deleting the cookie, but using
        # it here would require an asynchronous component round-trip and causes
        # the login form to flash briefly during refresh.
        remember_token = None
        if hasattr(st, "context"):
            remember_token = st.context.cookies.get(
                REMEMBER_COOKIE_NAME
            )

        if remember_token:
            session = accounts.authenticate_remember_token(
                remember_token
            )

            if session:
                (
                    st.session_state.user_id,
                    st.session_state.username,
                ) = session

    except Exception:
        logging.getLogger(__name__).exception(
            "Remember-me restore failed"
        )


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

                                queue_remember_cookie(token)

                            st.rerun()

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

                                queue_remember_cookie(token)

                                st.rerun()

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
    scope: list | None = None,
) -> None:

    css_role = (
        "user"
        if role == "user"
        else "assistant"
    )

    st.markdown(
        f'<div class="dm-row {css_role}">'
        f'<div class="dm-bubble {css_role}">'
        f'{content}'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if scope and css_role == "user":

        scope_chips = "".join(
            f'<span class="dm-source">📄 {html.escape(name)}</span>'
            for name in scope
        )

        st.markdown(
            '<div class="dm-sources">'
            '<strong>Asked about</strong> &nbsp;'
            + scope_chips
            + "</div>",
            unsafe_allow_html=True,
        )

    if sources and css_role == "assistant":

        def field(
            source,
            name,
            default=None,
        ):

            if isinstance(
                source,
                dict,
            ):

                return source.get(
                    name,
                    default,
                )

            return getattr(
                source,
                name,
                default,
            )

        unique = []
        seen = set()

        for source in sources:

            key = (
                field(
                    source,
                    "doc_name",
                    "",
                ),
                field(
                    source,
                    "page",
                ),
            )

            if key not in seen:

                seen.add(key)
                unique.append(source)

        chips = []

        for source in unique:

            doc_name = html.escape(
                field(
                    source,
                    "doc_name",
                    "Document",
                )
            )

            page = field(
                source,
                "page",
            )

            page_text = (
                f" · {html.escape(str(page))}"
                if page
                else ""
            )

            chips.append(
                f'<span class="dm-source">'
                f'📄 {doc_name}{page_text}'
                f'</span>'
            )

        st.markdown(
            '<div class="dm-sources">'
            '<strong>Sources</strong> &nbsp;'
            + "".join(chips)
            + "</div>",
            unsafe_allow_html=True,
        )


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

if "chat_menu_id" not in st.session_state:
    st.session_state.chat_menu_id = None

if "processed_files" not in st.session_state:
    st.session_state.processed_files = set()

if "doc_blobs" not in st.session_state:
    # name -> raw bytes of every document in the current chat, so they can
    # be saved with the chat and restored later.
    st.session_state.doc_blobs = {}


dm: FileWhisperer = st.session_state.dm


# ---------------------------------------------------------------------------
# Uploaded documents
# ---------------------------------------------------------------------------

# Per-chat document storage -------------------------------------------------

DOCS_DB_PATH = os.environ.get("FILEWHISPERER_DOCS_DB", "filewhisperer_docs.db")

# Adds a short note to each question telling the model which documents are
# loaded, so vague questions ("what's this about?") aren't answered from
# earlier replies. Set to False to send questions unchanged.
GUARD_QUESTIONS = True


def _docs_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DOCS_DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS chat_documents ("
        "user_id TEXT NOT NULL, chat_id TEXT NOT NULL, "
        "name TEXT NOT NULL, data BLOB NOT NULL, "
        "PRIMARY KEY (user_id, chat_id, name))"
    )
    return conn


def save_chat_documents(user_id, chat_id, blobs: dict[str, bytes]) -> None:
    with closing(_docs_conn()) as conn, conn:
        conn.execute(
            "DELETE FROM chat_documents WHERE user_id = ? AND chat_id = ?",
            (str(user_id), str(chat_id)),
        )
        conn.executemany(
            "INSERT INTO chat_documents (user_id, chat_id, name, data) "
            "VALUES (?, ?, ?, ?)",
            [(str(user_id), str(chat_id), n, d) for n, d in blobs.items()],
        )


def load_chat_documents(user_id, chat_id) -> dict[str, bytes]:
    with closing(_docs_conn()) as conn:
        rows = conn.execute(
            "SELECT name, data FROM chat_documents "
            "WHERE user_id = ? AND chat_id = ? ORDER BY rowid",
            (str(user_id), str(chat_id)),
        ).fetchall()
    return {name: bytes(data) for name, data in rows}


def delete_chat_documents(user_id, chat_id) -> None:
    with closing(_docs_conn()) as conn, conn:
        conn.execute(
            "DELETE FROM chat_documents WHERE user_id = ? AND chat_id = ?",
            (str(user_id), str(chat_id)),
        )


def persist_current_documents() -> None:
    """Save the current documents against the current chat (if it has an id)."""
    chat_id = st.session_state.current_chat_id
    if chat_id is None:
        return
    save_chat_documents(
        st.session_state.user_id,
        chat_id,
        dict(st.session_state.doc_blobs),
    )


def _add_bytes(target: FileWhisperer, name: str, data: bytes) -> None:
    """Write `data` to a temp file and register it with `target`."""
    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=Path(name).suffix,
    ) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        target.add_document(tmp_path, display_name=name)
    finally:
        for _ in range(3):
            try:
                Path(tmp_path).unlink(missing_ok=True)
                break
            except PermissionError:
                time.sleep(0.2)


def restore_chat_documents(chat_id) -> None:
    """Load a chat's saved documents into a fresh FileWhisperer."""
    blobs = load_chat_documents(st.session_state.user_id, chat_id)

    if not blobs:
        # Nothing stored (e.g. a chat from before documents were saved):
        # keep whatever is currently loaded.
        return

    fresh = FileWhisperer()
    restored: dict[str, bytes] = {}
    ok_keys = set()

    for name, data in blobs.items():
        restored[name] = data
        try:
            _add_bytes(fresh, name, data)
            ok_keys.add((name, len(data)))
        except Exception:
            logging.getLogger(__name__).exception(
                "Couldn't restore document %s", name
            )

    st.session_state.dm = fresh
    st.session_state.doc_blobs = restored
    st.session_state.processed_files = ok_keys


def current_doc_scope() -> list[str]:
    """Which loaded document names the next question should be restricted to.

    Empty list (the default) means "all documents". Names no longer loaded
    are dropped automatically.
    """
    all_names = list(dm.documents.keys())
    scope = [
        n for n in st.session_state.get("doc_scope", [])
        if n in all_names
    ]
    st.session_state.doc_scope = scope
    return scope


# Short acknowledgments that don't need a document lookup at all — just
# ordinary conversational replies. Keeping this list small and literal
# avoids misfiring on real (if short) questions like "ok but why?" or
# "cool, what about Hindi?".
_SMALL_TALK = {
    "ok", "okay", "kk", "k", "alright", "cool", "nice", "great", "perfect",
    "awesome", "sure", "got it", "gotcha", "noted", "fine", "fair enough",
    "thanks", "thank you", "thank u", "thanku", "thx", "ty",
    "okay thanks", "okay thank you", "okay thank u", "ok thanks",
    "ok thank you", "ok thank u", "thanks a lot", "thank you so much",
    "appreciate it", "appreciated", "np", "no problem", "you're welcome",
    "youre welcome", "welcome", "bye", "goodbye", "see ya", "see you",
    "good morning", "good afternoon", "good evening", "good night",
    "hi", "hello", "hey", "yo",
}


def is_small_talk(q: str) -> bool:
    """True for short pleasantries that shouldn't trigger document lookup."""
    normalized = re.sub(r"[^a-z0-9\s]", "", q.strip().lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)

    if not normalized:
        return False

    if normalized in _SMALL_TALK:
        return True

    # A short run of only small-talk words ("okay", "thank", "u", "so",
    # "much") with nothing else — catches minor variants without matching
    # every message that happens to contain "thanks".
    words = normalized.split()

    filler = {
        "ok", "okay", "thanks", "thank", "you", "u", "so", "very", "much",
        "a", "lot", "cool", "nice", "great", "awesome", "perfect", "yep",
        "yeah", "yes",
    }

    return len(words) <= 5 and all(w in filler for w in words)


def build_model_question(q: str) -> str:
    """Tell the model which documents to use, without changing what is saved."""
    if not GUARD_QUESTIONS or not dm.documents:
        return q

    scope = current_doc_scope()
    all_names = list(dm.documents.keys())

    if scope and set(scope) != set(all_names):
        # Restricted to a subset of the loaded documents.
        names = ", ".join(scope)
        others = ", ".join(n for n in all_names if n not in scope)

        return (
            f"{q}\n\n"
            f"(Answer using ONLY this document: {names}. Other documents "
            f"are loaded ({others}) but are OUT OF SCOPE for this "
            "question — ignore their content, and ignore any earlier "
            "reply in this conversation that drew on them. If this "
            "document doesn't contain the answer, say so instead of "
            "using the other documents.)"
        )

    names = ", ".join(all_names)

    return (
        f"{q}\n\n"
        f"(Documents currently loaded: {names}. Answer from these "
        "documents. If the question is general, cover every loaded "
        "document. If earlier replies in this conversation conflict with "
        "the loaded documents, trust the documents.)"
    )


# Uploads -------------------------------------------------------------------

def add_uploaded_file(
    uploaded_file,
) -> None:

    data = uploaded_file.getvalue()

    key = (
        uploaded_file.name,
        len(data),
    )

    if key in st.session_state.processed_files:
        return

    try:

        _add_bytes(dm, uploaded_file.name, data)

        st.session_state.processed_files.add(key)

        st.session_state.doc_blobs[uploaded_file.name] = data

        persist_current_documents()

    except UnsupportedFileType as e:

        st.sidebar.warning(
            str(e)
        )

    except EmptyDocument as e:

        st.sidebar.warning(
            str(e)
        )

    except Exception as e:

        st.sidebar.error(
            f'Couldn\'t read "{uploaded_file.name}": {e}'
        )


# ---------------------------------------------------------------------------
# Sample quarterly report
# ---------------------------------------------------------------------------

def load_sample_report() -> None:
    """Load the bundled sample quarterly report."""

    sample_dir = Path(
        "sample_documents"
    )

    if not sample_dir.exists():

        st.sidebar.error(
            "Sample document folder not found."
        )

        return

    preferred_sample = (
        sample_dir
        / "Sample_Quarterly_Report.md"
    )

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
            if (
                file.is_file()
                and file.suffix.lower()
                in supported_extensions
            )
        )

        if not sample_files:

            st.sidebar.error(
                "No sample document found "
                "in sample_documents."
            )

            return

        sample_path = sample_files[0]

    key = (
        sample_path.name,
        sample_path.stat().st_size,
    )

    if key in st.session_state.processed_files:

        return

    try:

        with st.spinner(
            "Loading sample quarterly report…"
        ):

            dm.add_document(
                str(sample_path),
                display_name=sample_path.name,
            )

            st.session_state.doc_blobs[sample_path.name] = (
                sample_path.read_bytes()
            )

            st.session_state.processed_files.add(
                key
            )

        st.session_state.chat_history = []

        st.session_state.current_chat_id = None

        st.rerun()

    except Exception as e:

        st.sidebar.error(
            f"Couldn't load sample report: {e}"
        )


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_size(
    num_bytes: int,
) -> str:

    if num_bytes < 1024:

        return f"{num_bytes} B"

    if num_bytes < 1024 * 1024:

        return (
            f"{num_bytes / 1024:.1f} KB"
        )

    return (
        f"{num_bytes / (1024 * 1024):.1f} MB"
    )


# ---------------------------------------------------------------------------
# Documents section
# ---------------------------------------------------------------------------

def render_documents_section(
    key_prefix: str,
    show_heading: bool = True,
    show_uploader: bool = True,
) -> None:

    if show_heading:

        st.markdown(
            "### Documents"
        )

        st.caption(
            "Add files to ask questions grounded in them."
        )

    if show_uploader:
        st.markdown(
            '<div class="dm-upload-label">'
            'Add documents'
            '</div>',
            unsafe_allow_html=True,
        )

        uploaded_files = st.file_uploader(
            "Add documents",
            type=[
                "txt",
                "md",
                "csv",
                "json",
                "log",
                "pdf",
                "docx",
                "xlsx",
            ],
            accept_multiple_files=True,
            key=f"{key_prefix}_uploader",
            label_visibility="collapsed",
        )

        if uploaded_files:

            for f in uploaded_files:

                if (
                    f.name,
                    f.size,
                ) in st.session_state.processed_files:

                    continue

                with st.spinner(
                    f'Reading "{f.name}"… '
                    "(scanned PDFs can take a bit longer)"
                ):

                    add_uploaded_file(f)


    if dm.documents:

        for name, doc_size in [
            (
                n,
                len(d.text),
            )
            for n, d in dm.documents.items()
        ]:

            safe_name = html.escape(
                name
            )

            suffix = (
                Path(name)
                .suffix
                .replace(".", "")
                .upper()
                or "FILE"
            )

            with st.container(
                key=f"docrow_{key_prefix}_{name}"
            ):

                card_col, btn_col = st.columns(
                    [5, 1]
                )

                with card_col:

                    # IMPORTANT:
                    # This is intentionally kept as one continuous
                    # HTML string so Streamlit doesn't interpret
                    # indentation as a Markdown code block.

                    st.markdown(
                        f'<div class="dm-doc-card">'
                        f'<span class="glyph">📄</span>'
                        f'<div class="meta">'
                        f'<div class="fname">{safe_name}</div>'
                        f'<div class="fsize">'
                        f'{suffix} · '
                        f'{format_size(doc_size)} '
                        f'of text'
                        f'</div>'
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                with btn_col:

                    with st.container(
                        key=(
                            f"docactions_"
                            f"{key_prefix}_"
                            f"{name}"
                        )
                    ):

                        if st.button(
                            "🗑",
                            key=(
                                f"{key_prefix}"
                                f"_remove_"
                                f"{name}"
                            ),
                            help="Remove document",
                        ):

                            dm.remove_document(
                                name
                            )

                            removed = st.session_state.doc_blobs.pop(
                                name,
                                None,
                            )

                            if removed is not None:
                                st.session_state.processed_files.discard(
                                    (name, len(removed))
                                )

                            persist_current_documents()

                            st.rerun()

    else:

        st.caption(
            "No documents yet."
        )


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:

    # Account
    with st.container(
        key="panel_profile"
    ):

        st.markdown(
            f"**👤 "
            f"{html.escape(st.session_state.username)}"
            f"**"
        )

        with st.popover(
            "Account & settings",
            use_container_width=True,
        ):

            st.caption(
                "Signed in as"
            )

            st.markdown(
                f"**"
                f"{html.escape(st.session_state.username)}"
                f"**"
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

                remember_token = st.context.cookies.get(
                    REMEMBER_COOKIE_NAME
                )

                if remember_token:
                    accounts.revoke_remember_token(
                        remember_token
                    )

                queue_delete_remember_cookie()

                st.session_state.user_id = None
                st.session_state.username = None
                st.session_state.chat_history = []
                st.session_state.current_chat_id = None
                st.session_state.processed_files = set()
                st.session_state.doc_blobs = {}
                st.session_state.dm = FileWhisperer()

                st.rerun()

    # Documents
    with st.container(
        key="panel_documents"
    ):

        render_documents_section(
            "sidebar",
            show_uploader=False,
        )

        st.markdown("---")

        # Separate keyed container lets us style only this button.
        with st.container(
            key="sample_report_button"
        ):

            if st.button(
                "Try sample quarterly report",
                use_container_width=True,
                key="sample_report",
            ):

                load_sample_report()

    # Chats
    with st.container(
        key="panel_chats"
    ):

        if st.button(
            "+ New chat",
            use_container_width=True,
        ):

            st.session_state.chat_history = []
            st.session_state.current_chat_id = None

            st.rerun()

        saved_chats = accounts.list_chats(
            st.session_state.user_id
        )

        if saved_chats:

            st.markdown(
                "### Chats"
            )

            for c in saved_chats:

                if (
                    st.session_state.renaming_chat_id
                    == c.id
                ):

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

                    with st.container(
                        key=f"chatrow_{c.id}"
                    ):

                        name_col, edit_col, del_col = (
                            st.columns(
                                [5, 1, 1],
                                vertical_alignment="center",
                            )
                        )

                        with name_col:

                            with st.container(
                                key=f"chatopen_{c.id}"
                            ):

                                label = (
                                    c.name
                                    + (
                                        " •"
                                        if (
                                            c.id
                                            == st.session_state.current_chat_id
                                        )
                                        else ""
                                    )
                                )

                                if st.button(
                                    label,
                                    key=f"open_{c.id}",
                                    use_container_width=True,
                                    help="Open this chat",
                                ):

                                    loaded = (
                                        accounts.load_chat(
                                            c.id,
                                            st.session_state.user_id,
                                        )
                                    )

                                    if loaded is not None:

                                        st.session_state.chat_history = (
                                            loaded.messages
                                        )

                                        st.session_state.current_chat_id = (
                                            loaded.id
                                        )

                                        with st.spinner(
                                            "Restoring documents…"
                                        ):
                                            restore_chat_documents(
                                                loaded.id
                                            )

                                        st.rerun()

                        with edit_col:

                            with st.container(
                                key=f"chatedit_{c.id}"
                            ):

                                if st.button(
                                    "✎",
                                    key=f"edit_{c.id}",
                                    help="Rename",
                                ):

                                    st.session_state.renaming_chat_id = (
                                        c.id
                                    )

                                    st.rerun()

                        with del_col:

                            with st.container(
                                key=f"chatdel_{c.id}"
                            ):

                                if st.button(
                                    "🗑",
                                    key=f"del_{c.id}",
                                    help="Delete",
                                ):

                                    accounts.delete_chat(
                                        c.id,
                                        st.session_state.user_id,
                                    )

                                    delete_chat_documents(
                                        st.session_state.user_id,
                                        c.id,
                                    )

                                    if (
                                        st.session_state.current_chat_id
                                        == c.id
                                    ):

                                        st.session_state.current_chat_id = (
                                            None
                                        )

                                    st.rerun()

                            with st.container(
                                key=f"chatmobilemenu_{c.id}"
                            ):
                                if st.button(
                                    "⋮",
                                    key=f"mobile_menu_{c.id}",
                                    help="Chat actions",
                                ):
                                    st.session_state.chat_menu_id = (
                                        None
                                        if st.session_state.chat_menu_id == c.id
                                        else c.id
                                    )
                                    st.rerun()

                        if st.session_state.chat_menu_id == c.id:
                            with st.container(
                                key=f"chatmobileactions_{c.id}"
                            ):
                                mobile_rename_col, mobile_delete_col = st.columns(2)

                                with mobile_rename_col:
                                    if st.button(
                                        "Rename",
                                        key=f"mobile_rename_{c.id}",
                                        use_container_width=True,
                                    ):
                                        st.session_state.chat_menu_id = None
                                        st.session_state.renaming_chat_id = c.id
                                        st.rerun()

                                with mobile_delete_col:
                                    if st.button(
                                        "Delete",
                                        key=f"mobile_delete_{c.id}",
                                        use_container_width=True,
                                    ):
                                        accounts.delete_chat(
                                            c.id,
                                            st.session_state.user_id,
                                        )
                                        delete_chat_documents(
                                            st.session_state.user_id,
                                            c.id,
                                        )

                                        if (
                                            st.session_state.current_chat_id
                                            == c.id
                                        ):
                                            st.session_state.current_chat_id = None
                                            st.session_state.chat_history = []
                                            restore_document_manager()

                                        st.session_state.chat_menu_id = None
                                        st.rerun()

    # API status
    if not dm.has_api_key():

        st.caption(
            "⚠️ No API key found. "
            "The assistant won't be able to respond yet."
        )


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

render_header()


# ---------------------------------------------------------------------------
# Existing chat history
# ---------------------------------------------------------------------------

for msg in st.session_state.chat_history:

    render_bubble(
        msg["role"],
        msg["content"],
        msg.get("sources"),
        msg.get("scope"),
    )


# ---------------------------------------------------------------------------
# Handle question
# ---------------------------------------------------------------------------

def handle_question(
    q: str,
) -> None:

    # Captured once up front so the scope used for this question is fixed
    # even if the "Ask about" picker changes before the run finishes.
    scope = current_doc_scope()

    render_bubble(
        "user",
        q,
        scope=scope,
    )

    if is_small_talk(q):

        # Skip retrieval entirely — re-deriving document content for
        # "okay thank u" is exactly the noisy, over-long reply this is
        # meant to avoid.
        answer = "You're welcome! Let me know if you have more questions."
        sources = []

    elif not dm.has_api_key():

        answer = (
            "This assistant isn't connected yet — "
            "an API key needs to be added before "
            "I can respond."
        )

        sources = []

    else:

        with st.spinner(
            "Thinking…"
        ):

            api_history = [
                {
                    "role": m["role"],
                    "content": m["content"],
                }
                for m in st.session_state.chat_history
            ]

            try:

                answer, sources = (
                    dm.ask_with_sources(
                        build_model_question(q),
                        history=api_history,
                    )
                )

                if scope:
                    # ask_with_sources retrieves across every loaded
                    # document; keep only the sources that were actually
                    # in scope for this question so the chips shown match
                    # what the answer was restricted to.
                    sources = [
                        s for s in sources
                        if getattr(s, "doc_name", None) in scope
                    ]

            except RuntimeError as e:

                answer = str(e)
                sources = []

            except Exception as e:

                answer = (
                    "Something went wrong calling "
                    f"the model: {e}"
                )

                sources = []

    render_bubble(
        "assistant",
        answer,
        sources,
    )

    source_data = []

    seen = set()

    for source in sources:

        item = {
            "doc_name": source.doc_name,
            "page": source.page,
        }

        key = (
            item["doc_name"],
            item["page"],
        )

        if key not in seen:

            seen.add(key)

            source_data.append(
                item
            )

    st.session_state.chat_history.append(
        {
            "role": "user",
            "content": q,
            "scope": scope,
        }
    )

    st.session_state.chat_history.append(
        {
            "role": "assistant",
            "content": answer,
            "sources": source_data,
        }
    )

    st.session_state.current_chat_id = (
        accounts.save_chat(
            st.session_state.user_id,
            st.session_state.chat_history,
            chat_id=st.session_state.current_chat_id,
        )
    )

    persist_current_documents()

    st.rerun()


# ---------------------------------------------------------------------------
# Quick-start interface
# ---------------------------------------------------------------------------

if not st.session_state.chat_history:

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

        handle_question(
            clicked_suggestion
        )


# ---------------------------------------------------------------------------
# Document scope
# ---------------------------------------------------------------------------

if len(dm.documents) > 1:

    doc_names = list(dm.documents.keys())

    if "doc_scope" not in st.session_state:
        st.session_state.doc_scope = []

    picked = st.multiselect(
        "Ask about",
        options=doc_names,
        default=current_doc_scope(),
        placeholder="All documents",
        key="doc_scope_picker",
        help=(
            "Leave empty to ask across every loaded document. "
            "Pick one or more to restrict the answer to just those."
        ),
    )

    st.session_state.doc_scope = picked


# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------

chat_submission = st.chat_input(
    "Ask anything about your documents...",
    accept_file="multiple",
    file_type=[
        "txt", "md", "csv", "json", "log",
        "pdf", "docx", "xlsx",
    ],
)

if chat_submission:
    attached_files = list(chat_submission.files or [])

    for f in attached_files:
        if (f.name, f.size) in st.session_state.processed_files:
            continue

        with st.spinner(
            f'Reading "{f.name}"… '
            "(scanned PDFs can take a bit longer)"
        ):
            add_uploaded_file(f)

    question = (chat_submission.text or "").strip()

    if question:
        handle_question(question)
    elif attached_files:
        st.rerun()