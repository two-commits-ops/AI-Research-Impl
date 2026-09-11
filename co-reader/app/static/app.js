const $ = (id) => document.getElementById(id);

pdfjsLib.GlobalWorkerOptions.workerSrc =
  'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

let docId = null;
let numPages = 0;
let currentPage = 1;      // page shown in the main viewer (what you're looking at)
let playingPage = null;   // page whose narration is loaded into mainAudio (what you're hearing)
let pdfDoc = null;
let readerStarted = false;
let pageRenderTask = null;
let renderRequest = 0;

const transcripts = {};       // page -> {text, sources, segments: [{text, audio_url}]}
let segmentQueue = [];
let segmentIndex = 0;
let autoAdvance = false;      // continuous reading: keep moving to the next page on its own

const mainAudio = $('audio-player');
const qaAudio = $('qa-audio');
let resumeAfterAnswer = false;
// While the mic is listening, a paused narration stays paused through as
// many follow-up questions as you like — it does not resume itself after
// each answer. It resumes only when you press the narrate button or turn
// the mic off.
let heldForConversation = false;

function setExperienceStatus(message, type = 'info') {
  const box = $('experience-status');
  if (!message) {
    box.textContent = '';
    box.classList.add('hidden');
    return;
  }
  box.textContent = message;
  box.classList.remove('hidden');
  box.classList.toggle('error', type === 'error');
}

async function fetchJson(url, options) {
  const resp = await fetch(url, options);
  let payload = null;
  try { payload = await resp.json(); } catch {}
  if (!resp.ok) {
    throw new Error(payload?.detail || `Request failed (${resp.status}).`);
  }
  return payload;
}

// ---------- persisted, lightweight per-viewer preferences ----------
function loadFixes() {
  try { return JSON.parse(localStorage.getItem('coreader_fixes') || '[]'); }
  catch { return []; }
}
function saveFixes(fixes) {
  try { localStorage.setItem('coreader_fixes', JSON.stringify(fixes)); } catch {}
}
let fixes = loadFixes();

// A character's customization has two independent parts — a rename (safe
// as a literal text substitution) and a gender override (NOT safe as a
// substitution — "he"/"she" are too short/common — so it's sent to the
// server as an instruction for the model's own word choice instead; see
// app/narrator.py's _gender_instruction). Either can be set without the
// other, so the entry is only dropped once both are back to nothing.
function upsertFix(find, patch) {
  const i = fixes.findIndex((f) => f.find.toLowerCase() === find.toLowerCase());
  const current = i >= 0 ? fixes[i] : { find, replace: '', gender: '' };
  const updated = { ...current, ...patch };
  if (!updated.replace && !updated.gender) {
    if (i >= 0) fixes.splice(i, 1);
  } else if (i >= 0) {
    fixes[i] = updated;
  } else {
    fixes.push(updated);
  }
  saveFixes(fixes);
}

// ---------- screens ----------
function showScreen(name) {
  for (const s of ['upload', 'processing', 'summary', 'reading']) {
    $(`screen-${s}`).classList.toggle('hidden', s !== name);
  }
  $('home-btn').classList.toggle('hidden', name === 'upload');
}

// ---------- home: leave this document, upload a different one ----------
// Reachable by clicking the button, or by voice/typed command ("go home",
// "start over", "upload a new document") — see go_home in askQuestion.
function goHome() {
  mainAudio.pause();
  qaAudio.pause();
  if (recognition && listening) { listening = false; recognition.stop(); }
  docId = null;
  numPages = 0;
  currentPage = 1;
  playingPage = null;
  pdfDoc = null;
  readerStarted = false;
  segmentQueue = [];
  segmentIndex = 0;
  autoAdvance = false;
  resumeAfterAnswer = false;
  heldForConversation = false;
  wrapupShown = false;
  Object.keys(transcripts).forEach((k) => delete transcripts[k]);
  summaryAudioUrl = null;
  $('file-input').value = '';
  $('qa-log').innerHTML = '';
  showScreen('upload');
}
$('home-btn').addEventListener('click', goHome);

