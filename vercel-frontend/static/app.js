(() => {
const role = location.pathname.replace('/', '');
const session = new URLSearchParams(location.search).get('s') || 'demo';
const isDoc = role === 'doctor';
document.body.classList.add(role);
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));

// ---------- i18n for patient UI (unreviewed; native review recommended) ----------
const UI = {
 en: {title:'Doctor', you:'You', speak:'Tap to speak', type:'Type a message…', confirming:'Doctor is confirming this', confirmed:'Confirmed by doctor', waiting:'Waiting for your doctor to join…', empty:'Your doctor’s words will appear here, in your language.', interp:'Request interpreter', prefs:'Preferences', read:'Read aloud', length:'Detail', tone:'Style', mode:'Mode', brief:'Brief', detailed:'Detailed', direct:'Direct', empathetic:'Empathetic', interactive:'Interactive', informational:'Informational', repeat:'Please repeat that', dunno:'I don’t understand', question:'I have a question', listening:'Listening…', paused:'Paused while audio plays', holdSpeak:'Patient is speaking — mic paused', retract:'Doctor is rephrasing', done:'Done', doctorSays:'Doctor', mic:'Microphone'},
 es: {title:'Su médico', you:'Usted', speak:'Toque para hablar', type:'Escriba un mensaje…', confirming:'El médico está confirmando esto', confirmed:'Confirmado por el médico', waiting:'Esperando a su médico…', empty:'Las palabras de su médico aparecerán aquí, en su idioma.', interp:'Solicitar intérprete', prefs:'Preferencias', read:'Leer en voz alta', length:'Detalle', tone:'Estilo', mode:'Modo', brief:'Breve', detailed:'Detallado', direct:'Directo', empathetic:'Empático', interactive:'Interactivo', informational:'Informativo', repeat:'Por favor, repita eso', dunno:'No entiendo', question:'Tengo una pregunta', listening:'Escuchando…', paused:'En pausa mientras suena el audio', holdSpeak:'El médico está hablando — micrófono en pausa', retract:'El médico está reformulando', done:'Listo', doctorSays:'Médico', mic:'Micrófono'},
 hi: {title:'आपके डॉक्टर', you:'आप', speak:'बोलने के लिए दबाएँ', type:'संदेश लिखें…', confirming:'डॉक्टर इसकी पुष्टि कर रहे हैं', confirmed:'डॉक्टर द्वारा पुष्टि की गई', waiting:'आपके डॉक्टर के जुड़ने की प्रतीक्षा है…', empty:'आपके डॉक्टर की बातें यहाँ आपकी भाषा में दिखेंगी।', interp:'दुभाषिया बुलाएँ', prefs:'पसंद', read:'ज़ोर से पढ़ें', length:'विवरण', tone:'शैली', mode:'मोड', brief:'संक्षिप्त', detailed:'विस्तृत', direct:'सीधा', empathetic:'संवेदनशील', interactive:'संवादात्मक', informational:'जानकारीपूर्ण', repeat:'कृपया दोबारा बताइए', dunno:'मुझे समझ नहीं आया', question:'मेरा एक सवाल है', listening:'सुन रहे हैं…', paused:'ऑडियो चलने तक रुका है', holdSpeak:'डॉक्टर बोल रहे हैं — माइक रुका है', retract:'डॉक्टर दोबारा कह रहे हैं', done:'ठीक है', doctorSays:'डॉक्टर', mic:'माइक'},
 zh: {title:'您的医生', you:'您', speak:'点击说话', type:'输入消息…', confirming:'医生正在确认此内容', confirmed:'医生已确认', waiting:'正在等待医生加入…', empty:'医生的话会以您的语言显示在这里。', interp:'请求口译员', prefs:'偏好设置', read:'朗读', length:'详细程度', tone:'风格', mode:'模式', brief:'简短', detailed:'详细', direct:'直接', empathetic:'体贴', interactive:'互动', informational:'资讯', repeat:'请再说一遍', dunno:'我不明白', question:'我有个问题', listening:'正在聆听…', paused:'音频播放时暂停', holdSpeak:'医生正在说话 — 麦克风已暂停', retract:'医生正在重新表述', done:'完成', doctorSays:'医生', mic:'麦克风'}
};
const NAMES = {es: 'Español', hi: 'हिन्दी', zh: '中文', en: 'English'};
const REC = {en: 'en-US', es: 'es-US', hi: 'hi-IN', zh: 'cmn-Hans-CN'};
const TTSL = {en: 'en-US', es: 'es-MX', hi: 'hi-IN', zh: 'zh-CN'};
const QUICK = {es: ['repeat', 'dunno', 'question'], hi: ['repeat', 'dunno', 'question'], zh: ['repeat', 'dunno', 'question']};
const EMP = [['worrying', 'I understand this is worrying'], ['take_your_time', 'Take your time'], ['right_to_come', 'You did the right thing coming in'], ['here_to_help', 'I am here to help']];

