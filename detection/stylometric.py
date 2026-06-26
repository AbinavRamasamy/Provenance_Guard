import re
import math

# Connective/transitional words that appear at elevated rates in AI writing
_AI_FUNCTION_WORDS = frozenset({
    "however", "therefore", "furthermore", "moreover", "consequently",
    "additionally", "notably", "specifically", "ultimately", "essentially",
    "particularly", "significantly", "importantly", "accordingly", "hence",
    "thus", "indeed", "certainly", "clearly", "obviously", "nonetheless",
    "nevertheless", "subsequently", "previously", "additionally",
})


def _sentences(text: str) -> list[str]:
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s for s in parts if s.strip()]


def _words(text: str) -> list[str]:
    return re.findall(r'\b[a-zA-Z]+\b', text.lower())


def _score_burstiness(sentence_lengths: list[int]) -> float:
    """Low std dev of sentence lengths → uniform → AI-like → returns high score."""
    if len(sentence_lengths) < 3:
        return 0.5  # insufficient data for reliable measurement
    mean = sum(sentence_lengths) / len(sentence_lengths)
    variance = sum((length - mean) ** 2 for length in sentence_lengths) / len(sentence_lengths)
    std_dev = math.sqrt(variance)
    # std_dev near 0 → AI (1.0); std_dev ≥ 15 → human (0.0)
    return round(max(0.0, 1.0 - std_dev / 15.0), 4)


def _score_avg_sentence_length(sentence_lengths: list[int]) -> float:
    """AI clusters around 15–25 word sentences. Extremes are human-like."""
    if not sentence_lengths:
        return 0.5
    avg = sum(sentence_lengths) / len(sentence_lengths)
    # Bell curve centered at 20; ±15 words away → score approaches 0
    return round(max(0.0, 1.0 - abs(avg - 20) / 15.0), 4)


def _score_ttr(words: list[str]) -> float:
    """Vocabulary diversity. AI texts cluster in a moderate TTR band."""
    if len(words) < 20:
        return 0.5  # too short for reliable TTR
    ttr = len(set(words)) / len(words)
    # AI clusters around TTR ~0.55; very high or very low TTR is human-like
    # ±0.35 away from center → score approaches 0
    return round(max(0.0, 1.0 - abs(ttr - 0.55) / 0.35), 4)


def _score_function_word_density(words: list[str]) -> float:
    """Higher density of AI connective words → higher AI probability."""
    if not words:
        return 0.0
    count = sum(1 for w in words if w in _AI_FUNCTION_WORDS)
    density = count / len(words)
    # Density of 0.04 (4%) is notably AI-like; normalize to [0, 1]
    return round(min(1.0, density / 0.04), 4)


def _score_punctuation_consistency(sentences: list[str]) -> float:
    """All-period endings signal AI uniformity; mixed punctuation is human-like."""
    if len(sentences) < 3:
        return 0.5
    endings = [s.strip()[-1] for s in sentences if s.strip()]
    if not endings:
        return 0.5
    period_ratio = endings.count(".") / len(endings)
    # period_ratio of 1.0 → 1.0; period_ratio of 0.5 → 0.0
    return round(max(0.0, (period_ratio - 0.5) / 0.5), 4)


def analyze(text: str) -> float:
    """
    Returns probability of AI authorship in [0.0, 1.0].
    0.0 = almost certainly human. 1.0 = almost certainly AI.
    Combines 5 stylometric features via equal-weight average.
    """
    sents = _sentences(text)
    ws = _words(text)
    sent_lengths = [len(re.findall(r'\b[a-zA-Z]+\b', s)) for s in sents]

    feature_scores = [
        _score_burstiness(sent_lengths),
        _score_avg_sentence_length(sent_lengths),
        _score_ttr(ws),
        _score_function_word_density(ws),
        _score_punctuation_consistency(sents),
    ]

    return round(sum(feature_scores) / len(feature_scores), 4)
