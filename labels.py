def build(confidence_score: float) -> tuple[str, dict]:
    """
    Maps ensemble confidence score to attribution string and transparency label.

    Thresholds:
        >= 0.70  → high-confidence AI
        <= 0.30  → high-confidence human
        else     → uncertain

    Returns:
        (attribution, label_dict)
        attribution: "ai" | "human" | "uncertain"
        label_dict: { headline, body, confidence_display }
    """
    score_pct = round(confidence_score * 100)

    if confidence_score >= 0.70:
        return "ai", {
            "headline": "Likely AI-Generated",
            "body": (
                f"Our system is highly confident this content was AI-generated "
                f"(confidence: {score_pct}%). This content has been labeled accordingly. "
                "If you are the author and believe this is incorrect, you may submit an appeal."
            ),
            "confidence_display": f"{score_pct}% AI likelihood",
        }

    if confidence_score <= 0.30:
        human_pct = 100 - score_pct
        return "human", {
            "headline": "Likely Human-Written",
            "body": (
                f"Our system is highly confident this content was written by a human "
                f"(confidence: {human_pct}% human likelihood). "
                "No AI attribution label has been applied."
            ),
            "confidence_display": f"{human_pct}% human likelihood",
        }

    return "uncertain", {
        "headline": "Authorship Uncertain",
        "body": (
            f"Our system found mixed signals in this content and cannot confidently "
            f"determine authorship ({score_pct}% AI likelihood). "
            "No definitive label has been applied. If this is your original work, "
            "you may submit an appeal to have it reviewed."
        ),
        "confidence_display": f"{score_pct}% AI likelihood (uncertain)",
    }
