import os,re,threading,unicodedata
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel
from concurrent.futures import ThreadPoolExecutor
import asyncio
app=FastAPI(); pool=ThreadPoolExecutor(max_workers=1)
ROOT=Path(__file__).parent
LANG={'en':'eng_Latn','hi':'hin_Deva','es':'spa_Latn','zh':'zho_Hans'}
EXAMPLES=[('en','hi','Take 5 mg twice daily. Do not drink alcohol.','दिन में दो बार 5 मिलीग्राम लें। शराब न पिएँ।'),('en','es','Take 5 mg twice daily. Do not drink alcohol.','Tome 5 mg dos veces al día. No beba alcohol.'),('en','zh','Take 5 mg twice daily. Do not drink alcohol.','每天两次，每次服用5毫克。不要喝酒。'),('hi','en','मेरा दिल घबरा रहा है।','I feel uneasy.'),('hi','en','Mera dil ghabra raha hai','I feel uneasy.'),('zh','en','我很害怕，我不明白。','I am very scared. I do not understand.'),('es','en','Tengo mucho miedo.','I am very scared.'),('hi','en','मैं दिन में एक बार 5 मिलीग्राम लूँगा।','I will take 5 mg once daily.'),('es','en','Tomaré 5 mg una vez al día.','I will take 5 mg once daily.'),('zh','en','我每天服用一次5毫克。','I will take 5 mg once daily.')]
CACHE={(a,b,c.strip()):d for a,b,c,d in EXAMPLES}; CACHE.update({(b,a,d):c for a,b,c,d in EXAMPLES})
model=tok=None

def translate(text,src,tgt):
 global model,tok
 if src==tgt:return text,'same language'
 if (src,tgt,text.strip()) in CACHE:return CACHE[src,tgt,text.strip()],'review-needed demo phrase'
 if os.getenv('MEDBRIDGE_MODEL','0')!='1':raise ValueError('Offline demo supports the example phrases only. Enable MEDBRIDGE_MODEL=1 for arbitrary text.')
 import torch
 from transformers import AutoTokenizer,AutoModelForSeq2SeqLM
 if model is None:
  name='facebook/nllb-200-distilled-600M'; tok=AutoTokenizer.from_pretrained(name); model=AutoModelForSeq2SeqLM.from_pretrained(name).to('cuda' if torch.cuda.is_available() else 'cpu').eval()
 tok.src_lang=LANG[src]; inputs=tok(text,return_tensors='pt',truncation=True,max_length=256).to(model.device)
 with torch.inference_mode():out=model.generate(**inputs,forced_bos_token_id=tok.convert_tokens_to_ids(LANG[tgt]),max_new_tokens=128,num_beams=2)
 return tok.batch_decode(out,skip_special_tokens=True)[0],'NLLB research model'

def norm(s):return unicodedata.normalize('NFKC',s).casefold().translate(str.maketrans('०१२३४५६७८९','0123456789'))
UNITS={'mg':'mg','milligrams':'mg','milligram':'mg','miligramos':'mg','मिलीग्राम':'mg','毫克':'mg','ml':'ml','milliliters':'ml','मिलीलीटर':'ml','毫升':'ml','g':'g','grams':'g','gramos':'g','ग्राम':'g','克':'g','mcg':'mcg','micrograms':'mcg','微克':'mcg'}
NUM={'five':'5','fifty':'50','cinco':'5','cincuenta':'50','पाँच':'5','पांच':'5','पचास':'50','五十':'50','五':'5','一':'1','二':'2','两':'2'}
FREQ={'1/day':['once daily','once a day','una vez al día','दिन में एक बार','每天一次','每天服用一次'],'2/day':['twice daily','twice a day','dos veces al día','दिन में दो बार','每天两次'],'3/day':['three times daily','three times a day','tres veces al día','दिन में तीन बार','每天三次']}
NEG={'en':r'\b(?:do not|don’t|don\x27t|never|not|no)\b','es':r'\b(?:no|nunca|jamás)\b','hi':r'नहीं|मत|(?<!\S)न(?!\S)','zh':r'不要|禁止|别|不'}
def facts(text,lang):
 s=norm(text)
 for k,v in sorted(NUM.items(),key=lambda x:-len(x[0])):s=re.sub(r'(?<!\w)'+re.escape(k)+r'(?!\w)',v,s) if k.isascii() or lang=='es' else s.replace(k,v)
 units='|'.join(map(re.escape,sorted(UNITS,key=len,reverse=True)))
 doses=[(float(n),UNITS[u]) for n,u in re.findall(r'(\d+(?:\.\d+)?)\s*('+units+r')',s)]
 # frequency matching uses original normalized text
 freq=[k for k,vs in FREQ.items() if any(v in norm(text) for v in vs)]
 return {'doses':doses,'frequency':freq,'negations':len(re.findall(NEG[lang],norm(text)))}