let myLang = isDoc ? 'en' : (localStorage.mb_lang || null);
let patLang = 'es', prefs = {tone: 'empathetic', length: 'detailed', mode: 'interactive'}, inject = false;
let readAloud = true;
const T = () => UI[isDoc ? 'en' : patLang] || UI.en;
const msgs = new Map();            // id -> final message
const els = new Map();             // id -> bubble wrapper
let ws, peerOnline = false;

// ---------- websocket ----------
function connect() {
  const queryBackend = new URLSearchParams(location.search).get('backend');
  if (queryBackend) localStorage.setItem('mb_backend', queryBackend.replace(/\/$/, ''));
  const backend = (localStorage.getItem('mb_backend') || location.origin).replace(/\/$/, '');
  const wsBase = backend.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:');
  ws = new WebSocket(`${wsBase}/ws/${encodeURIComponent(session)}/${role}`);
  ws.onopen = () => { if (!isDoc && myLang) sendPrefs(); };
  ws.onclose = () => setTimeout(connect, 1200);
  ws.onmessage = e => on(JSON.parse(e.data));
}
const send = o => ws && ws.readyState === 1 && ws.send(JSON.stringify(o));
const sendPrefs = () => send({type: 'prefs', lang: myLang, prefs});

function on(d) {
  switch (d.type) {
    case 'hello': patLang = d.lang; prefs = d.prefs; inject = d.inject; d.history.forEach(m => { msgs.set(m.id, m); }); renderAll(); break;
    case 'config': patLang = d.lang; prefs = d.prefs; inject = d.inject; relabel(); renderSide(); applyPrefsClasses(); break;
    case 'peer': peerOnline = d.online; relabel(); break;
    case 'interim': if (!msgs.has(d.id) && !done.has(d.id)) showLive(d.id, d.speaker, d.text, d.translation); break;
    case 'checking': done.add(d.id); if (d.speaker === role) markChecking(d.id, d.text); break;
    case 'final': onFinal(d.message, d.lead); break;
    case 'confirmed': { const m = msgs.get(d.id); if (m) { m.translation = d.translation; m.status = 'confirmed'; m.flags = m.flags.filter(f => f.level !== 'red'); renderMsg(m); renderSide(); if (!isDoc) speakMsg(m); } break; }
    case 'retract': { const m = msgs.get(d.id); if (m) { m.status = 'retracted'; renderMsg(m); renderSide(); } break; }
    case 'back': { const m = msgs.get(d.id); if (m) { m.back = d.back; renderMsg(m); } break; }
    case 'peer_floor': onPeerFloor(d.state); break;
    case 'interpreter': banner(d.from === 'patient' ? (isDoc ? '🧑‍⚕️ Patient requested a human interpreter.' : T().interp + ' ✓') : 'Clinician requested an interpreter.', true); break;
  }
}

