const MOOD_EMOJI = { frustrated: "😤", confused: "😕", neutral: "🙂", satisfied: "😊", urgent: "⏱️" };

async function main() {
  const callId = window.__CALL_ID__;
  const res = await fetch(`/api/calls/${callId}`);
  if (!res.ok) {
    document.getElementById("report").innerHTML = `<div class="loading">Call not found.</div>`;
    return;
  }
  const data = await res.json();
  render(data);
}

function toolFailureTurns(events) {
  const set = new Set();
  events.forEach((e) => {
    if (e.event_type === "tool_result" && e.tool_failed) set.add(e.turn_index);
  });
  return set;
}

function fmtDuration(call) {
  if (!call.started_at) return "–";
  const end = call.ended_at || Date.now() / 1000;
  const secs = Math.round(end - call.started_at);
  return `${Math.floor(secs / 60)}m ${secs % 60}s`;
}

function render(data) {
  const { call, events, flows } = data;
  const agentTurns = events.filter((e) => e.event_type === "llm_response");

  const root = document.getElementById("report");
  root.innerHTML = "";

  const steps = buildStepSequence(flows, agentTurns, events);

  if (call.final_label) root.appendChild(buildFinalSummary(call));
  root.appendChild(buildSummary(call, agentTurns));
  root.appendChild(buildLanes(flows, steps, events, toolFailureTurns(events)));
  root.appendChild(buildMoodChart(agentTurns, events));
  root.appendChild(buildSatisfactionChart(agentTurns));
  root.appendChild(buildTranscript(events));
  root.appendChild(buildLabelForm(call));
}

const LABEL_TEXT = {
  completed: "Completed",
  abandoned: "Abandoned",
  unresolved_drift: "Unresolved deviation",
  general_only: "Never engaged the flow",
  escalation_needed: "Needs escalation",
};

function buildFinalSummary(call) {
  const block = el("div", "panel-block final-summary");
  const pct = call.final_score != null ? Math.round(call.final_score * 100) : null;
  block.innerHTML = `
    <div class="final-summary-top">
      <span class="final-label final-label-${call.final_label}">${LABEL_TEXT[call.final_label] || call.final_label}</span>
      ${pct != null ? `<span class="final-score">${pct}%</span>` : ""}
    </div>
    <p class="final-reasoning">${call.final_reasoning || ""}</p>
  `;
  return block;
}

function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
}

function buildSummary(call, agentTurns) {
  const driftCount = call.drift_count || 0;
  const toolFailCount = call.tool_failure_count || 0;
  const sat = call.running_satisfaction != null ? Math.round(call.running_satisfaction * 100) : null;
  const block = el("div", "panel-block summary-grid");
  block.innerHTML = `
    <div><span class="metric-label">Call ID</span><div class="metric-value">${call.id}</div></div>
    <div><span class="metric-label">Duration</span><div class="metric-value">${fmtDuration(call)}</div></div>
    <div><span class="metric-label">Turns</span><div class="metric-value">${agentTurns.length}</div></div>
    <div><span class="metric-label">Deviations</span><div class="metric-value ${driftCount ? "bad" : ""}">${driftCount}</div></div>
    <div><span class="metric-label">Tool failures</span><div class="metric-value ${toolFailCount ? "bad" : ""}">${toolFailCount}</div></div>
    <div><span class="metric-label">Final satisfaction</span><div class="metric-value">${sat != null ? sat + "%" : "–"}</div></div>
    <div><span class="metric-label">User label</span><div class="metric-value">${call.user_label_score ? "★".repeat(call.user_label_score) + "☆".repeat(5 - call.user_label_score) : "not rated"}</div></div>
  `;
  return block;
}