// ---------- upload ----------
$('choose-btn').addEventListener('click', () => $('file-input').click());
$('file-input').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const form = new FormData();
  form.append('file', file);
  showScreen('processing');
  try {
    const data = await fetchJson('/api/upload', { method: 'POST', body: form });
    docId = data.doc_id;
    numPages = data.num_pages;
    $('start-reading-early-btn').disabled = false;
    waitForSummary();
  } catch (err) {
    showScreen('upload');
    alert(`Could not open this PDF: ${err.message}`);
  }
});

async function waitForSummary() {
  const resp = await fetch(`/api/${docId}/summary`);
  const s = await resp.json();
  if (s.ready) {
    if (readerStarted) return;
    $('summary-text').textContent = s.text;
    if (s.terms_ready) {
      renderTermsReview(s.terms || []);
    } else {
      // Character detection runs in parallel with the overview and is
      // frequently not done the moment the overview is — showing the
      // overview right away (rather than waiting on both) is the point,
      // but that means checking again for characters a beat later,
      // instead of only ever looking once and treating "not done yet" as
      // "none found".
      pollForTerms();
    }
    showScreen('summary');
  } else {
    setTimeout(waitForSummary, 500);
  }
}

async function pollForTerms() {
  if (readerStarted) return;
  const resp = await fetch(`/api/${docId}/summary`);
  const s = await resp.json();
  if (s.terms_ready) {
    renderTermsReview(s.terms || []);
  } else {
    setTimeout(pollForTerms, 500);
  }
}

$('start-reading-early-btn').addEventListener('click', () => openReader());

const GENDER_OPTIONS = [
  { value: '', label: 'As written' },
  { value: 'male', label: 'Male (he/him)' },
  { value: 'female', label: 'Female (she/her)' },
];

function renderTermsReview(terms) {
  const box = $('terms-review');
  if (!terms.length) { box.classList.add('hidden'); return; }
  box.classList.remove('hidden');
  $('terms-list').innerHTML = terms
    .map((term, i) => {
      // A detected gender pre-selects that option — still just a starting
      // point, not a fact the reader is stuck with; "As written" (blank)
      // always means "don't touch pronouns", even if one was detected.
      const detected = term.gender === 'male' || term.gender === 'female' ? term.gender : '';
      const options = GENDER_OPTIONS.map(
        (o) => `<option value="${o.value}"${o.value === detected ? ' selected' : ''}>${o.label}</option>`
      ).join('');
      return `
      <div class="term-row">
        <span class="term-name">${escapeHtml(term.name)}</span>
        ${term.description ? `<span class="term-desc">${escapeHtml(term.description)}</span>` : ''}
        <div class="term-controls">
          <input data-term="${escapeAttr(term.name)}" data-field="replace" placeholder="say instead (optional)" id="term-input-${i}">
          <select data-term="${escapeAttr(term.name)}" data-field="gender" id="term-gender-${i}">${options}</select>
        </div>
      </div>`;
    })
    .join('');
  // A detected gender is sent as the active fix right away (so it takes
  // effect even if the reader never touches the dropdown), not just kept
  // as a placeholder for a change event that may never fire.
  terms.forEach((term) => {
    if (term.gender === 'male' || term.gender === 'female') {
      upsertFix(term.name, { gender: term.gender });
    }
  });
  box.querySelectorAll('[data-term]').forEach((el) => {
    el.addEventListener('change', () => {
      const value = el.tagName === 'SELECT' ? el.value : el.value.trim();
      upsertFix(el.dataset.term, { [el.dataset.field]: value });
    });
  });
}

// ---------- summary screen ----------
let summaryAudioUrl = null;

function isSummaryAudioActive() {
  return summaryAudioUrl && mainAudio.currentSrc.endsWith(summaryAudioUrl);
}

function updateSummaryPlayIcon() {
  const playing = isSummaryAudioActive() && !mainAudio.paused && !mainAudio.ended;
  $('summary-play-btn').innerHTML = playing ? '&#10074;&#10074;' : '&#9658;';
}

