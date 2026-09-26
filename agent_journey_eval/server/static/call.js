const transcript = document.getElementById("transcript");
const micBtn = document.getElementById("mic-btn");
const micStatus = document.getElementById("mic-status");
const typeForm = document.getElementById("type-form");
const typeInput = document.getElementById("type-input");
const endCallBtn = document.getElementById("end-call-btn");
const connDot = document.getElementById("conn-dot");
const satFill = document.getElementById("sat-fill");
const satValue = document.getElementById("sat-value");
const moodValue = document.getElementById("mood-value");
const driftCountValue = document.getElementById("drift-count-value");
const latencyValue = document.getElementById("latency-value");
const stageStepper = document.getElementById("stage-stepper");
const driftList = document.getElementById("drift-list");
const pathHeading = document.getElementById("path-heading");
const treeToggleBtn = document.getElementById("tree-toggle-btn");
const treeView = document.getElementById("tree-view");

const flows = window.__FLOWS__; // { flowName: {name, entry_description, stages:[{id,name,edges,...}]} }
let callId = null;
let ws = null;
let recognition = null;
let listening = false;
let ended = false;
let activeFlowName = null;
let showingTree = false;

const MOOD_EMOJI = { frustrated: "😤", confused: "😕", neutral: "🙂", satisfied: "😊", urgent: "⏱️" };

// Nothing is known about this call's path until the conversation gives
// evidence of a flow — but the MOMENT a flow is identified, its full set of
// steps is shown up front (greyed out ahead of where the call actually is),
// not revealed one at a time. visitedPath is the full cross-flow history,
// used to drive the full-tree view's visited/current highlighting. Each
// entry: {flowName, stageId}.
let visitedPath = [];
let flowNodeLis = {}; // stageId -> <li> for the CURRENTLY RENDERED (active) flow's backbone

function findStage(flowName, stageId) {
  const flow = flows[flowName];
  return flow ? flow.stages.find((s) => s.id === stageId) : null;
}

function renderFlowBackbone(flowName) {
  stageStepper.innerHTML = "";
  flowNodeLis = {};
  const flow = flows[flowName];
  if (!flow) return;
  flow.stages.forEach((s, i) => {
    const li = document.createElement("li");
    li.className = "pending"; // shown up front as "this is the path this could take," not yet reached
    li.dataset.flowName = flowName;
    li.dataset.stageId = s.id;
    li.innerHTML = `<span class="idx">${i + 1}</span><span>${s.name}</span>`;
    attachHoverTooltip(li, flowName, s);
    stageStepper.appendChild(li);
    flowNodeLis[s.id] = li;
  });
}

function appendAside(text, kind) {
  const li = document.createElement("li");
  li.className = `aside ${kind}`;
  li.textContent = text;
  const currentLi = stageStepper.querySelector("li.current");
  if (currentLi) currentLi.insertAdjacentElement("afterend", li);
  else stageStepper.appendChild(li);
  stageStepper.scrollTop = stageStepper.scrollHeight;
}

function appendVisitedNode(flowName, stageId) {
  const stage = findStage(flowName, stageId);
  if (!stage) return;

  const hint = document.getElementById("stepper-hint");
  if (hint) hint.hidden = true;

  if (activeFlowName !== flowName) {
    const previous = activeFlowName;
    activeFlowName = flowName;
    renderFlowBackbone(flowName);
    if (previous) {
      const divider = document.createElement("li");
      divider.className = "aside divider";
      divider.textContent = `↳ switched from ${flow_display_name(previous)}`;
      stageStepper.insertBefore(divider, stageStepper.firstChild);
    }
    treeToggleBtn.hidden = false;
    pathHeading.textContent = `Path so far — ${flow_display_name(flowName)}`;
  }

  const prevCurrent = stageStepper.querySelector("li.current");
  if (prevCurrent) prevCurrent.classList.replace("current", "visited");

  const li = flowNodeLis[stageId];
  if (li) {
    li.classList.remove("pending");
    li.classList.add("current");
  }

  visitedPath.push({ flowName, stageId });
  if (showingTree) renderFullTree(); // keep the tree view in sync if it's the active view
}

function flow_display_name(flowName) {
  return flows[flowName] ? (flows[flowName].display_name || flows[flowName].name) : flowName;
}

// --- Hover tooltip: "what could happen next from here" ---
let tooltipEl = null;
function attachHoverTooltip(li, flowName, stage) {
  li.addEventListener("mouseenter", () => {
    if (!tooltipEl) {
      tooltipEl = document.createElement("div");
      tooltipEl.className = "path-tooltip";
      document.body.appendChild(tooltipEl);
    }
    const edgeLines = (stage.edges || [])
      .map((e) => `<div class="tt-edge">→ <b>${(findStage(flowName, e.to) || {}).name || e.to}</b><span>${e.condition}</span></div>`)
      .join("") || `<div class="tt-edge tt-empty">Terminal node — no further edges.</div>`;
    tooltipEl.innerHTML = `<div class="tt-title">${stage.name}</div><div class="tt-desc">${stage.description || ""}</div>${edgeLines}`;
    const rect = li.getBoundingClientRect();
    tooltipEl.style.left = `${rect.right + 10}px`;
    tooltipEl.style.top = `${rect.top}px`;
    tooltipEl.hidden = false;
  });
  li.addEventListener("mouseleave", () => {
    if (tooltipEl) tooltipEl.hidden = true;
  });
}

