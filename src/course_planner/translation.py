"""Translate Chinese course reviews into English, offline.

The default backend is the open-source ``Helsinki-NLP/opus-mt-zh-en`` MarianMT
model, run locally with ``transformers``. Nothing is sent to an external
service. The model files are downloaded once during setup::

    pip install -e ".[translation]"
    python -m course_planner.translation download

After that the app loads them from disk only (``local_files_only=True``).

Machine translation can miss tone and idioms, and the model is trained mostly
on Mandarin, so colloquial Cantonese may translate poorly. The original text is
always kept next to the translation, translated text feeds only one input of
the difficulty score, and ``export_review_sample`` writes a CSV so a
Chinese-reading team member can spot-check translations by hand.
"""

from __future__ import annotations

import csv
import random
import re
import sys
from collections.abc import MutableMapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Protocol

from course_planner.language import detect_language
from course_planner.models import Review

MODEL_NAME = "Helsinki-NLP/opus-mt-zh-en"
INSTALL_HINT = 'Install the translation extras with: pip install -e ".[translation]"'
DOWNLOAD_HINT = "Download the model once with: python -m course_planner.translation download"

_SENTENCE_END_RE = re.compile(r"(?<=[。！？!?；;\n])")


class TranslationUnavailableError(RuntimeError):
    """The offline model or its libraries are not installed."""


class Translator(Protocol):
    def translate(self, texts: Sequence[str]) -> list[str]:
        """Return one English string per input string, in the same order."""


# --------------------------------------------------------------------------- chunking


def split_for_translation(text: str, max_chars: int = 200) -> list[str]:
    """Split ``text`` into pieces of at most ``max_chars`` characters.

    Splits after sentence-ending punctuation first and only cuts inside a
    sentence when one sentence alone is too long, so long reviews are not
    silently truncated by the model's input limit. Whitespace-only pieces are
    dropped; the pieces joined with spaces cover all the text.
    """
    chunks: list[str] = []
    current = ""
    for sentence in _SENTENCE_END_RE.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        while len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        if current and len(current) + len(sentence) > max_chars:
            chunks.append(current)
            current = ""
        current += sentence
    if current:
        chunks.append(current)
    return chunks


# --------------------------------------------------------------------------- backends


class MarianTranslator:
    """Offline Chinese-to-English translation with a local MarianMT model."""

    def __init__(
        self,
        model_name: str = MODEL_NAME,
        *,
        local_files_only: bool = True,
        batch_size: int = 16,
        max_chars: int = 200,
    ) -> None:
        self.model_name = model_name
        self.local_files_only = local_files_only
        self.batch_size = batch_size
        self.max_chars = max_chars
        self._tokenizer = None
        self._model = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from transformers import MarianMTModel, MarianTokenizer
        except ImportError as exc:
            raise TranslationUnavailableError(
                f"The translation libraries are not installed. {INSTALL_HINT}"
            ) from exc
        try:
            self._tokenizer = MarianTokenizer.from_pretrained(
                self.model_name, local_files_only=self.local_files_only
            )
            self._model = MarianMTModel.from_pretrained(
                self.model_name, local_files_only=self.local_files_only
            )
        except OSError as exc:
            if self.local_files_only:
                message = (
                    f"The translation model '{self.model_name}' is not on this computer. "
                    f"{DOWNLOAD_HINT}"
                )
            else:
                message = (
                    f"The translation model '{self.model_name}' could not be downloaded. "
                    "Check your internet connection and try again."
                )
            raise TranslationUnavailableError(message) from exc

    def translate(self, texts: Sequence[str]) -> list[str]:
        if not texts:
            return []
        self._load()
        pieces = [split_for_translation(text, self.max_chars) for text in texts]
        flat = [piece for chunks in pieces for piece in chunks]
        translated: list[str] = []
        for start in range(0, len(flat), self.batch_size):
            translated.extend(self._translate_batch(flat[start : start + self.batch_size]))
        results: list[str] = []
        position = 0
        for chunks in pieces:
            results.append(" ".join(translated[position : position + len(chunks)]).strip())
            position += len(chunks)
        return results

    def _translate_batch(self, batch: list[str]) -> list[str]:
        inputs = self._tokenizer(batch, return_tensors="pt", padding=True, truncation=True)
        output = self._model.generate(**inputs, max_new_tokens=256)
        return self._tokenizer.batch_decode(output, skip_special_tokens=True)