$('summary-play-btn').addEventListener('click', async () => {
  try {
    if (isSummaryAudioActive() && !mainAudio.paused) {
      mainAudio.pause();
      return;
    }
    if (isSummaryAudioActive() && mainAudio.paused && !mainAudio.ended) {
      // Already loaded, just paused partway through — resume from there
      // rather than reassigning .src, which would restart it from 0.
      playSafely(mainAudio, () => { $('summary-audio-label').textContent = 'Your browser blocked playback. Tap play once more.'; });
      $('summary-audio-label').textContent = 'Playing…';
      return;
    }
    if (!summaryAudioUrl) {
      $('summary-audio-label').textContent = 'Creating audio…';
      const data = await fetchJson(`/api/${docId}/summary/audio?tone=${currentTone()}`);
      summaryAudioUrl = data.audio_url;
    }
    mainAudio.src = summaryAudioUrl;
    playSafely(mainAudio, () => { $('summary-audio-label').textContent = 'Your browser blocked playback. Tap play once more.'; });
    $('summary-audio-label').textContent = 'Playing…';
  } catch (err) {
    $('summary-audio-label').textContent = `Audio unavailable: ${err.message}`;
  }
});
mainAudio.addEventListener('play', updateSummaryPlayIcon);
mainAudio.addEventListener('pause', () => {
  updateSummaryPlayIcon();
  if (isSummaryAudioActive() && !mainAudio.ended) {
    $('summary-audio-label').textContent = 'Paused — tap to resume';
  }
});
mainAudio.addEventListener('ended', () => {
  updateSummaryPlayIcon();
  if (summaryAudioUrl && mainAudio.currentSrc.endsWith(summaryAudioUrl)) {
    $('summary-audio-label').textContent = 'Play the overview';
  }
});

async function openReader() {
  mainAudio.pause();
  readerStarted = true;
  showScreen('reading');
  try {
    if (!pdfDoc) {
      setExperienceStatus('Loading the PDF…');
      const loadingTask = pdfjsLib.getDocument(`/api/${docId}/pdf`);
      pdfDoc = await loadingTask.promise;
    }
    currentPage = 1;
    await renderPage(currentPage);
    setExperienceStatus('');
    // The whole point of pressing this one button is a hands-off listen —
    // start reading immediately rather than making that a second click.
    autoAdvance = true;
    startNarration(currentPage);
  } catch (err) {
    setExperienceStatus(`Could not display this PDF: ${err.message}`, 'error');
  }
}

$('start-reading-btn').addEventListener('click', openReader);

// ---------- reading screen: navigation ----------
$('prev-btn').addEventListener('click', () => {
  if (currentPage > 1) { currentPage -= 1; renderPage(currentPage); }
});
$('next-btn').addEventListener('click', () => {
  if (currentPage < numPages) { currentPage += 1; renderPage(currentPage); }
});

async function renderPage(pageNum) {
  const request = ++renderRequest;
  $('page-indicator').textContent = `page ${pageNum} / ${numPages}`;
  $('prev-btn').disabled = pageNum <= 1;
  $('next-btn').disabled = pageNum >= numPages;

  // The main viewer always shows the real PDF page — forward or back.
  await renderPdfPage(pageNum, request);
  if (request !== renderRequest) return;

  // The sidebar caption tracks whatever page you're looking at: already
  // narrated pages show their narration again; a fresh page clears it.
  // Exception: the page currently being narrated owns its own caption via
  // the live streaming reveal (beginCaptionReveal) — this render can
  // resolve AFTER that reveal has already started (a real race during
  // auto-advance, since a prefetched page's narrate() call often returns
  // faster than this PDF canvas render does), and touching the caption
  // here would stomp the in-progress reveal with the whole dumped text.
  if (pageNum !== playingPage) {
    const cached = transcripts[pageNum];
    renderCaption(cached ? pageNum : null, cached ? cached.text : null, cached ? cached.sources : null);
  }
  updateNarrateButton();

  // Includes whatever character renames are active right now, so the
  // background prefetch bakes them in from the start instead of buffering
  // audio with the original names that then has to be redone.
  const replacementsParam = encodeURIComponent(JSON.stringify(fixes));
  fetch(`/api/${docId}/touch?page=${pageNum}&tone=${currentTone()}&replacements_json=${replacementsParam}`, { method: 'POST' }).catch(() => {});
}