// One row PER NODE (not per flow) — grouped visually by journey, plus two
// flat bottom rows: General (a fine tangent — harmless) and Off-chart (a
// real problem). A node that was never reached still gets its row drawn
// (grey guide line, dim label) so the whole shape of every supported journey
// is always visible — this is the capability map. Staying in a journey and
// moving forward draws a stepped line across that journey's rows; switching
// journeys jumps to a different journey's block of rows.
let reportTooltipEl = null;
function showReportTooltip(anchorEl, html) {
  if (!reportTooltipEl) {
    reportTooltipEl = el("div", "path-tooltip");
    document.body.appendChild(reportTooltipEl);
  }
  reportTooltipEl.innerHTML = html;
  const rect = anchorEl.getBoundingClientRect();
  reportTooltipEl.style.left = `${rect.right + 10}px`;
  reportTooltipEl.style.top = `${rect.top}px`;
  reportTooltipEl.hidden = false;
}
function hideReportTooltip() { if (reportTooltipEl) reportTooltipEl.hidden = true; }

function attachStageTooltip(pointEl, flow, stage) {
  pointEl.addEventListener("mouseenter", () => {
    const edgeLines = (stage.edges || [])
      .map((e) => {
        const target = flow.stages.find((s) => s.id === e.to);
        return `<div class="tt-edge">→ <b>${target ? target.name : e.to}</b><span>${e.condition}</span></div>`;
      })
      .join("") || `<div class="tt-edge tt-empty">Terminal node — no further edges.</div>`;
    const toolLine = stage.expected_tool ? `<div class="tt-desc">tool: <code>${stage.expected_tool}</code></div>` : "";
    showReportTooltip(pointEl, `<div class="tt-title">${stage.name}</div><div class="tt-desc">${stage.description || ""}</div>${toolLine}${edgeLines}`);
  });
  pointEl.addEventListener("mouseleave", hideReportTooltip);
}

function attachFlowGraphTooltip(headerEl, flow) {
  headerEl.addEventListener("mouseenter", () => {
    const lines = flow.stages
      .map((s) => {
        const targets = (s.edges || []).map((e) => (flow.stages.find((t) => t.id === e.to) || {}).name || e.to).join(", ") || "(terminal)";
        return `<div class="tt-edge"><b>${s.name}</b>${s.expected_tool ? ` <code>${s.expected_tool}</code>` : ""}<span>→ ${targets}</span></div>`;
      })
      .join("");
    showReportTooltip(headerEl, `<div class="tt-title">${flow.display_name || flow.name} — full graph</div>${lines}`);
  });
  headerEl.addEventListener("mouseleave", hideReportTooltip);
}

// Mirrors agent/schemas.py CallFlow.path_stages — the stages implied on the
// shortest path between two nodes, so a multi-hop move shows every stage it
// genuinely passed through, not just where it ended up.
function jsPathStages(flow, fromId, toId, maxHops = 10) {
  const byId = Object.fromEntries(flow.stages.map((s) => [s.id, s]));
  if (!byId[toId]) return [];
  if (!fromId || fromId === toId) return [byId[toId]];
  let frontier = [[fromId, []]];
  const visited = new Set([fromId]);
  for (let h = 0; h < maxHops; h++) {
    const next = [];
    for (const [nodeId, path] of frontier) {
      const stage = byId[nodeId];
      if (!stage) continue;
      for (const e of stage.edges || []) {
        const newPath = [...path, e.to];
        if (e.to === toId) return newPath.map((id) => byId[id]).filter(Boolean);
        if (!visited.has(e.to)) { visited.add(e.to); next.push([e.to, newPath]); }
      }
    }
    frontier = next;
  }
  return [];
}

