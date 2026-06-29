import json
import requests
import gradio as gr

API_BASE = "http://localhost:5001"


def submit_text(text: str, creator_id: str):
    if not text.strip():
        return "—", "—", "—", "—", "Please enter text."

    try:
        r = requests.post(
            f"{API_BASE}/submit",
            json={"text": text, "creator_id": creator_id or "gradio-user"},
            timeout=30,
        )
    except requests.ConnectionError:
        return "—", "—", "—", "—", "Flask server not running on port 5001."

    if r.status_code == 429:
        return "—", "—", "—", "—", "Rate limit hit. Wait a minute and try again."
    if r.status_code == 400:
        return "—", "—", "—", "—", r.json().get("error", "Bad request.")
    if not r.ok:
        return "—", "—", "—", "—", f"Error {r.status_code}"

    d = r.json()
    attribution = d["attribution"].upper()
    confidence = f"{round(d['confidence'] * 100)}%"
    signals = f"LLM: {d['llm_score']}  |  Stylometric: {d['signals']['stylometric']}"
    label_text = d["label"]["body"]
    content_id = d["content_id"]

    return attribution, confidence, signals, content_id, label_text


def file_appeal(content_id: str, reasoning: str):
    if not content_id.strip():
        return "Paste a content_id from a submission above."
    if not reasoning.strip():
        return "Reasoning is required."

    try:
        r = requests.post(
            f"{API_BASE}/appeal",
            json={"content_id": content_id.strip(), "creator_reasoning": reasoning},
            timeout=10,
        )
    except requests.ConnectionError:
        return "Flask server not running on port 5001."

    if r.status_code == 404:
        return "content_id not found."
    if r.status_code == 429:
        return "Appeal rate limit hit (5/hour)."
    if not r.ok:
        return r.json().get("error", f"Error {r.status_code}")

    d = r.json()
    return f"Appeal received. ID: {d['appeal_id']}\nStatus: {d['status']}"


def fetch_log(limit: int):
    try:
        r = requests.get(f"{API_BASE}/log", params={"limit": int(limit)}, timeout=10)
    except requests.ConnectionError:
        return "Flask server not running on port 5001."

    if not r.ok:
        return f"Error {r.status_code}"

    entries = r.json().get("entries", [])
    if not entries:
        return "No entries yet."

    lines = []
    for e in entries:
        appeal_str = " [APPEALED]" if e.get("appeal") else ""
        lines.append(
            f"{e['timestamp'][:19]}  {e['attribution'].upper():9}  "
            f"conf={e['confidence']:.3f}  llm={e.get('llm_score', '?')}  "
            f"stylo={e['signals']['stylometric']:.3f}  "
            f"status={e['status']}{appeal_str}\n"
            f"  id: {e['content_id']}"
        )
    return "\n\n".join(lines)


ATTR_COLORS = {"AI": "#ffcccc", "HUMAN": "#ccffcc", "UNCERTAIN": "#fff3cc"}

with gr.Blocks(title="Provenance Guard", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# Provenance Guard\nAI content attribution — submit text, get a confidence score and transparency label.")

    with gr.Tab("Submit"):
        with gr.Row():
            with gr.Column(scale=2):
                text_input = gr.Textbox(
                    label="Text (50–10,000 chars)",
                    lines=8,
                    placeholder="Paste text here...",
                )
                creator_input = gr.Textbox(label="Creator ID", value="gradio-user")
                submit_btn = gr.Button("Analyze", variant="primary")
            with gr.Column(scale=1):
                attr_out = gr.Textbox(label="Attribution")
                conf_out = gr.Textbox(label="Confidence")
                signals_out = gr.Textbox(label="Signal Scores")
                cid_out = gr.Textbox(label="Content ID (save for appeal)")
                label_out = gr.Textbox(label="Transparency Label", lines=4)

        submit_btn.click(
            submit_text,
            inputs=[text_input, creator_input],
            outputs=[attr_out, conf_out, signals_out, cid_out, label_out],
        )

    with gr.Tab("Appeal"):
        gr.Markdown("Dispute a classification. Paste the content_id from a submission.")
        appeal_cid = gr.Textbox(label="Content ID")
        appeal_reason = gr.Textbox(label="Your reasoning", lines=4)
        appeal_btn = gr.Button("Submit Appeal", variant="secondary")
        appeal_out = gr.Textbox(label="Result")

        appeal_btn.click(
            file_appeal,
            inputs=[appeal_cid, appeal_reason],
            outputs=[appeal_out],
        )

    with gr.Tab("Audit Log"):
        log_limit = gr.Slider(1, 50, value=10, step=1, label="Entries to show")
        log_btn = gr.Button("Fetch Log")
        log_out = gr.Textbox(label="Recent entries", lines=20)

        log_btn.click(fetch_log, inputs=[log_limit], outputs=[log_out])


if __name__ == "__main__":
    demo.launch(server_port=7860)