async function renderPdfPage(pageNum, request) {
  const page = await pdfDoc.getPage(pageNum);
  if (request !== renderRequest) return;
  const canvas = $('pdf-canvas');
  const containerWidth = canvas.parentElement.clientWidth - 4;
  const unscaled = page.getViewport({ scale: 1 });
  const scale = containerWidth / unscaled.width;
  const viewport = page.getViewport({ scale });
  canvas.width = viewport.width;
  canvas.height = viewport.height;
  const ctx = canvas.getContext('2d');
  if (pageRenderTask) {
    try { pageRenderTask.cancel(); } catch {}
  }
  pageRenderTask = page.render({ canvasContext: ctx, viewport });
  try {
    await pageRenderTask.promise;
  } catch (err) {
    if (err?.name !== 'RenderingCancelledException') throw err;
  }
}

// ---------- narration (the sidebar companion — what you're hearing) ----------
function currentTone() {
  return $('tone-select').value;
}

function renderCaption(page, text, sources) {
  revealText = null; // browsing to a page shows its caption whole, not mid-reveal
  $('narration-title').textContent = page ? `Co-Reader — page ${page}` : 'Co-Reader';
  $('caption-box').innerHTML = text
    ? escapeHtml(text)
    : '<span class="caption-placeholder">Narration will appear here as it plays.</span>';
  renderCaptionSources(sources);
}

function renderCaptionSources(sources) {
  const row = $('sources-row');
  if (sources && sources.length) {
    row.classList.remove('hidden');
    row.innerHTML = sources
      .map((s) => `<a href="${escapeAttr(s.url)}" target="_blank" rel="noopener">${escapeHtml(s.title)}</a>`)
      .join('');
  } else {
    row.classList.add('hidden');
    row.innerHTML = '';
  }
}

// ---------- caption reveal: text appears as it's spoken, not dumped all at once ----------
let revealText = null; // the full caption text this playback is revealing
let revealSegmentCount = 1;

function beginCaptionReveal(page, text, sources) {
  $('narration-title').textContent = page ? `Co-Reader — page ${page}` : 'Co-Reader';
  renderCaptionSources(sources);
  revealText = text || '';
  revealSegmentCount = Math.max(segmentQueue.length, 1);
  $('caption-box').innerHTML = '<span class="caption-cursor"></span>';
}

mainAudio.addEventListener('timeupdate', () => {
  if (!revealText) return;
  const withinSegment = mainAudio.duration ? mainAudio.currentTime / mainAudio.duration : 0;
  const fraction = Math.min((segmentIndex + withinSegment) / revealSegmentCount, 1);
  const shown = revealText.slice(0, Math.floor(revealText.length * fraction));
  $('caption-box').innerHTML = escapeHtml(shown) + (fraction < 1 ? '<span class="caption-cursor"></span>' : '');
});

function updateNarrateButton() {
  const btn = $('narrate-btn');
  const isThisPagePlaying = playingPage === currentPage && !mainAudio.paused && !mainAudio.ended;
  const isThisPagePaused = playingPage === currentPage && mainAudio.paused && mainAudio.currentTime > 0 && !mainAudio.ended;
  btn.classList.toggle('playing', isThisPagePlaying);
  $('interrupt-btn').classList.toggle('hidden', !isThisPagePlaying);
  if (isThisPagePlaying) {
    btn.innerHTML = '&#10074;&#10074; Stop';
  } else if (isThisPagePaused) {
    btn.innerHTML = '&#9658; Resume narration';
  } else if (transcripts[currentPage]) {
    btn.innerHTML = '&#9658; Play again';
  } else {
    btn.innerHTML = '&#9658; Narrate this page';
  }
}

function playSafely(audioEl, onBlocked) {
  const p = audioEl.play();
  if (p && p.catch) {
    p.catch(() => { if (onBlocked) onBlocked(); });
  }
}