// Expands each agent turn into every stage it actually passed through. A
// turn that silently chains several tool-driven stages (e.g. check stock ->
// add to cart -> checkout -> close, all in one reply) gets one step PER
// stage here, not one dot at wherever it landed — each labeled with its own
// tool, and colored red individually if that specific stage's tool was
// never actually called this turn.
function buildStepSequence(flows, agentTurns, allEvents) {
  const toolsByTurn = {};
  allEvents.forEach((e) => {
    if (e.event_type === "tool_result" && !e.tool_failed) {
      (toolsByTurn[e.turn_index] = toolsByTurn[e.turn_index] || new Set()).add(e.tool_name);
    }
  });

  const steps = [];
  let lastStageId = null;
  let lastFlowName = null;
  agentTurns.forEach((e) => {
    if (e.stage_actual && e.flow_name) {
      const flow = flows[e.flow_name];
      const sameFlow = e.flow_name === lastFlowName;
      const path = sameFlow
        ? jsPathStages(flow, lastStageId, e.stage_actual)
        : [flow.stages.find((s) => s.id === e.stage_actual)].filter(Boolean);
      const toolsThisTurn = toolsByTurn[e.turn_index] || new Set();
      path.forEach((stage, idx) => {
        const isFinal = idx === path.length - 1;
        const toolOk = !stage.expected_tool || toolsThisTurn.has(stage.expected_tool);
        steps.push({ flowName: e.flow_name, stage, event: e, isFinalOfTurn: isFinal, drift: (isFinal && e.drift_flag) || !toolOk });
      });
      lastStageId = e.stage_actual;
      lastFlowName = e.flow_name;
    } else {
      steps.push({ flowName: null, stage: null, event: e, isFinalOfTurn: true, drift: !!e.drift_flag });
    }
  });
  return steps;
}

