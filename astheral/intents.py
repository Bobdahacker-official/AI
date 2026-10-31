"""Coarse teacher-answer labels used only for auxiliary training supervision."""
import re

LABELS = ("identity", "name_context", "greeting", "thanks", "goodbye", "food", "music", "books", "creative", "study", "writing", "pets", "outdoors", "support", "humor", "explanation", "social", "open")


def answer_intent(text):
    text = text.casefold()
    groups = [
        ("identity", r"astheral|ai assistant|software|physical robot|feelings|don't have a body"),
        ("name_context", r"\b(emma|ben|maya|omar|nora|leo|ada|sam)\b|your name|call you"),
        ("food", r"cook|pasta|tomato|recipe|ingredient|meal|dinner|food|garlic|olive"),
        ("music", r"music|jazz|song|piano|pop artist|vocals|instrumental"),
        ("books", r"book|read|novel|myster|thriller|ending|adventure stor"),
        ("creative", r"sketch|draw|creative|hobby|gardening|short story|photography"),
        ("study", r"math|arithmet|subject|studying|four|seven|ten|guessing game|python"),
        ("writing", r"writing|message|note|thank you for your help|thanks for helping"),
        ("pets", r"\b(cat|dog|pet|animal)\b|nap"),
        ("outdoors", r"trip|beach|walk|waterproof|jacket|weather|where would you like to go"),
        ("support", r"rest|break|frustrat|sorry|small task|rough"),
        ("humor", r"bicycle|two-tired|joke|smile"),
        ("explanation", r"computer|variable|machine|instructions|explained|information|patient"),
        ("goodbye", r"goodbye|take care|see you later|have a good day"),
        ("thanks", r"you're welcome|glad i could help|glad it helped"),
        ("greeting", r"^hello|^hi\b|^hey\b|welcome back|good morning|good evening"),
        ("social", r"how are you|how.*day|ready to chat|what happened|what made it|what is on your mind"),
    ]
    for label, pattern in groups:
        if re.search(pattern, text):
            return LABELS.index(label)
    return LABELS.index("open")