class CachedTranslator:
    """Wrap a translator so each distinct text is translated only once.

    ``cache`` is any mutable mapping from original text to translation, such as
    a dict, or a persistent store implementing the same interface.
    """

    def __init__(self, inner: Translator, cache: MutableMapping[str, str] | None = None) -> None:
        self.inner = inner
        self.cache: MutableMapping[str, str] = {} if cache is None else cache

    def translate(self, texts: Sequence[str]) -> list[str]:
        missing = list(dict.fromkeys(t for t in texts if t not in self.cache))
        if missing:
            for original, english in zip(missing, self.inner.translate(missing), strict=True):
                self.cache[original] = english
        return [self.cache[t] for t in texts]


# --------------------------------------------------------------------------- reviews


@dataclass
class TranslationResult:
    reviews: list[Review]
    # Set when the translator as a whole was unavailable (nothing was translated).
    error: str | None = None
    failures: list[Review] = field(default_factory=list)

    @property
    def translated_count(self) -> int:
        return sum(r.translation_status == "translated" for r in self.reviews)

    @property
    def failed_count(self) -> int:
        return sum(r.translation_status == "failed" for r in self.reviews)

    @property
    def warning(self) -> str | None:
        """Plain-language message for the student, or ``None`` if everything worked."""
        if self.error:
            return (
                f"{self.failed_count} Chinese review(s) could not be translated, so they are "
                f"left out of the difficulty score. {self.error}"
            )
        if self.failed_count:
            return (
                f"{self.failed_count} Chinese review(s) could not be translated and are left "
                "out of the difficulty score."
            )
        return None


def translate_reviews(reviews: Sequence[Review], translator: Translator) -> TranslationResult:
    """Detect each review's language and translate the Chinese ones.

    English reviews pass through unchanged. A review whose translation fails
    keeps its original text, gets ``translation_status == "failed"`` and has no
    ``english_text``, so it can never silently skew a score.
    """
    detected = [replace(r, language=detect_language(r.text)) for r in reviews]
    result_reviews = [
        replace(r, translation=r.text, translation_status="not_needed")
        if r.language == "en"
        else r
        for r in detected
    ]
    pending = [i for i, r in enumerate(result_reviews) if r.language == "zh"]
    outcome = TranslationResult(reviews=result_reviews)
    if not pending:
        return outcome

    texts = [result_reviews[i].text for i in pending]
    try:
        english = _translate_with_fallback(translator, texts)
    except TranslationUnavailableError as exc:
        english = [None] * len(pending)
        outcome.error = str(exc)

    for index, text in zip(pending, english, strict=True):
        review = result_reviews[index]
        if text and text.strip():
            result_reviews[index] = replace(
                review, translation=text.strip(), translation_status="translated"
            )
        else:
            result_reviews[index] = replace(review, translation=None, translation_status="failed")
            outcome.failures.append(result_reviews[index])
    return outcome


def _translate_with_fallback(translator: Translator, texts: list[str]) -> list[str | None]:
    """Translate as one batch; if that breaks, retry one by one so one bad text can't sink all."""
    try:
        result = translator.translate(texts)
        if len(result) == len(texts):
            return list(result)
    except TranslationUnavailableError:
        raise
    except Exception:
        pass
    results: list[str | None] = []
    for text in texts:
        try:
            results.append(translator.translate([text])[0])
        except TranslationUnavailableError:
            raise
        except Exception:
            results.append(None)
    return results


def export_review_sample(
    reviews: Sequence[Review], path: Path | str, n: int = 30, seed: int = 0
) -> int:
    """Write a random sample of translated reviews to CSV for a manual check.

    The columns ``adequate`` and ``notes`` are left blank for the reviewer.
    Returns the number of rows written. The file is UTF-8 with a BOM so Excel
    shows the Chinese text correctly.
    """
    translated = [r for r in reviews if r.translation_status == "translated"]
    sample = random.Random(seed).sample(translated, min(n, len(translated)))
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["course_code", "original", "machine_translation", "adequate", "notes"])
        for review in sample:
            writer.writerow([review.course_code, review.text, review.translation, "", ""])
    return len(sample)


# --------------------------------------------------------------------------- CLI


def download_model(model_name: str = MODEL_NAME) -> None:
    """Fetch the model files into the local Hugging Face cache (needs network, once)."""
    MarianTranslator(model_name, local_files_only=False)._load()


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    usage = "usage: python -m course_planner.translation download | translate TEXT [TEXT ...]"
    if not args or args[0] not in {"download", "translate"}:
        print(usage)
        return 2
    try:
        if args[0] == "download":
            download_model()
            print(f"Model '{MODEL_NAME}' is ready for offline use.")
        else:
            for text, english in zip(args[1:], MarianTranslator().translate(args[1:]), strict=True):
                print(f"{text}\n  -> {english}")
    except TranslationUnavailableError as exc:
        print(exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