// All journeys this agent supports are always shown as reference lines (a
// capability map), plus two flat lanes: General QA (a fine tangent —
// harmless) and Off Guard (a real problem — a structural skip, profanity,
// hallucination, or a tool call that actually failed). Time runs left to
// right, shared across every lane, one dot per STEP (not per turn — see
// buildStepSequence). Staying in a lane draws a flat line; a genuine switch
// or a dip into General QA/Off Guard draws a diagonal.
function buildLanes(flows, steps, allEvents, toolFailTurns) {
  const wrap = el("div", "panel-block");
  wrap.appendChild(el("h3", "", "Journeys and the call's actual movement"));

  const flowNames = Object.keys(flows);
  const laneKeys = [...flowNames, "__general__", "__offchart__"];
  const laneH = 78, colW = 120;
  const width = Math.max(steps.length, 1) * colW + 40;
  const height = laneKeys.length * laneH;
  const laneY = (i) => i * laneH + laneH / 2 + 10;

  const container = el("div", "lanes-container");
  const headers = el("div", "lane-headers");
  laneKeys.forEach((key, i) => {
    const isFlow = flowNames.includes(key);
    const row = el("div", "lane-header-row" + (isFlow ? "" : " lane-flat"));
    row.style.height = `${laneH}px`;
    if (isFlow) {
      row.innerHTML = `<div class="lane-name">${flows[key].display_name || flows[key].name}</div><div class="lane-hint">hover for full graph</div>`;
      attachFlowGraphTooltip(row, flows[key]);
    } else {
      row.textContent = key === "__general__" ? "General QA" : "Off Guard";
    }
    headers.appendChild(row);
  });
  container.appendChild(headers);

  const svgWrap = el("div", "swimlane-scroll");
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", width);
  svg.setAttribute("height", height);
  svg.setAttribute("class", "swimlane-svg");

  laneKeys.forEach((key, i) => {
    const line = document.createElementNS(svg.namespaceURI, "line");
    line.setAttribute("x1", 0); line.setAttribute("x2", width);
    line.setAttribute("y1", laneY(i)); line.setAttribute("y2", laneY(i));
    line.setAttribute("class", "guide-line" + (flowNames.includes(key) ? "" : " off-graph"));
    svg.appendChild(line);
  });

  const laneIndexOf = (s) => {
    if (s.stage && s.flowName) {
      const idx = flowNames.indexOf(s.flowName);
      if (idx >= 0) return idx;
    }
    return s.drift ? laneKeys.length - 1 : laneKeys.length - 2;
  };
  const occurrenceSoFar = {};
  const points = steps.map((s, i) => {
    let occNum = null;
    if (s.stage && s.flowName) {
      const key = `${s.flowName}::${s.stage.id}`;
      occurrenceSoFar[key] = (occurrenceSoFar[key] || 0) + 1;
      occNum = occurrenceSoFar[key];
    }
    return { x: colW / 2 + i * colW, y: laneY(laneIndexOf(s)), s, occNum };
  });

  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1], b = points[i];
    const line = document.createElementNS(svg.namespaceURI, "line");
    line.setAttribute("x1", a.x); line.setAttribute("y1", a.y);
    line.setAttribute("x2", b.x); line.setAttribute("y2", b.y);
    line.setAttribute("class", "path-seg" + (b.s.drift ? " drift" : ""));
    svg.appendChild(line);
  }

  points.forEach((p) => {
    const s = p.s, stage = s.stage, e = s.event;

    const c = document.createElementNS(svg.namespaceURI, "circle");
    c.setAttribute("cx", p.x); c.setAttribute("cy", p.y); c.setAttribute("r", 11);
    c.setAttribute("class", "point" + (s.drift ? " drift" : stage ? " reached" : " general"));
    c.style.cursor = "pointer";
    c.addEventListener("click", () => showDetail(s, steps, allEvents));
    if (stage) attachStageTooltip(c, flows[s.flowName], stage);
    svg.appendChild(c);

    if (p.occNum) {
      const num = document.createElementNS(svg.namespaceURI, "text");
      num.setAttribute("x", p.x); num.setAttribute("y", p.y + 4);
      num.setAttribute("class", "point-num");
      num.setAttribute("text-anchor", "middle");
      num.textContent = p.occNum;
      svg.appendChild(num);
    }

    // Label above the dot: the node name (+ its tool, if any) when reached,
    // else a short description of what actually happened off-guard.
    const label1 = document.createElementNS(svg.namespaceURI, "text");
    label1.setAttribute("x", p.x); label1.setAttribute("y", p.y - 30);
    label1.setAttribute("class", "point-label" + (s.drift ? " drift" : ""));
    label1.setAttribute("text-anchor", "middle");
    label1.textContent = stage ? stage.name : e.drift_flag ? "off guard" : "tangent";
    svg.appendChild(label1);

    const label2 = document.createElementNS(svg.namespaceURI, "text");
    label2.setAttribute("x", p.x); label2.setAttribute("y", p.y - 18);
    label2.setAttribute("class", "point-sublabel");
    label2.setAttribute("text-anchor", "middle");
    label2.textContent = stage && stage.expected_tool ? `[${stage.expected_tool}]` : e.drift_flag ? truncate(e.drift_note, 26) : "";
    svg.appendChild(label2);

    if ((s.isFinalOfTurn && toolFailTurns.has(e.turn_index)) || e.profanity_user || e.profanity_agent) {
      const mark = document.createElementNS(svg.namespaceURI, "text");
      mark.setAttribute("x", p.x); mark.setAttribute("y", p.y + 26);
      mark.setAttribute("class", "point-mark");
      mark.setAttribute("text-anchor", "middle");
      mark.textContent = (toolFailTurns.has(e.turn_index) ? "🔧" : "") + ((e.profanity_user || e.profanity_agent) ? "🚫" : "");
      svg.appendChild(mark);
    }
  });

  svgWrap.appendChild(svg);
  container.appendChild(svgWrap);
  wrap.appendChild(container);
  wrap.appendChild(el("div", "swimlane-legend", `
    <span><i class="dot-legend point"></i> reached</span>
    <span><i class="dot-legend point drift"></i> off guard (deviation)</span>
    <span>N in circle = visited that step N times</span>
    <span>🔧 tool failed this turn · 🚫 profanity</span>
  `));
  wrap.appendChild(el("div", "detail-panel", '<span class="hint">Click a point to see what happened there — including the full path taken to reach it.</span>'));
  return wrap;
}

