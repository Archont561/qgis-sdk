"""The questions ``qgis-sdk new`` asks a terminal, and nothing about terminals.

Interactive answers and command-line flags feed the same
:class:`~qgis_sdk_tools.scaffold.options.ScaffoldOptions` (decision-18), so this
module only decides *what* is asked, in which order, and what an answer means.
Whoever calls :func:`ask_web_questions` supplies the ``ask`` callable that
prints a prompt and reads a line; a test supplies a script.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .options import (
    DEFAULT_PACKAGE_MANAGER,
    DEFAULT_WEB_PLACEMENT,
    PACKAGE_MANAGERS,
    WEB_FRAMEWORKS,
    WEB_PLACEMENTS,
)

__all__ = [
    "INSTALL_QUESTION",
    "PACKAGE_MANAGER_QUESTION",
    "PLACEMENT_QUESTION",
    "WEB_FRAMEWORK_QUESTION",
    "Ask",
    "Question",
    "WebAnswers",
    "answer",
    "ask_web_questions",
]


@dataclass(frozen=True, slots=True)
class Question:
    """One closed question: a prompt, its choices and the choice silence means."""

    key: str
    prompt: str
    choices: tuple[str, ...]
    default: str

    @property
    def error(self) -> str:
        """What to say when an answer is not one of the choices."""
        return f"choose one of {', '.join(self.choices)}"


Ask = Callable[[Question, "str | None"], str]
"""Show a question (and the error the previous answer earned, if any); return a line."""

NO_WEB = "none"

WEB_FRAMEWORK_QUESTION = Question(
    "web", "Add a web UI?", (NO_WEB, *WEB_FRAMEWORKS), NO_WEB
)
PLACEMENT_QUESTION = Question(
    "placement", "Show it as", WEB_PLACEMENTS, DEFAULT_WEB_PLACEMENT
)
PACKAGE_MANAGER_QUESTION = Question(
    "package_manager",
    "JavaScript package manager",
    PACKAGE_MANAGERS,
    DEFAULT_PACKAGE_MANAGER,
)
INSTALL_QUESTION = Question(
    "install", "Install JavaScript dependencies now?", ("no", "yes"), "no"
)


@dataclass(frozen=True, slots=True)
class WebAnswers:
    """What the terminal chose, in the vocabulary of ``ScaffoldOptions.resolve``."""

    web: str | None
    placement: str | None
    package_manager: str | None
    install: bool


def answer(question: Question, raw: str) -> str | None:
    """The choice ``raw`` names, the default for an empty line, or ``None``."""
    text = raw.strip().lower()
    if not text:
        return question.default
    return text if text in question.choices else None


def ask_web_questions(ask: Ask) -> WebAnswers:
    """Ask about the web UI; stop at the first question if there is to be none."""
    framework = _settle(WEB_FRAMEWORK_QUESTION, ask)
    if framework == NO_WEB:
        return WebAnswers(None, None, None, False)
    placement = _settle(PLACEMENT_QUESTION, ask)
    package_manager = _settle(PACKAGE_MANAGER_QUESTION, ask)
    install = _settle(INSTALL_QUESTION, ask)
    return WebAnswers(framework, placement, package_manager, install == "yes")


def _settle(question: Question, ask: Ask) -> str:
    error: str | None = None
    while True:
        chosen = answer(question, ask(question, error))
        if chosen is not None:
            return chosen
        error = question.error