mainAudio.addEventListener('error', () => {
  setExperienceStatus('The audio file could not play. Check your output device, then try again.', 'error');
});
qaAudio.addEventListener('error', () => {
  setExperienceStatus('The answer was ready, but its audio could not play. You can still read it below.', 'error');
  resumeIfNeeded();
});

function interruptNarrationForQuestion() {
  if (!mainAudio.paused && !mainAudio.ended) {
    mainAudio.pause();
    resumeAfterAnswer = true;
  }
}

function stopAnswerPlayback() {
  qaAudio.pause();
  qaAudio.removeAttribute('src');
  qaAudio.load();
}

function playCurrentSegment() {
  const seg = segmentQueue[segmentIndex];
  if (!seg) return;
  mainAudio.src = seg.audio_url;
  playSafely(mainAudio, () => {
    // The browser blocked autoplay (this can happen if generating took long
    // enough that the original click's permission expired) — one more tap
    // on the now-ready audio will play instantly.
    $('narrate-btn').innerHTML = '&#9658; Tap to play';
    setExperienceStatus('Your browser blocked playback. Tap narration again to start the ready audio.', 'error');
  });
}

async function startNarration(page) {
  // Narration and an answer must never play at the same time.
  stopAnswerPlayback();
  // Only trust the cache if it's in the voice you're actually listening
  // to right now — otherwise a page that happened to get buffered in the
  // background before you changed the tone would keep playing back in
  // the old voice forever. A tone change always gets a fresh fetch (which
  // itself hits the server's own per-tone cache, so it's still instant
  // once that tone has been generated for this page before).
  if (transcripts[page] && transcripts[page].tone === currentTone()) {
    // Already generated on an earlier visit — play immediately, no round trip.
    playingPage = page;
    segmentQueue = transcripts[page].segments;
    segmentIndex = 0;
    beginCaptionReveal(page, transcripts[page].text, transcripts[page].sources);
    playCurrentSegment();
    return;
  }

  const btn = $('narrate-btn');
  const wasCurrentPage = page === currentPage;
  if (wasCurrentPage) {
    btn.innerHTML = 'Preparing audio&hellip;';
    btn.disabled = true;
    setExperienceStatus('Writing a short explanation, then creating audio…');
  }
  try {
    const data = await fetchJson(`/api/${docId}/narrate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page, tone: currentTone(), replacements: fixes }),
    });
    if (!data.segments?.length) throw new Error('The server did not return playable audio.');
    transcripts[page] = { text: data.text, sources: data.sources, segments: data.segments, tone: currentTone() };
    playingPage = page;
    segmentQueue = data.segments;
    segmentIndex = 0;
    beginCaptionReveal(page, data.text, data.sources);
    playCurrentSegment();
    setExperienceStatus('');
  } catch (err) {
    if (wasCurrentPage) {
      setExperienceStatus(`Could not start narration: ${err.message}`, 'error');
      btn.innerHTML = '&#9658; Try narration again';
    }
  } finally {
    if (wasCurrentPage) btn.disabled = false;
  }
}

$('narrate-btn').addEventListener('click', () => {
  const isThisPagePlaying = playingPage === currentPage && !mainAudio.paused && !mainAudio.ended;
  if (isThisPagePlaying) {
    mainAudio.pause();
    autoAdvance = false; // an explicit stop ends the continuous-reading chain
    updateNarrateButton();
    return;
  }
  const isThisPagePaused = playingPage === currentPage && mainAudio.paused && mainAudio.currentTime > 0 && !mainAudio.ended;
  autoAdvance = true; // starting (or resuming) narration means "keep going" by default
  if (isThisPagePaused) {
    heldForConversation = false; // explicit button press always resumes
    playSafely(mainAudio);
    return;
  }
  startNarration(currentPage);
});

mainAudio.addEventListener('play', updateNarrateButton);
mainAudio.addEventListener('pause', updateNarrateButton);

mainAudio.addEventListener('ended', () => {
  if (segmentIndex < segmentQueue.length - 1) {
    segmentIndex += 1;
    playCurrentSegment();
    return;
  }
  // Whole page finished — continue to the next page when continuous reading
  // is on. Its narration is generated only when needed so it never steals
  // priority from a current question or play request.
  updateNarrateButton();
  if (playingPage === numPages && !wrapupShown) {
    wrapupShown = true;
    showWrapUp();
  } else if (autoAdvance && playingPage && playingPage < numPages) {
    const next = playingPage + 1;
    currentPage = next;
    renderPage(next);
    startNarration(next);
  } else {
    autoAdvance = false;
  }
});

// ---------- wrap-up: reached the last page ----------
let wrapupShown = false;

async function showWrapUp() {
  autoAdvance = false;
  try {
    const data = await fetchJson(`/api/${docId}/wrapup?tone=${currentTone()}`);
    renderCaptionSources(null);
    $('narration-title').textContent = "You're all caught up";
    $('caption-box').innerHTML =
      escapeHtml(data.text) +
      '<div class="wrapup-actions">' +
      '<button type="button" id="wrapup-ask-btn">Ask a question</button>' +
      '<button type="button" id="wrapup-home-btn">Upload a new document</button>' +
      '</div>';
    $('wrapup-ask-btn').addEventListener('click', () => $('ask-input').focus());
    $('wrapup-home-btn').addEventListener('click', goHome);
    mainAudio.src = data.audio_url;
    playSafely(mainAudio);
  } catch (err) {
    // Non-critical — the listener already heard the whole document either way.
  }
}

// ---------- interrupt narration, ask, then auto-resume ----------

$('interrupt-btn').addEventListener('click', () => {
  interruptNarrationForQuestion();
  $('ask-input').focus();
});

function resumeIfNeeded() {
  if (heldForConversation) return; // stays paused through follow-up questions
  if (resumeAfterAnswer && mainAudio.paused && !mainAudio.ended && mainAudio.currentTime > 0) {
    playSafely(mainAudio, () => { $('narrate-btn').innerHTML = '&#9658; Tap to resume'; });
  }
  resumeAfterAnswer = false;
}
qaAudio.addEventListener('ended', resumeIfNeeded);

// ---------- sidebar Q&A ----------
function addQaBubble(question) {
  const log = $('qa-log');
  const qDiv = document.createElement('div');
  qDiv.className = 'qa-q';
  qDiv.textContent = question;
  log.appendChild(qDiv);
  const pending = document.createElement('div');
  pending.className = 'qa-pending';
  pending.textContent = 'thinking…';
  log.appendChild(pending);
  log.scrollTop = log.scrollHeight;
  return pending;
}

async function askQuestion(question) {
  // A question always owns the audio channel. This also handles typed
  // questions, which previously could overlap with page narration.
  interruptNarrationForQuestion();
  stopAnswerPlayback();
  setExperienceStatus('Thinking…');
  const pending = addQaBubble(question);
  // Say something immediately — "let me check" — rather than leaving dead
  // air while the real answer is still being generated.
  fetch(`/api/filler?tone=${currentTone()}`)
    .then((r) => (r.ok ? r.json() : null))
    .then((data) => {
      if (data?.audio_url) {
        qaAudio.src = data.audio_url;
        playSafely(qaAudio);
      }
    })
    .catch(() => {});
  try {
    const data = await fetchJson(`/api/${docId}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page: currentPage, question, tone: currentTone(), replacements: fixes }),
    });
    pending.className = 'qa-a';
    pending.textContent = data.answer;
    if (data.sources && data.sources.length) {
      const srcDiv = document.createElement('div');
      srcDiv.className = 'qa-sources';
      srcDiv.innerHTML = data.sources
        .map((s) => `<a href="${escapeAttr(s.url)}" target="_blank" rel="noopener">${escapeHtml(s.title)}</a>`)
        .join('');
      pending.appendChild(srcDiv);
    }
    if (data.go_home) {
      goHome();
    } else if (data.navigate_to && data.navigate_to !== currentPage) {
      // Navigation replaces the previous narration immediately; do not also
      // play a spoken confirmation over the destination page.
      resumeAfterAnswer = false;
      currentPage = data.navigate_to;
      await renderPage(currentPage);
      startNarration(currentPage);
    } else {
      qaAudio.src = data.audio_url;
      playSafely(qaAudio);
    }
    setExperienceStatus('');
  } catch (err) {
    resumeIfNeeded();
    pending.className = 'qa-a';
    pending.textContent = `Something went wrong: ${err.message}`;
    setExperienceStatus(`Could not answer the question: ${err.message}`, 'error');
  }
  $('qa-log').scrollTop = $('qa-log').scrollHeight;
}