function truncate(text, n) {
  if (!text) return "";
  return text.length > n ? text.slice(0, n - 1) + "…" : text;
}

function showDetail(step, allSteps, allEvents) {
  const panel = document.querySelector(".detail-panel");
  const event = step.event;
  const idx = allEvents.findIndex((e) => e.id === event.id);
  let precedingUser = null;
  for (let i = idx - 1; i >= 0; i--) {
    if (allEvents[i].actor === "user") { precedingUser = allEvents[i]; break; }
  }

  const upTo = allSteps.slice(0, allSteps.indexOf(step) + 1);
  let breadcrumb = "";
  let lastFlow = undefined;
  upTo.forEach((s) => {
    if (s.flowName !== lastFlow) {
      breadcrumb += `${breadcrumb ? " <span class='bc-switch'>⚡</span> " : ""}<span class="bc-flow">${s.flowName || "off-graph"}</span>: `;
      lastFlow = s.flowName;
    } else {
      breadcrumb += " → ";
    }
    breadcrumb += s.stage ? s.stage.name : (s.event.drift_flag ? "off guard" : "tangent");
  });

  panel.innerHTML = `
    ${precedingUser ? `<div class="detail-user">"${precedingUser.content}"</div>` : ""}
    <div class="detail-agent">${event.content || ""}</div>
    <div class="detail-meta">
      step: <b>${step.stage ? `${step.flowName} / ${step.stage.name}` : "off graph"}</b>${step.stage && step.stage.expected_tool ? ` · tool: <code>${step.stage.expected_tool}</code>` : ""} · mood: ${MOOD_EMOJI[event.caller_mood] || ""} ${event.caller_mood || "–"}
      · latency: ${event.latency_ms ? Math.round(event.latency_ms) + "ms" : "–"}
    </div>
    ${event.drift_flag ? `<div class="detail-drift">⚠ ${event.drift_note || "Deviation flagged"}</div>` : ""}
    ${(event.profanity_user || event.profanity_agent) ? `<div class="detail-drift">🚫 profanity detected (${[event.profanity_user && "caller", event.profanity_agent && "agent"].filter(Boolean).join(", ")})</div>` : ""}
    ${event.audio_url ? `<audio src="${event.audio_url}" controls></audio>` : ""}
    ${breadcrumb ? `<div class="detail-breadcrumb"><span class="detail-breadcrumb-label">Full trajectory to here:</span> ${breadcrumb}</div>` : ""}
  `;
}

function buildSatisfactionChart(agentTurns) {
  const wrap = el("div", "panel-block");
  wrap.appendChild(el("h3", "", "Satisfaction over the call"));
  const w = 640, h = 90, pad = 10;
  const vals = agentTurns.map((e) => (e.satisfaction_after != null ? e.satisfaction_after : 0.5));
  if (vals.length === 0) {
    wrap.appendChild(el("div", "hint", "No turns yet."));
    return wrap;
  }
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", w); svg.setAttribute("height", h);
  svg.setAttribute("class", "spark-svg");
  const stepX = (w - pad * 2) / Math.max(vals.length - 1, 1);
  const pts = vals.map((v, i) => `${pad + i * stepX},${h - pad - v * (h - pad * 2)}`).join(" ");
  const poly = document.createElementNS(svg.namespaceURI, "polyline");
  poly.setAttribute("points", pts);
  poly.setAttribute("class", "spark-line");
  svg.appendChild(poly);
  vals.forEach((v, i) => {
    const c = document.createElementNS(svg.namespaceURI, "circle");
    c.setAttribute("cx", pad + i * stepX);
    c.setAttribute("cy", h - pad - v * (h - pad * 2));
    c.setAttribute("r", 3);
    c.setAttribute("class", agentTurns[i].drift_flag ? "spark-point drift" : "spark-point");
    svg.appendChild(c);
  });
  wrap.appendChild(svg);
  return wrap;
}