// ---------- layout / chrome ----------
function relabel() {
  $('roleLbl').textContent = isDoc ? 'Clinician' : (T().you);
  $('langLbl').textContent = isDoc ? `Patient · ${NAMES[patLang]}` : NAMES[patLang];
  const p = $('peerLbl'); p.classList.toggle('on', peerOnline);
  p.querySelector('span').textContent = peerOnline ? (isDoc ? 'Patient connected' : (T().doctorSays + ' ✓')) : (isDoc ? 'Waiting for patient' : '…');
  $('txt').placeholder = T().type;
  $('empty').innerHTML = isDoc ? '<b>Ready when you are</b>Tap the microphone and speak in English. Your patient reads and hears you in their language.' : `<b>${esc(T().title)}</b>${esc(T().empty)}`;
  if (!isDoc) {
    $('topRight').innerHTML = `<button class="btn" id="bPref">⚙ ${esc(T().prefs)}</button><button class="btn" id="bInt">🙋 ${esc(T().interp)}</button>`;
    $('bPref').onclick = openPrefs; $('bInt').onclick = () => send({type: 'interpreter'});
    renderQuick();
  } else {
    $('topRight').innerHTML = `<button class="btn" id="bInt">Request interpreter</button>`;
    $('bInt').onclick = () => send({type: 'interpreter'});
  }
  updateMicUi();
}
function applyPrefsClasses() { document.body.dataset.len = prefs.length; renderQuick(); Object.values(msgs).length; msgs.forEach(renderMsg); }
function renderQuick() {
  const q = $('quick');
  if (isDoc) { q.innerHTML = ''; return; }
  q.innerHTML = prefs.mode === 'interactive' ? (QUICK[patLang] || []).map(k => `<button data-k="${k}">${esc(T()[k])}</button>`).join('') : '';
  q.querySelectorAll('button').forEach(b => b.onclick = () => sendText(T()[b.dataset.k]));
}
function banner(text, alert) { const b = $('banner'); b.hidden = false; b.className = 'banner' + (alert ? ' alert' : ''); b.textContent = text; if (alert) setTimeout(() => b.hidden = true, 9000); }

function openPrefs(first) {
  const seg = (k, opts) => `<div class="lbl">${esc(T()[k])}</div><div class="seg" data-k="${k === 'length' ? 'length' : k === 'tone' ? 'tone' : 'mode'}">${opts.map(o => `<button data-v="${o}" class="${prefs[k === 'length' ? 'length' : k === 'tone' ? 'tone' : 'mode'] === o ? 'on' : ''}">${esc(T()[o])}</button>`).join('')}</div>`;
  $('sheet').innerHTML = `<h2>${esc(T().prefs)}</h2><p>${esc(T().read)}</p>
   ${seg('length', ['brief', 'detailed'])}${seg('tone', ['direct', 'empathetic'])}${seg('mode', ['interactive', 'informational'])}
   <div class="toggle"><span>🔊 ${esc(T().read)}</span><button class="sw ${readAloud ? 'on' : ''}" id="swRead"></button></div>
   <div class="lbl" style="margin-top:14px">Language</div><div class="seg" id="langSeg">${['es', 'hi', 'zh'].map(l => `<button data-l="${l}" class="${l === patLang ? 'on' : ''}">${NAMES[l]}</button>`).join('')}</div>
   <button class="btn primary" style="width:100%;padding:12px" id="pdone">${esc(T().done)}</button>`;
  $('modal').hidden = false;
  $('sheet').querySelectorAll('.seg[data-k] button').forEach(b => b.onclick = () => { prefs[b.parentElement.dataset.k] = b.dataset.v; sendPrefs(); b.parentElement.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); applyPrefsClasses(); });
  $('langSeg').querySelectorAll('button').forEach(b => b.onclick = () => { myLang = b.dataset.l; localStorage.mb_lang = myLang; patLang = myLang; sendPrefs(); stopRec(); relabel(); openPrefs(); });
  $('swRead').onclick = e => { readAloud = !readAloud; e.currentTarget.classList.toggle('on', readAloud); if (!readAloud) speechSynthesis.cancel(); };
  $('pdone').onclick = () => $('modal').hidden = true;
}
function languageGate() {
  $('sheet').innerHTML = `<h2>MedBridge</h2><p>Choose your language · Elija su idioma · अपनी भाषा चुनें</p><div class="langs">${['es', 'hi', 'zh'].map(l => `<button data-l="${l}">${NAMES[l]}<span>→</span></button>`).join('')}</div>`;
  $('modal').hidden = false;
  $('sheet').querySelectorAll('button').forEach(b => b.onclick = () => { myLang = patLang = b.dataset.l; localStorage.mb_lang = myLang; $('modal').hidden = true; sendPrefs(); relabel(); });
}

