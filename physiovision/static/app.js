/* PhysioVision AI - Ultra-Simple Browser Client
   Drives the 3-step user flow, live workout mode, audio coaching, and fitness logs. */
(() => {
  "use strict";

  const EXERCISES = JSON.parse(document.getElementById("ex-data").textContent);
  const $ = (id) => document.getElementById(id);
  const RING_LEN = 2 * Math.PI * 52;

  const EX_ICONS = {
    bicep_curl: "💪",
    squat: "🦵",
    shoulder_press: "🙆",
    lateral_raise: "🤸",
    knee_raise: "🦿",
  };

  const CAL_PER_REP = {
    squat: 0.38,
    shoulder_press: 0.28,
    bicep_curl: 0.22,
    lateral_raise: 0.24,
    knee_raise: 0.30,
  };

  const LEVEL_CONFIG = {
    kids: {
      name: "Kids (6 reps)",
      target: 6,
      suggestion: "💡 <strong>Kids Tip:</strong> 6 reps per session · 2 to 3 fun play sessions daily at home. Keeps you energetic & happy!",
      cheers: ["Awesome job!", "You're a superstar!", "Super rep!", "High five!", "Keep jumping!"],
    },
    student: {
      name: "Student (10 reps)",
      target: 10,
      suggestion: "💡 <strong>Student Tip:</strong> 10 reps every 2 study hours resets desk slouch and burns snack calories!",
      cheers: ["Great form!", "Halfway there!", "Crushing it!", "Strong posture!", "Almost done!"],
    },
    adult: {
      name: "Adult (15 reps)",
      target: 15,
      suggestion: "💡 <strong>Adult Tip:</strong> 15–20 reps · 3 to 4 sets, 4–5 days a week for stamina, posture, and maximum calorie burn.",
      cheers: ["Power through!", "Excellent control!", "Feel the burn!", "Solid rep!", "Champion pace!"],
    },
  };

  const els = {
    picker: $("picker"), desc: $("ex-desc"), tip: $("ex-tip"),
    reps: $("reps"), targetShow: $("target-show"), ring: $("ring"),
    gonio: $("gonio"), jointLabel: $("joint-label"), sideShow: $("side-show"),
    phases: [...document.querySelectorAll("#phases li")],
    feedback: $("feedback"), time: $("time"), partial: $("partial"), rom: $("rom"),
    calNum: $("cal-num"),
    preStartCard: $("pre-start-card"), liveWorkoutCard: $("live-workout-card"),
    setup: $("setup"), profile: $("profile"), profileList: $("profile-list"),
    side: $("side"), target: $("target"), voice: $("voice"),
    start: $("btn-start"), pause: $("btn-pause"), finish: $("btn-finish"), cancel: $("btn-cancel"),
    status: $("status"), statusText: $("status-text"), fps: $("fps"), badge: $("video-badge"),
    cheerOverlay: $("cheer-overlay"), cheerText: $("cheer-text"),
    histProfile: $("history-profile"), histBody: $("history-body"), histEmpty: $("history-empty"),
    chart: $("chart"), toast: $("toast"), feed: $("feed"),
    levelSuggestion: $("level-suggestion"),
    levelPills: [...document.querySelectorAll(".level-pill")],
    themeBtns: [...document.querySelectorAll(".theme-btn")],
    btnOpenGuide: $("btn-open-guide"), btnCloseGuide: $("btn-close-guide"),
    btnCloseGuideFooter: $("btn-close-guide-footer"),
    modalBackdrop: $("modal-backdrop"), guideModal: $("guide-modal"),
    tabBtns: [...document.querySelectorAll(".tab-btn")],
    tabPanes: [...document.querySelectorAll(".tab-pane")],
  };

  let selected = EXERCISES[0].key;
  let currentLevel = "student";
  let session = null;          // latest session object from server
  let lastRepId = 0;
  let needle = null, valueText = null;
  let drawnFor = null;
  let historyData = null;
  let lastSpokenCueTime = 0;

  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* ignore */ } },
  };

  // ------------------------------------------------------------------ API
  async function api(path, body, method) {
    const res = await fetch(path, {
      method: method || (body ? "POST" : "GET"),
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
    return data;
  }

  // ---------------------------------------------------------------- THEMES
  function applyTheme(themeName) {
    document.documentElement.dataset.theme = themeName;
    store.set("pv.theme", themeName);
    els.themeBtns.forEach((b) => b.classList.toggle("active", b.dataset.themeVal === themeName));
    drawChart(historyData && historyData.daily);
  }

  // ---------------------------------------------------------------- LEVELS
  function applyLevel(lvl) {
    if (!LEVEL_CONFIG[lvl]) lvl = "student";
    currentLevel = lvl;
    store.set("pv.level", lvl);

    els.levelPills.forEach((p) => p.classList.toggle("active", p.dataset.level === lvl));
    const cfg = LEVEL_CONFIG[lvl];
    if (els.levelSuggestion) els.levelSuggestion.innerHTML = cfg.suggestion;

    if (!session) {
      els.target.value = cfg.target;
      els.targetShow.textContent = String(cfg.target);
    }
  }

  // -------------------------------------------------------------- PICKER
  function exByKey(k) { return EXERCISES.find((e) => e.key === k); }

  function renderPicker() {
    els.picker.innerHTML = "";
    for (const ex of EXERCISES) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "ex-card";
      b.setAttribute("role", "radio");
      b.setAttribute("aria-checked", String(ex.key === selected));
      b.dataset.key = ex.key;
      const icon = EX_ICONS[ex.key] || "🏋️";
      b.innerHTML = `
        <span class="ex-icon">${icon}</span>
        <span class="ex-name">${ex.name}</span>
        <span class="ex-range">${ex.joint} ${Math.round(ex.rest_angle)}°→${Math.round(ex.peak_angle)}°</span>
      `;
      b.addEventListener("click", () => selectExercise(ex.key));
      els.picker.appendChild(b);
    }
  }

  function selectExercise(key) {
    if (session) return;
    selected = key;
    store.set("pv.exercise", key);
    for (const b of els.picker.children) b.setAttribute("aria-checked", String(b.dataset.key === key));
    const ex = exByKey(key);
    els.desc.textContent = ex.description;
    els.tip.textContent = ex.camera_tip;
    els.jointLabel.textContent = ex.joint;
    els.feedback.textContent = `${ex.cue_start}. Press Start Workout to begin!`;
    els.feedback.dataset.tone = "";
    drawGauge(ex);
    setNeedle(null);
  }

  // --------------------------------------------------------- GONIOMETER
  const CX = 110, CY = 112, R = 88;
  const NS = "http://www.w3.org/2000/svg";
  const polar = (deg, r = R) => {
    const t = (deg * Math.PI) / 180;
    return [CX - r * Math.cos(t), CY - r * Math.sin(t)];
  };
  const arcPath = (a1, a2, r = R) => {
    const [x1, y1] = polar(a1, r), [x2, y2] = polar(a2, r);
    return `M${x1.toFixed(2)} ${y1.toFixed(2)} A${r} ${r} 0 0 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
  };
  function svgEl(tag, attrs, parent) {
    const el = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    parent.appendChild(el);
    return el;
  }

  function drawGauge(ex) {
    const g = els.gonio;
    if (!g) return;
    g.innerHTML = "";
    drawnFor = ex.key;
    const decreasing = ex.peak_angle < ex.rest_angle;
    const rest = decreasing ? [ex.rest_angle, 180] : [0, ex.rest_angle];
    const peak = decreasing ? [0, ex.peak_angle] : [ex.peak_angle, 180];

    svgEl("path", { d: arcPath(0, 180), class: "g-track", fill: "none", "stroke-width": 12 }, g);
    svgEl("path", { d: arcPath(...rest), class: "g-rest", fill: "none", "stroke-width": 12 }, g);
    svgEl("path", { d: arcPath(...peak), class: "g-peak", fill: "none", "stroke-width": 12 }, g);

    for (let a = 0; a <= 180; a += 10) {
      const major = a % 30 === 0;
      const [x1, y1] = polar(a, R + 8);
      const [x2, y2] = polar(a, R + (major ? 14 : 11));
      svgEl("line", { x1, y1, x2, y2, class: "g-tick", "stroke-width": major ? 1.4 : 0.8 }, g);
      if (major) {
        const [lx, ly] = polar(a, R + 22);
        const t = svgEl("text", { x: lx, y: ly + 3, "text-anchor": "middle", class: "g-label" }, g);
        t.textContent = a;
      }
    }
    const zoneLabel = (range, text, cls) => {
      const mid = (range[0] + range[1]) / 2;
      const [x, y] = polar(mid, R - 28);
      const t = svgEl("text", { x, y: y + 3, "text-anchor": "middle", class: `g-zone-label ${cls}` }, g);
      t.textContent = text;
    };
    zoneLabel(rest, "START", "rest");
    zoneLabel(peak, "TARGET", "peak");

    needle = svgEl("line", { x1: CX, y1: CY, x2: CX - R + 4, y2: CY, class: "g-needle" }, g);
    svgEl("circle", { cx: CX, cy: CY, r: 6, class: "g-hub" }, g);
    valueText = svgEl("text", { x: CX, y: CY - 26, "text-anchor": "middle", class: "g-value" }, g);
  }

  function setNeedle(angle) {
    if (!needle) return;
    if (angle == null) {
      needle.style.opacity = "0.25";
      needle.setAttribute("transform", `rotate(90 ${CX} ${CY})`);
      valueText.textContent = "–";
      return;
    }
    const a = Math.max(0, Math.min(180, angle));
    needle.style.opacity = "1";
    needle.setAttribute("transform", `rotate(${a.toFixed(1)} ${CX} ${CY})`);
    valueText.textContent = `${Math.round(angle)}°`;
  }

  // ---------------------------------------------------------- CALORIES & TIME
  const fmtTime = (s) => {
    s = Math.floor(s || 0);
    const m = Math.floor(s / 60), sec = s % 60;
    return `${m}:${String(sec).padStart(2, "0")}`;
  };

  function estimateCalories(exerciseKey, reps, elapsedS) {
    const factor = CAL_PER_REP[exerciseKey] || 0.26;
    const mult = currentLevel === "kids" ? 0.8 : (currentLevel === "adult" ? 1.2 : 1.0);
    const repKcal = reps * factor * mult;
    const timeKcal = (elapsedS || 0) * 0.035 * mult;
    return Math.round((repKcal + timeKcal) * 10) / 10;
  }

  function toneFor(text) {
    if (/partial|too fast|can't see|no one/i.test(text)) return "warn";
    if (/done|reached|well done|good/i.test(text)) return "good";
    return "";
  }

  // ------------------------------------------------------------- SPEECH
  function speak(text, isEncouragement = false) {
    if (!els.voice.checked || !("speechSynthesis" in window)) return;
    try {
      if (!isEncouragement) window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.rate = currentLevel === "kids" ? 1.05 : 1.15;
      u.pitch = currentLevel === "kids" ? 1.2 : 1.0;
      u.lang = "en-US";
      window.speechSynthesis.speak(u);
    } catch { /* speech not available */ }
  }

  let cheerTimer = null;
  function triggerCheer(emoji, text) {
    if (!els.cheerOverlay) return;
    clearTimeout(cheerTimer);
    els.cheerOverlay.querySelector(".cheer-emoji").textContent = emoji;
    els.cheerText.textContent = text;
    els.cheerOverlay.hidden = false;
    cheerTimer = setTimeout(() => { els.cheerOverlay.hidden = true; }, 1200);
  }

  // ---------------------------------------------------------- LIVE RENDER
  function render(state) {
    // Camera status
    let st = "ok", txt;
    if (!state.camera_ok) { st = "err"; txt = "Camera not available"; }
    else if (!state.person) { st = "wait"; txt = `Camera on · step into view`; }
    else txt = `Camera on · ready!`;
    els.status.dataset.state = st;
    els.statusText.textContent = txt;
    els.fps.textContent = state.camera_ok ? `${state.fps.toFixed(0)} fps` : "";

    const s = state.session;
    const wasRunning = !!session;
    session = s;
    setRunningUI(!!s, s && s.paused);

    if (!s) {
      if (wasRunning) selectExercise(selected);
      return;
    }

    if (drawnFor !== s.exercise) {
      selected = s.exercise;
      for (const b of els.picker.children) b.setAttribute("aria-checked", String(b.dataset.key === selected));
      drawGauge(exByKey(s.exercise));
    }

    els.reps.textContent = s.reps;
    els.targetShow.textContent = s.target;
    const frac = Math.min(1, s.reps / s.target);
    els.ring.style.strokeDashoffset = String(RING_LEN * (1 - frac));
    els.ring.classList.toggle("done", s.completed);

    // Live calories
    const burned = estimateCalories(s.exercise, s.reps, s.elapsed);
    if (els.calNum) els.calNum.textContent = burned.toFixed(1);

    // Rep milestone celebratory speech
    if (s.rep_id > lastRepId) {
      els.reps.classList.remove("bump");
      void els.reps.offsetWidth;
      els.reps.classList.add("bump");

      const cheers = LEVEL_CONFIG[currentLevel]?.cheers || ["Great!"];
      const randomCheer = cheers[s.reps % cheers.length];

      if (s.reps === s.target) {
        triggerCheer("🏆", "Target Smashed!");
        speak(`${s.reps}. Target reached! Outstanding job!`);
      } else if (s.reps === Math.floor(s.target / 2)) {
        triggerCheer("⚡", "Halfway!");
        speak(`${s.reps}. Halfway there, keep going!`);
      } else {
        if (currentLevel === "kids") {
          triggerCheer("⭐", randomCheer);
          speak(`${s.reps}. ${randomCheer}`);
        } else {
          speak(String(s.reps));
        }
      }
    }
    lastRepId = s.rep_id;

    // Form warning speech (throttled)
    const now = Date.now();
    if (!s.paused && /too fast|incomplete|can't see/i.test(s.feedback)) {
      if (now - lastSpokenCueTime > 5000) {
        lastSpokenCueTime = now;
        if (/too fast/i.test(s.feedback)) speak("Slow down and control the movement", true);
        else if (/can't see/i.test(s.feedback)) speak("Step clearly into camera view", true);
      }
    }

    setNeedle(s.visible ? s.angle : null);
    els.sideShow.textContent = s.active_side ? s.active_side : "";
    for (const li of els.phases) li.classList.toggle("on", s.visible && li.dataset.stage === s.stage);

    els.feedback.textContent = s.paused ? "Paused. Press Resume when you're ready." : s.feedback;
    els.feedback.dataset.tone = s.paused ? "" : toneFor(s.feedback);
    els.time.textContent = fmtTime(s.elapsed);
    els.partial.textContent = s.partial;
    els.rom.textContent = s.avg_rom == null ? "–" : `${Math.round(s.avg_rom)}°`;

    els.badge.hidden = false;
    els.badge.dataset.kind = s.paused ? "paused" : "live";
    els.badge.textContent = s.paused ? "PAUSED" : `${s.name.toUpperCase()} · ${s.reps}`;
  }

  // Switch between Pre-Start card and Live Workout card
  function setRunningUI(running, paused) {
    if (els.preStartCard) els.preStartCard.hidden = running;
    if (els.liveWorkoutCard) els.liveWorkoutCard.hidden = !running;

    els.pause.textContent = paused ? "▶️ Resume" : "⏸️ Pause";
    els.setup.setAttribute("aria-disabled", String(running));
    for (const b of els.picker.children) b.disabled = running;
    els.levelPills.forEach((p) => p.disabled = running);

    if (!running) {
      els.badge.hidden = true;
      els.reps.textContent = "0";
      els.ring.style.strokeDashoffset = String(RING_LEN);
      els.ring.classList.remove("done");
      els.targetShow.textContent = els.target.value || "10";
      els.time.textContent = "0:00";
      if (els.calNum) els.calNum.textContent = "0";
      els.partial.textContent = "0";
      els.rom.textContent = "–";
      els.sideShow.textContent = "";
      for (const li of els.phases) li.classList.remove("on");
    }
  }

  let polling = false, failures = 0;
  async function poll() {
    if (polling) return;
    polling = true;
    try {
      render(await api("/api/state"));
      failures = 0;
    } catch {
      if (++failures > 3) {
        els.status.dataset.state = "err";
        els.statusText.textContent = "Can't reach server. Is app.py running?";
      }
    } finally {
      polling = false;
    }
  }

  // ------------------------------------------------------------ CONTROLS
  async function startSession() {
    const target = parseInt(els.target.value, 10);
    if (!Number.isFinite(target) || target < 1) {
      toast("Enter a target of at least 1 rep.");
      els.target.focus();
      return;
    }
    const profile = els.profile.value.trim() || "Me";
    store.set("pv.profile", profile);
    store.set("pv.target", String(target));
    store.set("pv.side", els.side.value);
    try {
      lastRepId = 0;
      const state = await api("/api/session/start", {
        exercise: selected, side: els.side.value, target, profile,
      });
      render(state);
      speak(`Starting ${exByKey(selected).name}. Stand ready!`);
    } catch (e) { toast(e.message); }
  }

  async function togglePause() {
    if (!session) return;
    try { render(await api("/api/session/pause", { paused: !session.paused })); }
    catch (e) { toast(e.message); }
  }

  async function finishSession() {
    try {
      const res = await api("/api/session/finish", {});
      const s = res.summary;
      const cal = estimateCalories(s.exercise, s.reps, s.duration_s);
      toast(res.saved
        ? `🎉 Great workout! ${s.reps} reps · ${cal} kcal burned in ${fmtTime(s.duration_s)}!`
        : "Nothing to save. No reps were counted in this session.");
      await poll();
      await loadHistory();
    } catch (e) { toast(e.message); }
  }

  let cancelArmed = null;
  async function cancelSession() {
    if (!cancelArmed) {
      els.cancel.textContent = "Confirm discard?";
      cancelArmed = setTimeout(() => { els.cancel.textContent = "✕ Discard"; cancelArmed = null; }, 3000);
      return;
    }
    clearTimeout(cancelArmed);
    cancelArmed = null;
    els.cancel.textContent = "✕ Discard";
    try { await api("/api/session/cancel", {}); await poll(); toast("Session discarded."); }
    catch (e) { toast(e.message); }
  }

  // ------------------------------------------------------------- HISTORY
  async function loadHistory() {
    const p = els.histProfile.value;
    try {
      historyData = await api(`/api/history${p ? `?profile=${encodeURIComponent(p)}` : ""}`);
    } catch { return; }
    renderProfiles(historyData.profiles);
    renderTable(historyData.sessions);
    drawChart(historyData.daily);
  }

  function renderProfiles(list) {
    const current = els.histProfile.value;
    els.histProfile.innerHTML = `<option value="">Everyone</option>`;
    els.profileList.innerHTML = "";
    for (const name of list) {
      const o = document.createElement("option");
      o.value = name; o.textContent = name;
      els.histProfile.appendChild(o);
      const d = document.createElement("option");
      d.value = name;
      els.profileList.appendChild(d);
    }
    els.histProfile.value = list.includes(current) ? current : "";
  }

  function renderTable(rows) {
    els.histBody.innerHTML = "";
    els.histEmpty.hidden = rows.length > 0;
    for (const r of rows) {
      const tr = document.createElement("tr");
      const when = new Date(r.started_at);
      const cells = [
        when.toLocaleDateString(undefined, { day: "numeric", month: "short" }) + ", " +
          when.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }),
        r.profile,
        `${r.exercise_name}${r.side ? ` (${r.side})` : ""}`,
      ];
      for (const c of cells) {
        const td = document.createElement("td"); td.textContent = c; tr.appendChild(td);
      }
      const reps = document.createElement("td");
      reps.className = "num";
      reps.textContent = `${r.reps}/${r.target}`;
      if (r.reps >= r.target) {
        const pill = document.createElement("span");
        pill.className = "pill met"; pill.textContent = "met";
        reps.appendChild(pill);
      }
      tr.appendChild(reps);

      const cal = estimateCalories(r.exercise, r.reps, r.duration_s);
      const calTd = document.createElement("td");
      calTd.className = "num";
      calTd.textContent = `${cal} kcal`;
      tr.appendChild(calTd);

      for (const v of [r.partial_reps, r.avg_rom == null ? "–" : `${Math.round(r.avg_rom)}°`, fmtTime(r.duration_s)]) {
        const td = document.createElement("td"); td.className = "num"; td.textContent = v; tr.appendChild(td);
      }
      const act = document.createElement("td");
      const del = document.createElement("button");
      del.type = "button"; del.className = "del"; del.textContent = "Delete";
      del.setAttribute("aria-label", `Delete session from ${cells[0]}`);
      del.addEventListener("click", async () => {
        if (del.dataset.armed !== "1") {
          del.dataset.armed = "1"; del.textContent = "Confirm?";
          setTimeout(() => { del.dataset.armed = ""; del.textContent = "Delete"; }, 3000);
          return;
        }
        try { await api(`/api/history/${r.id}`, null, "DELETE"); await loadHistory(); }
        catch (e) { toast(e.message); }
      });
      act.appendChild(del);
      tr.appendChild(act);
      els.histBody.appendChild(tr);
    }
  }

  function drawChart(daily) {
    if (!daily) return;
    const c = els.chart;
    const css = getComputedStyle(document.documentElement);
    const col = (n) => css.getPropertyValue(n).trim();
    const dpr = window.devicePixelRatio || 1;
    const w = c.clientWidth, h = 200;
    c.width = w * dpr; c.height = h * dpr; c.style.height = h + "px";
    const ctx = c.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const padL = 30, padB = 26, padT = 18, padR = 6;
    const max = Math.max(10, ...daily.map((d) => d.reps));
    const step = [2, 5, 10, 20, 25, 50, 100, 200, 250, 500].find((s) => max / s <= 5) || 1000;
    const top = Math.ceil(max / step) * step;
    const plotH = h - padB - padT, plotW = w - padL - padR;
    const y = (v) => padT + plotH * (1 - v / top);

    ctx.font = `500 10px ${col("--f-mono")}`;
    ctx.fillStyle = col("--ink-soft");
    ctx.strokeStyle = col("--line");
    ctx.lineWidth = 1;
    ctx.textAlign = "right";
    for (let v = 0; v <= top; v += step) {
      ctx.beginPath(); ctx.moveTo(padL, y(v) + 0.5); ctx.lineTo(w - padR, y(v) + 0.5); ctx.stroke();
      ctx.fillText(String(v), padL - 6, y(v) + 3);
    }
    const slot = plotW / daily.length, bw = Math.min(34, slot * 0.6);
    ctx.textAlign = "center";
    const todayIdx = daily.length - 1;
    daily.forEach((d, i) => {
      const x = padL + slot * i + (slot - bw) / 2;
      const by = y(d.reps);
      ctx.fillStyle = i === todayIdx ? col("--tape") : col("--blue");
      if (d.reps > 0) {
        ctx.beginPath();
        ctx.roundRect ? ctx.roundRect(x, by, bw, padT + plotH - by, [4, 4, 0, 0]) : ctx.rect(x, by, bw, padT + plotH - by);
        ctx.fill();
        ctx.fillStyle = col("--ink");
        ctx.fillText(String(d.reps), x + bw / 2, by - 5);
      }
      ctx.fillStyle = col("--ink-soft");
      const label = i === todayIdx ? "Today" :
        new Date(d.day + "T00:00").toLocaleDateString(undefined, { weekday: "short" });
      ctx.fillText(label, x + bw / 2, h - 8);
    });
  }

  // --------------------------------------------------------------- MISC
  let toastTimer = null;
  function toast(msg) {
    els.toast.textContent = msg;
    els.toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { els.toast.hidden = true; }, 4000);
  }

  function openGuide() {
    els.guideModal.hidden = false;
    document.body.style.overflow = "hidden";
  }
  function closeGuide() {
    els.guideModal.hidden = true;
    document.body.style.overflow = "";
  }

  function init() {
    // Restore theme
    const savedTheme = store.get("pv.theme") || "light";
    applyTheme(savedTheme);

    // Restore level
    const savedLevel = store.get("pv.level") || "student";
    applyLevel(savedLevel);

    selected = exByKey(store.get("pv.exercise")) ? store.get("pv.exercise") : EXERCISES[0].key;
    els.profile.value = store.get("pv.profile") || "";
    els.target.value = store.get("pv.target") || LEVEL_CONFIG[savedLevel].target;
    els.side.value = store.get("pv.side") || "auto";
    els.voice.checked = store.get("pv.voice") !== "0";
    els.ring.style.strokeDasharray = String(RING_LEN);
    els.ring.style.strokeDashoffset = String(RING_LEN);

    renderPicker();
    selectExercise(selected);
    setRunningUI(false, false);

    // Listeners
    els.start.addEventListener("click", startSession);
    els.pause.addEventListener("click", togglePause);
    els.finish.addEventListener("click", finishSession);
    els.cancel.addEventListener("click", cancelSession);
    els.voice.addEventListener("change", () => store.set("pv.voice", els.voice.checked ? "1" : "0"));
    els.target.addEventListener("input", () => { if (!session) els.targetShow.textContent = els.target.value || "10"; });
    els.histProfile.addEventListener("change", loadHistory);
    els.setup.addEventListener("submit", (e) => { e.preventDefault(); startSession(); });

    // Themes
    els.themeBtns.forEach((btn) => {
      btn.addEventListener("click", () => applyTheme(btn.dataset.themeVal));
    });

    // Levels
    els.levelPills.forEach((pill) => {
      pill.addEventListener("click", () => applyLevel(pill.dataset.level));
    });

    // Guide Modal
    els.btnOpenGuide.addEventListener("click", openGuide);
    els.btnCloseGuide.addEventListener("click", closeGuide);
    els.btnCloseGuideFooter.addEventListener("click", closeGuide);
    els.modalBackdrop.addEventListener("click", closeGuide);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !els.guideModal.hidden) closeGuide();
    });

    // Guide Tabs
    els.tabBtns.forEach((tab) => {
      tab.addEventListener("click", () => {
        els.tabBtns.forEach((t) => t.classList.toggle("active", t === tab));
        const targetId = `tab-${tab.dataset.tab}`;
        els.tabPanes.forEach((p) => p.classList.toggle("active", p.id === targetId));
      });
    });

    els.feed.addEventListener("error", () => {
      setTimeout(() => { els.feed.src = `/video_feed?t=${Date.now()}`; }, 1500);
    });
    document.addEventListener("keydown", (e) => {
      if (e.code !== "Space" || /INPUT|SELECT|TEXTAREA|BUTTON/.test(document.activeElement.tagName)) return;
      e.preventDefault();
      session ? togglePause() : startSession();
    });
    window.addEventListener("resize", () => drawChart(historyData && historyData.daily));

    poll();
    setInterval(poll, 150);
    loadHistory();
  }

  init();
})();