// Mood is categorical, not a scale — the vertical order below is just to
// keep same-mood points visually level, not a claim that e.g. "urgent" is
// between "confused" and "satisfied".
const MOOD_ORDER = ["frustrated", "confused", "urgent", "neutral", "satisfied"];

function buildMoodChart(agentTurns, allEvents) {
  const wrap = el("div", "panel-block");
  wrap.appendChild(el("h3", "", "Caller mood over the call"));
  const moodTurns = agentTurns.filter((e) => e.caller_mood);
  if (!moodTurns.length) {
    wrap.appendChild(el("div", "hint", "No mood data yet."));
    return wrap;
  }
  const w = 640, h = 110, pad = 16;
  const rowH = (h - pad * 2) / (MOOD_ORDER.length - 1);
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", w); svg.setAttribute("height", h);
  svg.setAttribute("class", "mood-svg");

  MOOD_ORDER.forEach((mood, i) => {
    const y = pad + i * rowH;
    const line = document.createElementNS(svg.namespaceURI, "line");
    line.setAttribute("x1", pad); line.setAttribute("x2", w - pad);
    line.setAttribute("y1", y); line.setAttribute("y2", y);
    line.setAttribute("class", "mood-guide");
    svg.appendChild(line);
    const label = document.createElementNS(svg.namespaceURI, "text");
    label.setAttribute("x", 2); label.setAttribute("y", y + 3);
    label.setAttribute("class", "mood-row-label");
    label.textContent = MOOD_EMOJI[mood] || mood;
    svg.appendChild(label);
  });

  const stepX = (w - pad * 2) / Math.max(moodTurns.length - 1, 1);
  const yFor = (mood) => pad + (MOOD_ORDER.indexOf(mood) >= 0 ? MOOD_ORDER.indexOf(mood) : 3) * rowH;

  for (let i = 1; i < moodTurns.length; i++) {
    const a = moodTurns[i - 1], b = moodTurns[i];
    const line = document.createElementNS(svg.namespaceURI, "line");
    line.setAttribute("x1", pad + (i - 1) * stepX); line.setAttribute("y1", yFor(a.caller_mood));
    line.setAttribute("x2", pad + i * stepX); line.setAttribute("y2", yFor(b.caller_mood));
    line.setAttribute("class", "mood-line" + (a.caller_mood !== b.caller_mood ? " mood-shift" : ""));
    svg.appendChild(line);
  }

  moodTurns.forEach((e, i) => {
    const c = document.createElementNS(svg.namespaceURI, "circle");
    c.setAttribute("cx", pad + i * stepX);
    c.setAttribute("cy", yFor(e.caller_mood));
    c.setAttribute("r", 6);
    c.setAttribute("class", "mood-point");
    c.style.cursor = "pointer";
    c.addEventListener("click", () => showMoodDetail(e, moodTurns, i, allEvents));
    svg.appendChild(c);
  });

  wrap.appendChild(svg);
  wrap.appendChild(el("div", "mood-detail", '<span class="hint">Click a point to see what caused that mood.</span>'));
  return wrap;
}

function showMoodDetail(event, moodTurns, i, allEvents) {
  const panel = document.querySelector(".mood-detail");
  const idx = allEvents.findIndex((e) => e.id === event.id);
  let precedingUser = null;
  for (let j = idx - 1; j >= 0; j--) {
    if (allEvents[j].actor === "user") { precedingUser = allEvents[j]; break; }
  }
  const prev = i > 0 ? moodTurns[i - 1] : null;
  const shiftNote = prev && prev.caller_mood !== event.caller_mood
    ? `<div class="mood-shift-note">Shifted from ${MOOD_EMOJI[prev.caller_mood] || ""} ${prev.caller_mood} to ${MOOD_EMOJI[event.caller_mood] || ""} ${event.caller_mood} here.</div>`
    : `<div class="mood-shift-note">Stayed ${MOOD_EMOJI[event.caller_mood] || ""} ${event.caller_mood} through this turn.</div>`;
  panel.innerHTML = `
    ${shiftNote}
    ${precedingUser ? `<div class="detail-user">"${precedingUser.content}"</div>` : ""}
    <div class="detail-agent">${event.content || ""}</div>
    ${event.drift_flag ? `<div class="detail-drift">⚠ ${event.drift_note || ""}</div>` : ""}
  `;
}