// ---------- rendering ----------
const feed = $('feed');
function scroll() { feed.scrollTop = feed.scrollHeight; }
function ensure(id, mine) {
  let w = els.get(id);
  if (!w) { w = document.createElement('div'); w.className = 'msg ' + (mine ? 'mine' : 'theirs'); els.set(id, w); feed.appendChild(w); $('empty').style.display = 'none'; }
  return w;
}
const done = new Set();
function showLive(id, speaker, text, translation) {
  const mine = speaker === role;
  const w = ensure('live:' + speaker, mine);
  // listener sees translation in grey; speaker sees own transcript (so mis-heard numbers are visible)
  const main = mine ? text : translation;
  w.innerHTML = `<div class="who">${whoLabel(speaker)} · live</div><div class="bubble live"><div class="main">${esc(main)}</div>${!mine && isDoc ? `<div class="sub">${esc(text)}</div>` : ''}</div>`;
  scroll();
}
function markChecking(id, text) { const w = ensure('live:' + role, true); w.innerHTML = `<div class="who">${whoLabel(role)}</div><div class="bubble live checking"><div class="main">${esc(text)}</div></div>`; }
function whoLabel(sp) { return isDoc ? (sp === 'doctor' ? 'You' : 'Patient') : (sp === 'patient' ? T().you : T().doctorSays); }
function removeLive(speaker) { const w = els.get('live:' + speaker); if (w) { w.remove(); els.delete('live:' + speaker); } }

function onFinal(m, lead) {
  done.add(m.id);
  m.lead = lead || m.lead;
  removeLive(m.speaker);
  const prev = msgs.get(m.id); msgs.set(m.id, {...(prev || {}), ...m});
  renderMsg(msgs.get(m.id)); renderSide(); scroll();
  if (m.speaker === role) { floor('idle'); }
  if (!isDoc && m.speaker === 'doctor' && m.status !== 'red') speakMsg(msgs.get(m.id));
  if (isDoc && m.speaker === 'patient') speakMsg(msgs.get(m.id));
}

function renderAll() { feed.querySelectorAll('.msg').forEach(e => e.remove()); els.clear(); msgs.forEach(renderMsg); renderSide(); relabel(); applyPrefsClasses(); scroll(); }

function dot(m) { return `<i class="dot ${m.status}"></i>`; }
function renderMsg(m) {
  const mine = m.speaker === role;
  const w = ensure(m.id, mine);
  const status = m.status;
  let html = '';
  const redP = !isDoc && status === 'red';
  if (isDoc) {
    // clinician view
    if (mine) {
      html = `<div class="who">You ${dot(m)}</div><div class="bubble ${status}"><div class="main">${esc(m.text)}</div><div class="sub">${NAMES[m.tgt_lang]}: ${esc(m.translation)}</div>${m.back ? `<div class="sub">↺ Back-translation: “${esc(m.back)}”</div>` : ''}</div>`;
    } else {
      html = `<div class="who">Patient ${dot(m)}</div><div class="bubble ${status}"><div class="main">${esc(m.translation)}</div><div class="sub">Original · ${esc(m.text)}</div></div>${chips(m)}`;
    }
  } else {
    const T_ = T();
    if (mine) {
      html = `<div class="who">${esc(T_.you)}</div><div class="bubble"><div class="main">${esc(m.text)}</div></div>`;
    } else {
      const facts = prefs.length === 'detailed' && (m.facts || []).length ? `<div class="chips facts">${m.facts.map(f => `<span class="chip">${esc(f[0])} ${esc(f[1])}</span>`).join('')}</div>` : '';
      html = `${m.lead ? `<div class="lead">💚 ${esc(m.lead)}</div>` : ''}<div class="who">${esc(T_.doctorSays)} ${dot(m)}</div>
      <div class="bubble ${status === 'retracted' ? 'retracted' : redP ? 'red' : ''}"><div class="main">${esc(m.translation)}</div></div>
      ${redP ? `<div class="confirming">⚠ ${esc(T_.confirming)}</div>` : ''}${status === 'retracted' ? `<div class="confirming">${esc(T_.retract)}</div>` : ''}${status === 'confirmed' ? `<div class="chips"><span class="chip ok">✓ ${esc(T_.confirmed)}</span></div>` : ''}${facts}`;
    }
  }
  w.className = 'msg ' + (mine ? 'mine' : 'theirs');
  w.innerHTML = html;
}
function chips(m) {
  const c = [];
  (m.emotions || []).forEach(e => c.push(`<span class="chip emo">♥ ${e.category} · ${e.intensity} · “${esc(e.span)}”</span>`));
  (m.flags || []).filter(f => f.kind === 'culture').forEach(f => c.push(`<span class="chip warn">◇ Ambiguous: ${esc(f.span)}</span>`));
  (m.flags || []).filter(f => f.kind === 'emotion').forEach(f => c.push(`<span class="chip warn">${esc(f.reason)}</span>`));
  return c.length ? `<div class="chips">${c.join('')}</div>` : '';
}

