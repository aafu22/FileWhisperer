# FileWhisperer

A small Python, AI-powered document Q&A assistant. Add your own documents,
ask questions, and get answers grounded in what's actually in them — powered
by a **free** model on [OpenRouter](https://openrouter.ai), no paid API key
required.

📄 See [CASE_STUDY.md](CASE_STUDY.md) for a write-up of the architecture,
engineering decisions, and specific bugs this project's design solves.

## How it works

1. **Load** — `.txt`, `.md`, `.csv`, `.json`, `.pdf`, `.docx`, and `.xlsx`
   files are read into a list of pages (a PDF page, a spreadsheet sheet, or
   the whole file for formats with no page concept) — see "Advanced
   features" below for what each format gets beyond plain text.
2. **Chunk** — each page is split into overlapping ~1400-character pieces
   so retrieval can be precise, without ever letting a chunk span two
   pages — keeping a chunk from spanning two pages keeps retrieval more
   precise.
3. **Retrieve** — for each question, a lightweight TF-IDF ranker (pure
   Python, no embedding API needed) picks the most relevant chunks across
   all loaded documents (`filewhisperer/retriever.py`).
4. **Answer** — those chunks are handed to a free LLM on OpenRouter, with
   instructions to answer only from what's given and to name its sources
   (`filewhisperer/assistant.py`). The Streamlit app also shows which chunks
   were used in a "Sources" expander under each answer.

This is retrieval-augmented generation (RAG) in miniature: enough structure
to stay accurate on documents too large to fit in one prompt, without
pulling in a vector database.

## Setup

```bash
pip install -r requirements.txt
```

**Add your API key once, and FileWhisperer will remember it every time you run
it:**

1. Get a free key at [openrouter.ai/keys](https://openrouter.ai/keys) (no
   credit card needed).
2. Copy `.env.example` to a new file named `.env` in the project root.
3. Open `.env` and paste your key in place of `sk-or-your-key-here`.

That's it - `.env` is loaded automatically, and it's already listed in
`.gitignore` so it won't accidentally get committed if you put this project
under version control.

(If you'd rather not use a `.env` file, you can instead set
`OPENROUTER_API_KEY` as a regular environment variable — see the bottom of
this README for OS-specific commands.)

## Use it as a library

```python
from filewhisperer import FileWhisperer

dm = FileWhisperer()
dm.add_document("quarterly_report.pdf")
dm.add_document("meeting_notes.docx")

print(dm.ask("What were the Q3 revenue numbers?"))
print(dm.ask("Did the meeting notes mention any risks?"))
```

## Use the browser UI (recommended if you don't want the command line)

```bash
streamlit run app.py
```

This is the only command you'll type. It opens FileWhisperer in your browser —
drag files into the sidebar to add them, paste your API key there if it
isn't already in `.env`, and ask questions in a normal chat box. No further
typing into a terminal required.

## Use it from the command line

```bash
python -m filewhisperer.cli
```

```
FileWhisperer — ask questions about your own documents
---------------------------------------------------
/add <path>       add a .txt .md .csv .json .pdf or .docx file
/list             show loaded documents
/remove <name>    drop a document
/quit             exit

> /add quarterly_report.pdf
  added "quarterly_report.pdf" (14 chunk(s))

> What was the biggest driver of Q3 growth?
According to "quarterly_report.pdf", ...
```

## Advanced features

**A sample document loads automatically the first time.** So the app is
never a blank slate — a bundled sample quarterly report
(`sample_documents/Sample_Quarterly_Report.md`) loads once per fresh
session if you haven't added anything of your own yet, with a few
suggested questions shown as one-click buttons. It's a real document like
any other — remove it, add your own, whatever you'd do normally. This
only happens once per session; removing it doesn't bring it back.

**Multi-column PDFs.** A page is checked for a large horizontal gap
between words — the signature of a two-column layout. If found, the left
column is read fully (top to bottom) before the right column, instead of
interleaving lines across both, which is what naive text extraction
usually does. Normal single-column pages are unaffected (the gap check
requires an ~8%-of-page-width gap, well beyond ordinary word spacing).

**Spreadsheets (`.xlsx`).** Every sheet becomes a markdown table. Long
sheets (over 150 rows by default) are automatically split into multiple
row-range "pages" — e.g. "Sales (rows 1-150)", "Sales (rows 151-300)" — so
one huge sheet doesn't become one unmanageably large chunk that's hard for
the model to reason about accurately. Adjust the row-batch size with
`FILEWHISPERER_XLSX_ROWS_PER_PAGE` in `.env` if needed.

**Mixed scanned/digital PDFs.** OCR now runs per-page rather than
all-or-nothing — if only a few pages of an otherwise-digital PDF are
scanned images (e.g. a signed page inserted into a typed contract), only
those pages get OCR'd; the rest use the normal, much faster text
extraction.

## Accounts and chat history

FileWhisperer has real accounts: sign up with a username and password, and your
chat history saves automatically as you go — log back in later (even in a
different browser) and your past chats are there, exactly as you left
them. Nobody else's chats are visible to you, and yours aren't visible to
them.

A few things worth knowing about how this works:

- **Passwords are hashed**, not stored as plain text — using PBKDF2 (part
  of Python's standard library, 260,000 iterations, a random salt per
  user), not a third-party library. Even someone with direct access to the
  database file can't read passwords back out of it.
- **Everything is stored locally** in a single SQLite file at
  `data/documind.db`, created automatically the first time you run the
  app. There's no external database or account provider — the whole
  system is self-contained and already covered by `.gitignore`.
- **Documents are not saved per account** — only chat text is. Re-add
  documents after logging back in for a new session; they live in memory
  for that session only, the same as before accounts existed. Saving raw
  file contents per account would grow the database quickly and duplicate
  files that already exist on your computer.
- **This is deliberately simple**: no email verification, no "forgot
  password" flow, no admin panel. For a small, self-hosted deployment
  where you already know who you're giving access to, that's the right
  amount of system.

### Protecting a public deployment

Two different things are private per account already (chat history)
versus shared across everyone (the API key), and only one of those needs
extra protection:

- Chat history and documents are already isolated — nothing extra needed.
- Your API key is **not** private per account — it lives on the server
  and is used by every account's requests. On a public URL, anyone can
  sign up for a free account and start using your quota. Set
  `FILEWHISPERER_SIGNUP_CODE` in `.env` to require an invite code to create a
  *new* account (existing accounts can still log in without it) — share
  that code only with people you actually want to have access.

## Deploying a live version (Streamlit Community Cloud)

This is the right platform for this specific app, not an arbitrary pick:
it's free, purpose-built for Streamlit, supports a `packages.txt` for
installing Tesseract (already included in this repo), and its Secrets
feature exposes whatever you set as regular environment variables — so the
existing `os.environ`-based code works there with no changes.

1. **Push this project to a public GitHub repo.** From the project folder:
   ```bash
   git init
   git add .
   git commit -m "FileWhisperer"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<repo-name>.git
   git push -u origin main
   ```
   (`.env` and `data/` are already in `.gitignore`, so your key and local
   accounts database won't get pushed.)
2. Go to **[share.streamlit.io](https://share.streamlit.io)** and sign in
   with GitHub.
3. Click **New app**, pick your repo/branch, and set the main file path to
   `app.py`.
4. Click **Advanced settings**, and paste into the **Secrets** box (TOML
   format):
   ```toml
   OPENROUTER_API_KEY = "sk-or-..."
   FILEWHISPERER_SIGNUP_CODE = "choose-something-not-guessable"
   ```
5. Click **Deploy**. First build takes a couple of minutes (it's also
   installing Tesseract via `packages.txt`). You'll get a URL like
   `https://<something>.streamlit.app` — that's your live link.

Two things worth knowing about this specific hosting setup, so nothing here surprises you later:

- **Free-tier apps sleep after inactivity.** The first visitor after a
  quiet period waits ~30-60 seconds while it wakes up. Worth mentioning if
  you're sending someone a link cold (a recruiter, say) so a slow first
  load doesn't look broken.
- **The SQLite accounts database is not guaranteed to survive a redeploy.**
  Community Cloud rebuilds the app's container from your repo each time
  you push new code, and there's no persistent volume by default — so
  accounts/chats created on the live demo can be wiped whenever you
  update it. Fine for a live portfolio demo (visitors can always sign up
  fresh), but not something to rely on for real user data long-term. If
  you outgrow that, swapping the SQLite calls in `filewhisperer/accounts.py`
  for a hosted database (e.g. Supabase, Turso) is the natural next step —
  the rest of the app wouldn't need to change.

## Notes and limitations

- The TF-IDF retriever is keyword-based, not semantic — great for names,
  numbers, and specific terms, weaker on questions phrased very differently
  from the document's own wording. Swap in an embedding-based retriever in
  `retriever.py` if you need that.
- **Free models on OpenRouter rotate in and out with little notice** — you
  may see a `404` error saying a model "is unavailable for free" or "no
  endpoints found." To avoid chasing this, `DEFAULT_MODEL` is set to
  **`openrouter/free`**, OpenRouter's own router that automatically picks
  whichever free model is currently working. This is the safest default and
  what the app uses out of the box.

  If you want a *specific* model instead (for a particular strength, e.g.
  long context or coding), set `OPENROUTER_MODEL` as an environment
  variable or pick one from the sidebar dropdown in the Streamlit app — but
  expect named free models to occasionally stop working and need swapping.
  Check [openrouter.ai/models?max_price=0](https://openrouter.ai/models?max_price=0)
  for the current list:
  ```bash
  export OPENROUTER_MODEL="meta-llama/llama-3.3-70b-instruct:free"
  ```
- Free tiers are rate-limited (requests per minute/day), not unlimited. If
  you hit a 429 error, wait a bit or reduce how many questions you ask in a
  short burst.
- Want to switch to a paid, non-rate-limited option later? OpenRouter also
  hosts Claude, GPT, and Gemini models behind the same API — just change
  `DEFAULT_MODEL` to a paid model ID and add credit to your OpenRouter
  account. No code changes needed.

## Enable OCR for scanned PDFs

`pip install -r requirements.txt` already installs the Python OCR packages
(`pypdfium2`, `pytesseract`, `Pillow`). The one piece pip can't install for
you is the **Tesseract OCR engine itself** — a separate program those
packages call out to. Install it once per machine:

- **Windows:** download and run the installer from the
  [UB-Mannheim Tesseract build](https://github.com/UB-Mannheim/tesseract/wiki)
  (the most common Windows distribution). During install, note the install
  path (usually `C:\Program Files\Tesseract-OCR\tesseract.exe`). If
  FileWhisperer still can't find it afterward, add that folder to your PATH, or
  add these two lines near the top of `filewhisperer/loaders.py`:
  ```python
  import pytesseract
  pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
  ```
- **macOS:** `brew install tesseract`
- **Linux (Debian/Ubuntu):** `sudo apt install tesseract-ocr`

No key or account needed — it's a free, local install. Once it's on your
PATH, scanned PDFs work exactly like any other document: drop one in and
ask questions about it. If Tesseract isn't installed, FileWhisperer will tell
you clearly instead of silently failing.

### Speeding up OCR

OCR is inherently slower than reading normal text — each page has to be
turned into an image and then read like a photograph. Three things make it
faster, all set via environment variables (add them to `.env` alongside
your API key, or `export`/`set` them like any other variable):

| Variable | Default | What it does |
|---|---|---|
| `FILEWHISPERER_OCR_MAX_WORKERS` | up to 4 (capped by your CPU cores) | Pages are OCR'd **in parallel**, not one at a time. Raising this helps most on a multi-core machine; on a single-core one it won't do much. |
| `FILEWHISPERER_OCR_RENDER_SCALE` | `2.0` | How sharp each page is rendered before OCR. Lower (e.g. `1.5`) is noticeably faster but can lose accuracy on small or dense text. |
| `FILEWHISPERER_OCR_MAX_PAGES` | `20` | Hard cap on pages OCR'd per document. Lower it if you only need the first few pages of long scans. |

Example — push harder on parallelism and accept slightly lower render
quality for speed:
```bash
export FILEWHISPERER_OCR_MAX_WORKERS=8
export FILEWHISPERER_OCR_RENDER_SCALE=1.5
```

Two smaller things already built in, with no configuration needed: pages
are converted to grayscale before OCR (less data to process, and usually
*more* accurate, since color noise is removed), and Tesseract runs in
LSTM-only mode (`--oem 1`), which is faster than trying its older legacy
engine too.

If OCR still comes back empty on a page it hasn't already given up on,
FileWhisperer automatically checks Tesseract's own confidence score and — only
if that's low — tries the other three rotations (in case the scan is
sideways or upside down, common with phone-scanned documents) and a couple
of contrast/threshold variants (in case the scan is faded or has a light
watermark/security background behind the text). This only kicks in when
the plain first attempt looks unreliable, so a normal clean scan isn't
slowed down by it.

## Alternative: setting the key as a permanent environment variable

If you'd rather not use `.env`, you can set `OPENROUTER_API_KEY` once at the
OS level so it's available in every terminal, forever, without a `.env`
file:

- **Windows (Command Prompt, permanent):** `setx OPENROUTER_API_KEY "sk-or-..."`
  — then close and reopen your terminal for it to take effect.
- **macOS/Linux (bash/zsh):** add `export OPENROUTER_API_KEY="sk-or-..."` to
  the end of `~/.bashrc` or `~/.zshrc`, then run `source ~/.bashrc` (or open
  a new terminal).

Either approach works — `.env` keeps the key scoped to this project folder,
while a permanent environment variable makes it available everywhere on
your machine.

### Remember Me

FileWhisperer stores a cryptographically random 30-day remember-me token in the browser and stores only its SHA-256 hash in `data/documind.db`. The database is kept outside the Python package files so replacing/updating the code does not require recreating accounts.

For local development over `http://localhost`, leave `FILEWHISPERER_COOKIE_SECURE=false`. For an HTTPS deployment, set `FILEWHISPERER_COOKIE_SECURE=true`.

### Database compatibility note

The application is branded and packaged as **FileWhisperer**, but the local SQLite filename remains `data/documind.db` intentionally so existing DocuMind-era accounts and chat history can be carried forward without a database migration. Do not rename or delete this file unless you intentionally want to start with a new database.
