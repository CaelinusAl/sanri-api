from typing import List, Dict


def evolve_memory(memory_list: List[Dict]) -> Dict:
    """
    Kullanıcının geçmiş konuşmalarından pattern çıkarır
    """

    if not memory_list:
        return {}

    patterns = []
    emotions = []
    topics = []

    for m in memory_list:

        text = (m.get("input_text") or "").lower()

        if "neden" in text or "why" in text:
            patterns.append("deep_questioning")

        if "hissediyorum" in text or "feel" in text:
            emotions.append("emotional_awareness")

        if "gelecek" in text or "future" in text:
            topics.append("future_focus")

    return {
        "pattern": list(set(patterns)),
        "emotion": list(set(emotions)),
        "topics": list(set(topics))
    }