function buildTranscript(events) {
  const wrap = el("div", "panel-block");
  wrap.appendChild(el("h3", "", "Full transcript"));
  const list = el("div", "transcript-list");
  events.forEach((e) => {
    if (e.event_type === "tool_call" || e.event_type === "tool_result") {
      const problem = e.tool_arg_issue || e.tool_failed;
      const row = el("div", "t-row t-tool" + (problem ? " t-tool-problem" : ""));
      row.innerHTML = `<span class="t-actor">tool</span><span>${e.tool_name}${e.event_type === "tool_call" ? "(" + JSON.stringify(e.tool_args || {}) + ")" : " → " + JSON.stringify(e.tool_result || {}).slice(0, 160)}</span>${e.tool_arg_issue ? `<span class="t-tool-flag">⚠ ${e.tool_arg_issue}</span>` : ""}${e.tool_failed ? `<span class="t-tool-flag">🔧 failed</span>` : ""}`;
      list.appendChild(row);
      return;
    }
    if (e.event_type === "flow_switch") {
      list.appendChild(el("div", "t-row t-switch", `<span>↳ ${e.content}</span>`));
      return;
    }
    if (!e.content) return;
    const cls = `t-row t-${e.actor}${e.drift_flag ? " t-drift" : ""}${!e.drift_flag && e.event_type === "llm_response" && !e.stage_actual ? " t-general" : ""}`;
    const row = el("div", cls);
    row.innerHTML = `
      <span class="t-actor">${e.actor}</span>
      <span class="t-content">${e.content}</span>
      ${e.stage_actual ? `<span class="t-stage">${e.flow_name}/${e.stage_actual}</span>` : (e.event_type === "llm_response" ? `<span class="t-stage">off graph</span>` : "")}
      ${(e.profanity_user || e.profanity_agent) ? `<span class="t-stage">🚫</span>` : ""}
      ${e.audio_url ? `<audio src="${e.audio_url}" controls></audio>` : ""}
      ${e.drift_flag ? `<div class="t-drift-note">⚠ ${e.drift_note || ""}</div>` : ""}
    `;
    list.appendChild(row);
  });
  wrap.appendChild(list);
  return wrap;
}

function buildLabelForm(call) {
  const wrap = el("div", "panel-block");
  wrap.appendChild(el("h3", "", "Your satisfaction with this call"));
  const form = el("div", "label-form");
  const stars = el("div", "stars");
  let selected = call.user_label_score || 0;
  for (let i = 1; i <= 5; i++) {
    const s = el("span", "star" + (i <= selected ? " on" : ""), "★");
    s.addEventListener("click", () => {
      selected = i;
      [...stars.children].forEach((c, idx) => c.classList.toggle("on", idx < selected));
    });
    stars.appendChild(s);
  }
  const comment = el("textarea", "label-comment");
  comment.placeholder = "Anything to add? (optional)";
  comment.value = call.user_label_comment || "";
  const submit = el("button", "label-submit", "Save label");
  submit.addEventListener("click", async () => {
    if (!selected) return;
    await fetch(`/api/calls/${call.id}/label`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ score: selected, comment: comment.value }),
    });
    submit.textContent = "Saved ✓";
  });
  form.appendChild(stars);
  form.appendChild(comment);
  form.appendChild(submit);
  wrap.appendChild(form);
  return wrap;
}

main();
