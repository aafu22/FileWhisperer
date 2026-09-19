"""FileWhisperer — a small retrieval-augmented Q&A assistant for your own documents."""

from dotenv import load_dotenv

load_dotenv()  # reads a .env file in the current working directory, if present

from .assistant import FileWhisperer

__all__ = ["FileWhisperer"]
__version__ = "0.1.0"
