"""SAGE's fixed spoken phrases in English and Hindi. Pick with APP_LANGUAGE in .env."""
import config

PHRASES = {
    "ready":         {"en": "SAGE is ready.",
                      "hi": "सेज तैयार है।"},
    "yes":           {"en": "Yes?",
                      "hi": "हाँ, बोलिए?"},
    "not_heard":     {"en": "I didn't hear anything.",
                      "hi": "मुझे कुछ सुनाई नहीं दिया।"},
    "alerting":      {"en": "I'm alerting your family right now. Stay where you are.",
                      "hi": "मैं अभी आपके परिवार को बता रही हूँ। आप वहीं रहिए।"},
    "checkin":       {"en": "Good morning! How are you feeling today?",
                      "hi": "सुप्रभात! आज आप कैसा महसूस कर रहे हैं?"},
    "med_ask":       {"en": "It's time for your {label}. Have you taken it?",
                      "hi": "आपकी {label} का समय हो गया है। क्या आपने ले ली?"},
    "med_thanks":    {"en": "Thank you. Well done.",
                      "hi": "धन्यवाद, बहुत अच्छा।"},
    "med_take_now":  {"en": "Please take your {label} now. I'll ask again in a little while.",
                      "hi": "कृपया अभी अपनी {label} ले लीजिए। मैं थोड़ी देर में फिर पूछूँगी।"},
    "tell_family":   {"en": "I'll let your family know.",
                      "hi": "मैं आपके परिवार को बता दूँगी।"},
    "offline_help":  {"en": "I've alerted your family.",
                      "hi": "मैंने आपके परिवार को बता दिया है।"},
    "offline_error": {"en": "Sorry, I can't think clearly right now. Press the button and say help if you need your family.",
                      "hi": "माफ़ कीजिए, अभी मैं ठीक से सोच नहीं पा रही। परिवार की ज़रूरत हो तो बटन दबाकर मदद बोलिए।"},
}


def t(key: str, **kw) -> str:
    lang = config.APP_LANGUAGE if config.APP_LANGUAGE in ("en", "hi") else "en"
    return PHRASES[key][lang].format(**kw)