// ---------- doctor sidebar ----------
function renderSide() {
  if (!isDoc) { $('side').style.display = 'none'; $('layout').classList.add('solo'); return; }
  const all = [...msgs.values()];
  const open = all.filter(m => m.status !== 'confirmed' && m.status !== 'retracted' && (m.flags || []).some(f => f.level !== 'info' && f.kind !== 'emotion'));
  const cards = open.map(m => (m.flags || []).filter(f => f.level !== 'info' && f.kind !== 'emotion').map(f => flagCard(m, f)).join('')).join('');
  const lastDoc = all.map(m => m.speaker).lastIndexOf('doctor');
  const concerns = all.filter((m, i) => i > lastDoc && m.speaker === 'patient' && ((m.emotions || []).length || /[?¿？]/.test(m.text) || (m.flags || []).some(f => f.kind === 'culture')));
  const infos = all.slice(-3).flatMap(m => (m.flags || []).filter(f => f.level === 'info').map(f => `<div class="flag info"><b>ℹ ${esc(f.reason)}</b></div>`));
  $('side').innerHTML = `
  <div class="card"><h4>Needs attention <span class="chip ${open.length ? 'red' : 'ok'}">${open.length || '✓'}</span></h4>${cards || '<div class="none">All clear — no safety or cultural flags.</div>'}${infos.slice(-2).join('')}</div>
  <div class="card"><h4>Patient concerns</h4>${concerns.length ? concerns.map(m => `<div class="concern">“${esc(m.translation)}”<div class="sub" style="color:var(--mute);font-size:12px">${(m.emotions || []).map(e => e.category + ' · ' + e.intensity).join(', ')}</div></div>`).join('') : '<div class="none">No unanswered concerns.</div>'}</div>
  <div class="card"><h4>Say it with warmth</h4><div class="emp">${EMP.map(([k, t]) => `<button data-emp="${k}">${t}</button>`).join('')}</div></div>
  <div class="card"><h4>Controls</h4>
   <div class="toggle"><span>🔊 Read patient replies aloud</span><button class="sw ${readAloud ? 'on' : ''}" id="swRead"></button></div>
   <div class="toggle"><span>🧪 Demo: inject translation error</span><button class="sw ${inject ? 'on' : ''}" id="swInj"></button></div>
   <div class="sub" style="font-size:12px;color:var(--mute);margin-top:10px">Patient style: ${esc(prefs.tone)} · ${esc(prefs.length)} · ${esc(prefs.mode)}</div></div>`;
  $('side').querySelectorAll('[data-emp]').forEach(b => b.onclick = () => send({type: 'empathy', key: b.dataset.emp}));
  $('side').querySelectorAll('[data-confirm]').forEach(b => b.onclick = () => send({type: 'confirm', id: b.dataset.confirm}));
  $('side').querySelectorAll('[data-reph]').forEach(b => b.onclick = () => { send({type: 'rephrase', id: b.dataset.reph}); $('txt').value = msgs.get(b.dataset.reph).text; $('txt').focus(); });
  $('side').querySelectorAll('[data-clar]').forEach(b => b.onclick = () => send({type: 'clarify', span: b.dataset.clar, en: b.dataset.q}));
  $('swRead').onclick = () => { readAloud = !readAloud; if (!readAloud) speechSynthesis.cancel(); renderSide(); };
  $('swInj').onclick = () => send({type: 'inject', on: !inject});
}
function flagCard(m, f) {
  const icon = f.level === 'red' ? '⚠' : '◇';
  let acts = '';
  if (f.kind === 'safety') acts = `<div class="acts"><button class="btn sm primary" data-confirm="${m.id}">Confirm &amp; correct</button><button class="btn sm" data-reph="${m.id}">Rephrase</button></div>`;
  if (f.kind === 'culture') acts = `<div class="acts"><button class="btn sm primary" data-clar="${esc(f.span)}" data-q="${esc(f.suggestion || '')}">Ask: “${esc(f.suggestion || '')}”</button></div>`;
  const tag = f.level === 'red' ? 'Needs human review' : f.kind === 'tone' ? 'Tone' : 'Check meaning';
  return `<div class="flag ${f.level}"><b>${icon} ${esc(f.reason)}</b><div class="span">“${esc(f.span)}” · ${tag}</div>${f.kind === 'safety' && f.suggestion ? `<div>${esc(f.suggestion)}</div>` : ''}${acts}</div>`;
}

