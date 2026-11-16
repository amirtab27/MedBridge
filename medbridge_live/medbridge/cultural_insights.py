"""Patient-triggered, non-diagnostic prompts for the clinician."""
import re

RULES = [
 (r"\b(navratri|ramadan|ramzan|lent|religious fast|fasting|vrat|upvas|roza|ayuno|cuaresma|उपवास|व्रत|रोज़ा)\b", "Fasting", "Ask whether fasting changes meal times, hydration, or medication use. Do not assume the patient is fasting."),
 (r"\b(vegetarian|vegan|no meat|don't eat meat|dont eat meat|vegetariano|vegetariana|शाकाहारी|मांस नहीं)\b", "Dietary preference", "Ask about usual meals and any nutritional concerns relevant to the patient's symptoms; do not assume a deficiency."),
 (r"\b(ayurveda|ayurvedic|herbal|home remedy|traditional medicine|remedio casero|hierbas|घरेलू नुस्ख|आयुर्वेद|जड़ी.?बूटी)\b", "Traditional remedies", "Ask what remedies, herbs, or supplements the patient uses and check for possible medication interactions without judgment."),
 (r"\b(can't afford|cannot afford|too expensive|no insurance|cost of medicine|no puedo pagar|muy caro|sin seguro|पैसे नहीं|महंगा|महँगा)\b", "Cost or access barrier", "Ask whether cost, transportation, or access makes the care plan difficult; consider available lower-cost options."),
 (r"\b(tortilla|tortillas|dal|daal|roti|chapati|rice|arroz|चपाती|रोटी|दाल|चावल)\b", "Food context", "Ask about typical portions and meal patterns rather than recommending unfamiliar substitutions."),
]

def insights(text: str) -> list[dict]:
    return [{"topic":name,"suggestion":suggestion} for pattern,name,suggestion in RULES if re.search(pattern,text,re.IGNORECASE)][:3]
