import hashlib
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import db
import labels
from detection import pipeline

load_dotenv()

app = Flask(__name__)

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    storage_uri="memory://",
    default_limits=[],
)

with app.app_context():
    db.init_db()


@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def submit():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "request body must be JSON"}), 400

    missing = [f for f in ("text", "creator_id") if f not in data]
    if missing:
        return jsonify({"error": f"missing required fields: {', '.join(missing)}"}), 400

    text = data["text"]
    if not isinstance(text, str) or not (50 <= len(text) <= 10000):
        return jsonify({"error": "text must be between 50 and 10000 characters"}), 400

    creator_id = data["creator_id"]
    content_id = str(uuid.uuid4())
    text_hash = hashlib.sha256(text.encode()).hexdigest()
    timestamp = datetime.now(timezone.utc).isoformat()

    signals = pipeline.run(text)
    attribution, label = labels.build(signals["confidence_score"])

    db.insert_log_entry(
        content_id=content_id,
        creator_id=creator_id,
        text_hash=text_hash,
        groq_score=signals["groq_score"],
        stylo_score=signals["stylo_score"],
        confidence_score=signals["confidence_score"],
        attribution=attribution,
        label=label,
        timestamp=timestamp,
    )

    return jsonify({
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": timestamp,
        "attribution": attribution,
        "confidence": signals["confidence_score"],
        "llm_score": signals["groq_score"],
        "signals": {
            "groq": signals["groq_score"],
            "stylometric": signals["stylo_score"],
        },
        "label": label,
        "status": "classified",
    }), 200


@app.route("/appeal", methods=["POST"])
@app.route("/appeal/<content_id>", methods=["POST"])
@limiter.limit("5 per hour")
def appeal(content_id=None):
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "request body must be JSON"}), 400

    if content_id is None:
        content_id = data.get("content_id")
        if not content_id:
            return jsonify({"error": "missing required field: content_id"}), 400

    if "creator_reasoning" not in data:
        return jsonify({"error": "missing required field: creator_reasoning"}), 400

    entry = db.get_entry(content_id)
    if not entry:
        return jsonify({"error": "content_id not found"}), 404

    appeal_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    db.insert_appeal(
        appeal_id=appeal_id,
        content_id=content_id,
        creator_reasoning=data["creator_reasoning"],
        contact=data.get("contact"),
        timestamp=timestamp,
    )
    db.update_status(content_id, "under_review")

    return jsonify({
        "appeal_id": appeal_id,
        "content_id": content_id,
        "status": "under_review",
        "message": (
            "Your appeal has been received. A reviewer will assess the original "
            "decision alongside your reasoning. No automated re-classification will occur."
        ),
    }), 200


@app.route("/log", methods=["GET"])
def get_log():
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    entries, total = db.get_log_entries(limit=limit, offset=offset)
    return jsonify({"entries": entries, "total": total}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=True, port=port)
