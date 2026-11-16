"""Supplemental educational glosses, never replacements for clinical translations."""
import re

GLOSSARY = {
 "hypertension": {"en":"High blood pressure: blood pushes against artery walls with more force than usual.","es":"Presión arterial alta: la sangre empuja las paredes de las arterias con más fuerza de lo habitual.","hi":"उच्च रक्तचाप: खून धमनियों की दीवारों पर सामान्य से अधिक दबाव डालता है।","zh":"高血压：血液对动脉壁的压力高于正常水平。"},
 "hypoglycemia": {"en":"Low blood sugar: the amount of sugar in your blood is below the usual range.","es":"Nivel bajo de azúcar en la sangre: la glucosa está por debajo del nivel habitual.","hi":"खून में शुगर कम होना: रक्त में शुगर का स्तर सामान्य से कम है।","zh":"低血糖：血液中的血糖水平低于正常范围。"},
 "biopsy": {"en":"A test where a small sample of tissue is taken and examined.","es":"Una prueba en la que se toma una pequeña muestra de tejido para examinarla.","hi":"एक जांच जिसमें शरीर के ऊतक का छोटा नमूना लेकर उसकी जांच की जाती है।","zh":"活检：取少量身体组织进行检查。"},
 "inflammation": {"en":"The body's response to irritation or injury; it can cause swelling, redness, warmth or pain.","es":"Respuesta del cuerpo a una irritación o lesión; puede causar hinchazón, enrojecimiento, calor o dolor.","hi":"चोट या जलन पर शरीर की प्रतिक्रिया; इससे सूजन, लालिमा, गर्माहट या दर्द हो सकता है।","zh":"炎症：身体对刺激或损伤的反应，可能出现肿胀、发红、发热或疼痛。"},
 "anemia": {"en":"A condition where you do not have enough healthy red blood cells or hemoglobin to carry oxygen well.","es":"Una afección en la que no hay suficientes glóbulos rojos sanos o hemoglobina para transportar bien el oxígeno.","hi":"ऐसी स्थिति जिसमें ऑक्सीजन पहुंचाने के लिए पर्याप्त स्वस्थ लाल रक्त कोशिकाएं या हीमोग्लोबिन नहीं होता।","zh":"贫血：健康红细胞或血红蛋白不足，影响氧气输送。"},
 "dehydration": {"en":"Your body has lost more fluid than it has taken in.","es":"Su cuerpo ha perdido más líquido del que ha recibido.","hi":"आपके शरीर में जितना तरल गया है, उससे अधिक तरल निकल गया है।","zh":"脱水：身体流失的水分多于摄入的水分。"},
 "antibiotics": {"en":"Medicines used to treat certain infections caused by bacteria; they do not treat viruses.","es":"Medicamentos para tratar algunas infecciones causadas por bacterias; no tratan los virus.","hi":"कुछ बैक्टीरिया से होने वाले संक्रमण के इलाज की दवाएं; ये वायरस पर काम नहीं करतीं।","zh":"抗生素：治疗某些细菌感染的药物，不能治疗病毒感染。"},
 "chronic": {"en":"Long-lasting or continuing over time; it does not necessarily mean severe.","es":"Que dura mucho tiempo o continúa con el tiempo; no significa necesariamente grave.","hi":"जो लंबे समय तक बना रहता है; इसका मतलब हमेशा गंभीर होना नहीं है।","zh":"慢性：持续较长时间，不一定意味着严重。"},
}

def explain(text: str, lang: str) -> list[dict]:
    out=[]
    for term, translations in GLOSSARY.items():
        if re.search(r"\b"+re.escape(term)+r"\b", text, re.IGNORECASE):
            out.append({"term":term, "explanation":translations.get(lang, translations["en"])})
    return out[:3]
