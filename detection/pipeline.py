from detection import groq_signal, stylometric

_GROQ_WEIGHT = 0.60
_STYLO_WEIGHT = 0.40


def run(text: str) -> dict:
    """
    Runs both detection signals and returns ensemble result.
    Falls back to stylometric-only (Groq weight redistributed) if Groq is unavailable.

    Returns:
        groq_score:       float | None
        stylo_score:      float
        confidence_score: float (weighted ensemble or stylometric fallback)
    """
    stylo_score = stylometric.analyze(text)

    try:
        groq_score = groq_signal.analyze(text)
        confidence_score = round(
            groq_score * _GROQ_WEIGHT + stylo_score * _STYLO_WEIGHT, 4
        )
    except Exception:
        groq_score = None
        confidence_score = stylo_score  # full weight to stylometric on Groq failure

    return {
        "groq_score": groq_score,
        "stylo_score": stylo_score,
        "confidence_score": confidence_score,
    }