// --- Full tree view: the whole graph for the active flow, visited highlighted ---
function layoutFlow(flow) {
  const layer = { [flow.stages[0].id]: 0 };
  const queue = [flow.stages[0].id];
  while (queue.length) {
    const id = queue.shift();
    const stage = flow.stages.find((s) => s.id === id);
    for (const e of stage.edges || []) {
      if (!(e.to in layer)) {
        layer[e.to] = layer[id] + 1;
        queue.push(e.to);
      }
    }
  }
  flow.stages.forEach((s) => { if (!(s.id in layer)) layer[s.id] = 0; }); // unreachable safety net
  const byLayer = {};
  flow.stages.forEach((s) => {
    (byLayer[layer[s.id]] = byLayer[layer[s.id]] || []).push(s.id);
  });
  const colW = 130, rowH = 40, padX = 70, padY = 24;
  const pos = {};
  Object.entries(byLayer).forEach(([l, ids]) => {
    ids.forEach((id, i) => {
      pos[id] = { x: padX + Number(l) * colW, y: padY + i * rowH };
    });
  });
  const width = padX * 2 + (Math.max(...Object.values(layer)) + 1) * colW;
  const height = padY * 2 + Math.max(...Object.values(byLayer).map((a) => a.length)) * rowH;
  return { pos, width: Math.max(width, 300), height: Math.max(height, 200) };
}

function renderFullTree() {
  treeView.innerHTML = "";
  const flow = flows[activeFlowName];
  if (!flow) return;
  const { pos, width, height } = layoutFlow(flow);
  const visitedIds = new Set(visitedPath.filter((v) => v.flowName === activeFlowName).map((v) => v.stageId));
  const currentId = [...visitedPath].reverse().find((v) => v.flowName === activeFlowName)?.stageId;

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", width);
  svg.setAttribute("height", height);
  svg.setAttribute("class", "tree-svg");

  flow.stages.forEach((s) => {
    (s.edges || []).forEach((e) => {
      const a = pos[s.id], b = pos[e.to];
      if (!a || !b) return;
      const line = document.createElementNS(svg.namespaceURI, "line");
      line.setAttribute("x1", a.x); line.setAttribute("y1", a.y);
      line.setAttribute("x2", b.x); line.setAttribute("y2", b.y);
      line.setAttribute("class", "tree-edge" + (b.x < a.x ? " tree-edge-back" : ""));
      svg.appendChild(line);
    });
  });

  flow.stages.forEach((s) => {
    const p = pos[s.id];
    if (!p) return;
    const g = document.createElementNS(svg.namespaceURI, "g");
    g.setAttribute("class", "tree-node" + (s.id === currentId ? " current" : visitedIds.has(s.id) ? " visited" : ""));
    const circle = document.createElementNS(svg.namespaceURI, "circle");
    circle.setAttribute("cx", p.x); circle.setAttribute("cy", p.y); circle.setAttribute("r", 8);
    g.appendChild(circle);
    const label = document.createElementNS(svg.namespaceURI, "text");
    label.setAttribute("x", p.x + 14); label.setAttribute("y", p.y + 4);
    label.textContent = s.name;
    g.appendChild(label);
    attachHoverTooltip(g, activeFlowName, s);
    svg.appendChild(g);
  });

  treeView.appendChild(svg);
}

treeToggleBtn.addEventListener("click", () => {
  showingTree = !showingTree;
  stageStepper.hidden = showingTree;
  treeView.hidden = !showingTree;
  treeToggleBtn.textContent = showingTree ? "View trace" : "View full tree";
  if (showingTree) renderFullTree();
});

