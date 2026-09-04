def generate_summary_from_transcript(transcript_text: str) -> str:
    if not transcript_text or not transcript_text.strip():
        return "No transcript content was available for summarization."

    sentences = [s.strip() for s in transcript_text.replace("\n", " ").split(". ") if s.strip()]
    if not sentences:
        return transcript_text.strip()

    selected = []
    for sentence in sentences[:3]:
        selected.append(sentence.rstrip("."))

    summary = " ".join(selected)
    if len(summary) > 900:
        summary = summary[:897].rstrip() + "..."
    return summary