$('ask-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const input = $('ask-input');
  const q = input.value.trim();
  if (!q) return;
  input.value = '';
  askQuestion(q);
});

$('reexplain-btn').addEventListener('click', () => {
  askQuestion('Please re-explain this page, in a different way.');
});

// ---------- voice: press the mic, talk anytime, it barges in and answers ----------
// Uses the browser's built-in speech recognition (Web Speech API) — no
// server, no separate API key. In Chrome this routes audio through
// Google's recognition service to produce the transcript; nothing else
// about the app's local-first design changes.
let recognition = null;
let listening = false;

function getRecognition() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return null;
  const r = new SR();
  r.continuous = true;
  r.interimResults = true;
  r.lang = 'en-US';
  r.onresult = (event) => {
    const result = event.results[event.results.length - 1];
    if (!result.isFinal) {
      // You've started talking — barge in immediately, don't wait for you
      // to finish before pausing the narration. Stays paused through
      // follow-ups while the mic is on; see heldForConversation.
      heldForConversation = true;
      interruptNarrationForQuestion();
      return;
    }
    const text = result[0].transcript.trim();
    if (text) askQuestion(text);
  };
  r.onerror = (event) => {
    // 'no-speech' and 'aborted' are routine (nobody was talking, or we
    // stopped it ourselves) — not worth alarming about. Anything else
    // means listening actually broke, so stop and say why.
    if (event.error === 'no-speech' || event.error === 'aborted') return;
    listening = false;
    $('mic-btn').classList.remove('listening');
    const messages = {
      'not-allowed': 'Microphone access was blocked — check your browser/system mic permissions for this page.',
      'audio-capture': 'No microphone found.',
      'network': 'Voice recognition needs a network connection.',
      'service-not-allowed': 'Speech recognition service is unavailable.',
    };
    $('mic-hint').textContent = messages[event.error] || `Voice input stopped (${event.error}).`;
    heldForConversation = false; // listening stopped (even unexpectedly) — resume like mic-off
    resumeIfNeeded();
  };
  r.onend = () => {
    if (listening) { try { r.start(); } catch {} }
  };
  return r;
}