// ---------- sending ----------
let curId = null;
const newId = () => Math.random().toString(36).slice(2, 10);
function sendText(t) { t = (t || '').trim(); if (!t) return; floor('idle'); send({type: 'speech', id: newId(), text: t, is_final: true}); }
$('send').onclick = () => { sendText($('txt').value); $('txt').value = ''; };
$('txt').onkeydown = e => { if (e.key === 'Enter') { sendText($('txt').value); $('txt').value = ''; } };

// ---------- floor control: audio never overlaps between devices ----------
let myFloor = 'idle', peerFloor = 'idle', peerTimer = null, lastHeard = 0;
let lastFloorSent = 0;
function floor(s) {
  const now = Date.now();
  // 'speaking' is re-sent as a heartbeat (~1/s) so the other device keeps its mic closed for the whole turn
  if (s !== myFloor || (s === 'speaking' && now - lastFloorSent > 1000)) { myFloor = s; lastFloorSent = now; send({type: 'floor', state: s}); }
}
function onPeerFloor(s) {
  peerFloor = s; clearTimeout(peerTimer);
  if (s === 'speaking') { if (myFloor !== 'speaking') suspendMic(); peerTimer = setTimeout(() => { peerFloor = 'idle'; resumeMic(); pumpTts(); updateMicUi(); }, 3000); }
  if (s === 'tts') { suspendMic(); peerTimer = setTimeout(() => { peerFloor = 'idle'; resumeMic(); }, 25000); }
  if (s === 'idle') { setTimeout(() => { resumeMic(); updateMicUi(); }, 700); pumpTts(); }
  updateMicUi();
}