def flag(kind,level,reason,span='',suggestion=''):return dict(kind=kind,level=level,reason=reason,span=span,suggestion=suggestion)
def safety(text,src,translation,tgt,teach=False):
 a,b=facts(text,src),facts(translation,tgt); out=[]
 for k in ['doses','frequency']:
  if a[k]!=b[k]:out.append(flag('safety','red',f'{k.capitalize()} differ: {a[k]} → {b[k]}'))
 if not teach and a['negations']!=b['negations']:out.append(flag('safety','red','Negation count differs; confirm which instruction is prohibited.'))
 if teach and a['negations']:out.append(flag('teach-back','amber','Ask the patient to restate the warning explicitly; not verified by this comparison.'))
 return out
CULTURE=[('hi',['मेरा दिल घबरा रहा है','mera dil ghabra raha hai'],'Unease, anxiety, palpitations or nausea','What are you feeling in your body? Is your heart racing, or do you feel nauseated or uneasy?'),('hi',['सर भारी है','sar bhaari hai','सिर भारी है'],'Pain, pressure or fatigue','Can you describe the sensation in your head?'),('es',['ataque de nervios'],'Emotional distress or other physical symptoms','Can you describe what happened in your body?'),('zh',['心慌'],'Palpitations or unease','Can you describe what you feel in your chest?'),('zh',['上火'],'Various symptoms, including mouth discomfort','Which symptoms are you noticing?')]
EMO={'en':{'fear':['scared','afraid'],'confusion':['do not understand',"don't understand"],'worry':['worried'],'pain':['hurts','pain']},'hi':{'fear':['डर लग','dar lag'],'confusion':['समझ नहीं','samajh nahi'],'worry':['चिंता','फ़िक्र'],'pain':['दर्द']},'es':{'fear':['miedo','asustado','asustada'],'confusion':['no entiendo'],'worry':['preocupa'],'pain':['duele','dolor']},'zh':{'fear':['害怕','很怕'],'confusion':['不明白','听不懂'],'worry':['担心'],'pain':['疼','痛']}}
def emotions(text,lang):
 s=norm(text); out=[]
 for cat,words in EMO[lang].items():
  for w in words:
   if w in s:
    if cat!='confusion' and any(x+w in s for x in ['not ','no ','不','没']):continue
    out.append({'category':cat,'span':w,'intensity':'strong' if any(x in s for x in ['very','mucho','बहुत','很','非常']) else 'normal'});break
 return out
class Request(BaseModel):
 text:str; src:str='en'; tgt:str='hi'; inject:bool=False; reference:str=''
def process(r):
 if r.src not in LANG or r.tgt not in LANG:raise ValueError('Unsupported language')
 if not r.text.strip() or len(r.text)>1500:raise ValueError('Enter 1–1500 characters')
 t,mode=translate(r.text,r.src,r.tgt)
 if r.inject:t=re.sub(r'(?<!\d)5(?!\d)','50',t,count=1)
 flags=safety(r.text,r.src,t,r.tgt)
 for lang,variants,meaning,q in CULTURE:
  if lang==r.src and any(norm(v) in norm(r.text) for v in variants):flags.append(flag('culture','amber','Ambiguous expression: '+meaning,suggestion=q))
 em=emotions(r.text,r.src); target=emotions(t,r.tgt)
 for e in em:
  if not any(x['category']==e['category'] for x in target):flags.append(flag('emotion','amber','Expressed '+e['category']+' may be missing in translation.',e['span']))
 if r.reference:flags+=safety(r.reference,'en',t,r.tgt,True)
 return dict(text=r.text,translation=t,flags=flags,emotions=em,mode=mode,injected=r.inject,src=r.src,tgt=r.tgt,teach=bool(r.reference))
@app.get('/')
def index():return FileResponse(ROOT/'index.html')
@app.post('/api/message')
async def message(r:Request):
 try:return await asyncio.get_running_loop().run_in_executor(pool,process,r)
 except Exception as e:return {'error':str(e)}
rooms={}
@app.websocket('/ws/{room}')
async def ws(w:WebSocket,room:str):
 await w.accept(); rooms.setdefault(room,set()).add(w)
 try:
  while True:
   data=await w.receive_json()
   for peer in list(rooms[room]):
    if peer!=w:
     try:await peer.send_json(data)
     except Exception:rooms[room].discard(peer)
 except WebSocketDisconnect:pass
 finally:rooms[room].discard(w)