function addBubble(text, cls, meta) {
  const div = document.createElement("div");
  div.className = `bubble ${cls}`;
  div.textContent = text;
  if (meta) {
    const span = document.createElement("span");
    span.className = "meta";
    span.textContent = meta;
    div.appendChild(span);
  }
  transcript.appendChild(div);
  transcript.scrollTop = transcript.scrollHeight;
  return div;
}

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/call`);

  ws.onopen = () => connDot.classList.add("live");
  ws.onclose = () => {
    connDot.classList.remove("live");
    if (!ended) connDot.classList.add("error");
  };
  ws.onerror = () => connDot.classList.add("error");

  ws.onmessage = (evt) => {
    const msg = JSON.parse(evt.data);
    handleMessage(msg);
  };
}

function handleMessage(msg) {
  if (msg.type === "call_started") {
    callId = msg.call_id;
    addBubble("Call connected. Say hello to get started.", "system");
  } else if (msg.type === "user_echo") {
    // already rendered optimistically when sent; no-op if it matches
  } else if (msg.type === "agent_turn") {
    micBtn.classList.remove("speaking");
    const stageLabel = msg.stage_actual
      ? `${msg.flow_name} / ${msg.stage_actual}`
      : (msg.unscored ? "unscored (judge unavailable)" : (msg.drift_flag ? "off-path" : "general"));
    const profanityBadge = (msg.profanity_user || msg.profanity_agent) ? " · 🚫 profanity" : "";
    const toolBadge = msg.tool_issue_summary ? " · 🔧 tool issue" : "";
    const meta = `${stageLabel} · ${msg.latency_ms ? Math.round(msg.latency_ms) + "ms" : ""}${profanityBadge}${toolBadge}`;
    let cls = "agent";
    if (msg.drift_flag) cls += " drift";
    else if (!msg.stage_actual) cls += " general";
    const bubble = addBubble(msg.agent_text, cls, meta);
    if (msg.audio_url) {
      const audio = document.createElement("audio");
      audio.src = msg.audio_url;
      audio.controls = true;
      audio.autoplay = true;
      bubble.appendChild(audio);
    } else {
      speakBrowserFallback(msg.agent_text);
    }
    if (msg.stage_actual) {
      appendVisitedNode(msg.flow_name, msg.stage_actual);
    } else if (msg.drift_flag) {
      appendAside(`⚠ ${msg.drift_note || "went off path"}`, "drift");
    } else if (!msg.unscored && activeFlowName) {
      appendAside("↳ fine tangent", "general");
    }
    updateMetrics(msg);
  } else if (msg.type === "call_ended") {
    ended = true;
    addBubble("Call ended.", "system");
    setTimeout(() => { window.location.href = `/call/${msg.call_id}`; }, 600);
  } else if (msg.type === "error") {
    addBubble(`Error: ${msg.message}`, "system");
  }
}

function updateMetrics(msg) {
  if (typeof msg.running_satisfaction === "number") {
    const pct = Math.round(msg.running_satisfaction * 100);
    satFill.style.width = `${pct}%`;
    satValue.textContent = `${pct}%`;
  }
  if (msg.caller_mood) {
    moodValue.textContent = `${MOOD_EMOJI[msg.caller_mood] ?? ""} ${msg.caller_mood}`;
  }
  if (typeof msg.drift_count === "number") {
    driftCountValue.textContent = msg.drift_count;
  }
  if (typeof msg.latency_ms === "number") {
    latencyValue.textContent = `${Math.round(msg.latency_ms)}ms`;
  }
  if (msg.drift_flag || msg.profanity_user || msg.profanity_agent || msg.tool_issue_summary) {
    const empty = driftList.querySelector(".empty");
    if (empty) empty.remove();
    const li = document.createElement("li");
    const parts = [];
    if (msg.drift_flag) parts.push(msg.drift_note || "Deviation flagged");
    if (msg.profanity_user) parts.push("🚫 profanity from caller");
    if (msg.profanity_agent) parts.push("🚫 profanity from agent");
    if (msg.tool_issue_summary) parts.push(`🔧 ${msg.tool_issue_summary}`);
    li.textContent = parts.join(" · ");
    driftList.prepend(li);
  }
}

function sendUtterance(text) {
  if (!text.trim() || !ws || ws.readyState !== WebSocket.OPEN) return;
  addBubble(text, "user");
  micBtn.classList.add("speaking");
  ws.send(JSON.stringify({ type: "utterance", text }));
}

function speakBrowserFallback(text) {
  if (!("speechSynthesis" in window)) return;
  const utter = new SpeechSynthesisUtterance(text);
  window.speechSynthesis.speak(utter);
}

// --- Speech recognition (Chrome/Edge only) ---
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SpeechRecognition) {
  recognition = new SpeechRecognition();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = "en-US";

  recognition.onresult = (event) => {
    let finalText = "";
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const t = event.results[i][0].transcript;
      if (event.results[i].isFinal) finalText += t;
      else interim += t;
    }
    if (interim) micStatus.textContent = `Listening: "${interim}"`;
    if (finalText.trim()) {
      micStatus.textContent = "Listening…";
      sendUtterance(finalText.trim());
    }
  };
  recognition.onerror = (e) => { micStatus.textContent = `Mic error: ${e.error}`; };
  recognition.onend = () => {
    if (listening) recognition.start(); // keep it continuous across pauses
  };
} else {
  micStatus.textContent = "Speech recognition isn't supported in this browser — type instead.";
  micBtn.disabled = true;
}

micBtn.addEventListener("click", () => {
  if (!recognition) return;
  listening = !listening;
  micBtn.classList.toggle("listening", listening);
  if (listening) {
    recognition.start();
    micStatus.textContent = "Listening…";
  } else {
    recognition.stop();
    micStatus.textContent = "Click the mic and start talking";
  }
});

typeForm.addEventListener("submit", (e) => {
  e.preventDefault();
  sendUtterance(typeInput.value);
  typeInput.value = "";
});

endCallBtn.addEventListener("click", () => {
  if (listening) recognition && recognition.stop();
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "end_call" }));
  }
});

connect();