$('mic-btn').addEventListener('click', async () => {
  if (!recognition) recognition = getRecognition();
  if (!recognition) {
    $('mic-hint').textContent = "Voice input needs a browser with speech recognition (Chrome, Edge) — not supported here.";
    return;
  }
  if (!listening) {
    // Pressing the mic is itself an interruption. Do not wait for the
    // recognizer's first interim transcript before stopping narration.
    interruptNarrationForQuestion();
    // Ask for macOS/browser permission explicitly so a rejected permission is
    // reported here rather than appearing as a broken microphone button.
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('no microphone API');
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((track) => track.stop());
      recognition.start();
      // Only now, with the mic actually granted and listening, hold
      // narration paused through as many follow-ups as you like.
      heldForConversation = true;
    } catch (permissionError) {
      $('mic-hint').textContent = 'Microphone permission is needed. Allow it in your browser and macOS settings, then try again.';
      setExperienceStatus('Microphone access was not granted.', 'error');
      resumeIfNeeded();
      return;
    }
    listening = true;
    $('mic-btn').classList.add('listening');
    $('mic-hint').textContent = 'Listening — ask anytime, even mid-narration.';
  } else {
    listening = false;
    $('mic-btn').classList.remove('listening');
    recognition.stop();
    $('mic-hint').textContent = '';
    // Turning the mic off is itself the "I'm done asking" signal — resume
    // whatever narration was paused for the conversation.
    heldForConversation = false;
    resumeIfNeeded();
  }
});


function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}
function escapeAttr(s) {
  return (s || '').replace(/"/g, '&quot;');
}