// ---------- TTS (natural voice, queued, sentence-chunked) ----------
let voices = [], ttsQ = [], ttsBusy = false;
function loadVoices() { voices = speechSynthesis.getVoices(); }
if ('speechSynthesis' in window) { loadVoices(); speechSynthesis.onvoiceschanged = loadVoices; }
function pickVoice(lang) {
  const pre = TTSL[lang].split('-')[0];
  const c = voices.filter(v => v.lang.toLowerCase().replace('_', '-').startsWith(pre));
  const score = v => (/natural|neural|premium|enhanced|siri/i.test(v.name) ? 4 : 0) + (/google/i.test(v.name) ? 3 : 0) + (v.localService ? 0 : 1) + (v.lang.replace('_', '-') === TTSL[lang] ? 2 : 0);
  return c.sort((a, b) => score(b) - score(a))[0];
}
function speakMsg(m) {
  if (!readAloud || !('speechSynthesis' in window)) return;
  const lang = isDoc ? 'en' : patLang;
  const lines = [];
  if (!isDoc && m.lead) lines.push(m.lead);
  lines.push(m.translation);
  lines.forEach(t => ttsQ.push({t, lang, id: m.id}));
  pumpTts();
}
function pumpTts() {
  if (ttsBusy || !ttsQ.length) return;
  if (peerFloor === 'speaking' || peerFloor === 'tts' || Date.now() - lastHeard < 1200 || myFloor === 'speaking') { setTimeout(pumpTts, 350); return; }
  const it = ttsQ.shift(); ttsBusy = true;
  const v = pickVoice(it.lang);
  if (!v && it.lang !== 'en' && voices.length) { noVoice(it.lang); ttsBusy = false; pumpTts(); return; }
  const u = new SpeechSynthesisUtterance(it.t); u.lang = TTSL[it.lang]; if (v) u.voice = v;
  u.rate = 0.96; u.pitch = 1;
  suspendMic(); floor('tts'); updateMicUi();
  let wd;
  const end = () => { clearTimeout(wd); if (!ttsBusy) return; ttsBusy = false; if (!ttsQ.length) { floor('idle'); setTimeout(resumeMic, 500); } updateMicUi(); pumpTts(); };
  u.onend = end; u.onerror = end;
  wd = setTimeout(() => { speechSynthesis.cancel(); end(); }, 3000 + it.t.length * 110);  // never let a stuck voice freeze the mic
  speechSynthesis.speak(u);
}
let warnedVoice = {};
function noVoice(l) { if (warnedVoice[l]) return; warnedVoice[l] = 1; banner(`No ${NAMES[l]} voice installed on this device — captions still work. (Install one in system Settings → Accessibility → Spoken Content.)`); }

// ---------- speech recognition ----------
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let rec = null, micWanted = false, suspended = false;
function micAllowed() { return micWanted && !ttsBusy && peerFloor !== 'tts' && (peerFloor !== 'speaking' || myFloor === 'speaking'); }
function startRec() {
  if (!SR) return;
  if (rec) return;
  rec = new SR(); rec.continuous = true; rec.interimResults = true; rec.lang = REC[myLang || 'en'];
  rec.onresult = e => {
    let interim = '', fin = '';
    for (let i = e.resultIndex; i < e.results.length; i++) { const r = e.results[i]; (r.isFinal ? (fin += r[0].transcript) : (interim += r[0].transcript)); }
    lastHeard = Date.now();
    if (interim || fin) { floor('speaking'); curId = curId || newId(); }
    if (fin) { send({type: 'speech', id: curId, text: fin.trim(), is_final: true}); curId = null; floor('idle'); }
    else if (interim) send({type: 'speech', id: curId, text: interim, is_final: false});
  };
  rec.onerror = e => { if (e.error === 'not-allowed') { micWanted = false; banner('Microphone blocked — type instead, or allow mic access.'); } };
  rec.onend = () => { rec = null; if (micAllowed()) setTimeout(startRec, 200); updateMicUi(); };
  try { rec.start(); } catch (e) { rec = null; }
}
function stopRec() { if (rec) { const r = rec; rec = null; r.onend = null; try { r.abort(); } catch (e) {} } }
function suspendMic() { stopRec(); }
function resumeMic() { if (micAllowed() && !rec) startRec(); updateMicUi(); }
function updateMicUi() {
  const m = $('mic'), s = $('micStatus'); if (!m) return;
  const held = micWanted && !micAllowed();
  m.classList.toggle('on', micWanted && !held); m.classList.toggle('hold', held);
  const t = T();
  s.innerHTML = held ? `⏸ ${esc(peerFloor === 'speaking' ? t.holdSpeak : t.paused)}` : micWanted ? `<b>● ${esc(t.listening)}</b>` : (SR ? esc(t.speak) : 'Speech not supported in this browser — type below (Chrome recommended)');
}
$('mic').onclick = () => {
  if (!SR) { banner('Speech recognition needs Chrome. You can still type.'); return; }
  if (!isDoc && !myLang) return;
  micWanted = !micWanted;
  if (micWanted) { speechSynthesis && speechSynthesis.cancel(); ttsBusy = false; startRec(); } else { stopRec(); floor('idle'); }
  updateMicUi();
};

// ---------- boot ----------
$('roleLbl').textContent = isDoc ? 'Clinician' : 'Patient';
relabel(); applyPrefsClasses();
if (!isDoc && !myLang) languageGate();
connect();
})();
