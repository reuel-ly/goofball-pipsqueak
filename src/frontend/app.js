const isDesktop = new URLSearchParams(location.search).get("desktop") === "1";
const titlebar = document.getElementById("titlebar");
const closeBtn = document.getElementById("close-btn");
const characterStage = document.getElementById("character-stage");
const characterImg = document.getElementById("character-img");
const transcript = document.getElementById("transcript");
const caption = document.getElementById("caption");
const answerBubble = document.getElementById("answer-bubble");
const statusEl = document.getElementById("status");
const textInput = document.getElementById("text-input");
const sendBtn = document.getElementById("send-btn");
const micBtn = document.getElementById("mic-btn");
const loadingScreen = document.getElementById("loading-screen");
const loadingMessage = document.getElementById("loading-message");
const levelWrap = document.getElementById("level-wrap");
const levelFill = document.getElementById("level-fill");

const ANSWER_FADE_MS = 10_000;
const ANSWER_FADE_TRANSITION_MS = 400;

if (isDesktop) {
  document.documentElement.classList.add("desktop-mode");
  titlebar.classList.remove("hidden");
  characterStage.classList.remove("hidden");
  loadingScreen.classList.add("hidden");
  closeBtn.addEventListener("click", () => {
    window.pywebview.api.close();
  });
}

let ws = null;
let state = "idle";
let appReady = false;
let reconnectTimer = null;
let typingIndicator = null;
let activeAssistantBubble = null;
let assistantStreamText = "";
let busyFlashTimer = null;
let answerFadeTimer = null;
let answerClearTimer = null;

const STATUS_LABELS = {
  idle: "Idle",
  loading: "Loading…",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking…",
};

const CHARACTER_GIFS = {
  idle:      "/assets/idle.gif",
  loading:   "/assets/idle.gif",
  listening: "/assets/listening.gif",
  thinking:  "/assets/thinking.gif",
  speaking:  "/assets/speaking.gif",
};

function setCharacter(newState) {
  const src = CHARACTER_GIFS[newState] ?? "/assets/idle.gif";
  if (characterImg.getAttribute("src") !== src) characterImg.src = src;
}

function scrollTranscript() {
  transcript.scrollTop = transcript.scrollHeight;
}

function clearAnswerFadeTimers() {
  if (answerFadeTimer) {
    clearTimeout(answerFadeTimer);
    answerFadeTimer = null;
  }
  if (answerClearTimer) {
    clearTimeout(answerClearTimer);
    answerClearTimer = null;
  }
}

function hideAnswerBubble() {
  if (!isDesktop || !answerBubble) return;
  clearAnswerFadeTimers();
  answerBubble.classList.add("hidden");
  answerBubble.classList.remove("fading", "streaming", "caption-mode");
  answerBubble.textContent = "";
}

function showAnswerBubble(text, { streaming = false, captionMode = false } = {}) {
  if (!isDesktop || !answerBubble) return;
  clearAnswerFadeTimers();
  answerBubble.textContent = text;
  answerBubble.classList.toggle("streaming", streaming);
  answerBubble.classList.toggle("caption-mode", captionMode);
  answerBubble.classList.remove("hidden", "fading");
}

function scheduleAnswerFade() {
  if (!isDesktop || !answerBubble) return;
  clearAnswerFadeTimers();
  answerFadeTimer = setTimeout(() => {
    answerBubble.classList.add("fading");
    answerBubble.classList.remove("streaming");
    answerClearTimer = setTimeout(() => {
      hideAnswerBubble();
    }, ANSWER_FADE_TRANSITION_MS);
  }, ANSWER_FADE_MS);
}

function setState(newState) {
  state = newState;
  statusEl.textContent = STATUS_LABELS[newState] || newState;
  statusEl.className = `status ${newState}`;
  const idle = appReady && newState === "idle";
  const generating = newState === "thinking" || newState === "speaking";
  const listening = newState === "listening";

  textInput.disabled = !idle;
  // Send doubles as Stop while a reply is being generated or spoken.
  sendBtn.disabled = !appReady || listening || newState === "loading";
  sendBtn.textContent = generating ? "Stop" : "Send";
  sendBtn.classList.toggle("stop", generating);
  // Mic doubles as Cancel while listening.
  micBtn.disabled = !appReady || generating || newState === "loading";
  micBtn.classList.toggle("active", listening);
  micBtn.title = listening ? "Cancel listening" : "Push to talk";

  levelWrap.classList.toggle("hidden", !listening);
  if (!listening) levelFill.style.width = "0%";
  setCharacter(newState);

  if (isDesktop && idle && appReady) {
    textInput.focus();
  }
}

function addBubble(role, text) {
  const el = document.createElement("div");
  el.className = `bubble ${role}`;
  el.textContent = text;
  transcript.appendChild(el);
  scrollTranscript();
  return el;
}

function removeTypingIndicator() {
  if (typingIndicator) {
    typingIndicator.remove();
    typingIndicator = null;
  }
}

function showTypingIndicator() {
  removeTypingIndicator();
  typingIndicator = document.createElement("div");
  typingIndicator.className = "bubble assistant typing";
  typingIndicator.innerHTML = "<span></span><span></span><span></span>";
  transcript.appendChild(typingIndicator);
  scrollTranscript();
}

function clearAssistantStream() {
  removeTypingIndicator();
  activeAssistantBubble = null;
  assistantStreamText = "";
}

function ensureAssistantBubble() {
  removeTypingIndicator();
  if (!activeAssistantBubble) {
    activeAssistantBubble = document.createElement("div");
    activeAssistantBubble.className = "bubble assistant streaming";
    transcript.appendChild(activeAssistantBubble);
  }
}

function appendAssistantDelta(delta) {
  ensureAssistantBubble();
  assistantStreamText += delta;
  activeAssistantBubble.textContent = assistantStreamText;
  scrollTranscript();
  if (isDesktop) {
    showAnswerBubble(assistantStreamText, { streaming: true });
  }
}

function finalizeAssistantBubble(text) {
  ensureAssistantBubble();
  activeAssistantBubble.textContent = text;
  activeAssistantBubble.classList.remove("streaming");
  activeAssistantBubble = null;
  assistantStreamText = "";
  scrollTranscript();
  if (isDesktop) {
    showAnswerBubble(text, { streaming: false });
    scheduleAnswerFade();
  }
}

function flashBusy() {
  statusEl.classList.add("flash");
  if (busyFlashTimer) clearTimeout(busyFlashTimer);
  busyFlashTimer = setTimeout(() => statusEl.classList.remove("flash"), 600);
}

function setLevel(value) {
  // Typical speech RMS is ~0.02-0.25; scale so normal speech fills the bar.
  const pct = Math.min(100, value * 400);
  levelFill.style.width = `${pct}%`;
}

function handleEvent(event) {
  switch (event.type) {
    case "ready":
      appReady = true;
      loadingScreen.classList.add("hidden");
      setState(state);
      if (isDesktop) textInput.focus();
      break;
    case "status":
      setState(event.state);
      if (event.state === "thinking") {
        showTypingIndicator();
        if (isDesktop) {
          showAnswerBubble("…", { streaming: true });
        }
      } else if (event.state === "listening") {
        clearAssistantStream();
        caption.classList.add("hidden");
        caption.textContent = "";
        if (isDesktop) {
          showAnswerBubble("Listening…", { captionMode: true });
        }
      } else if (event.state === "idle") {
        removeTypingIndicator();
        activeAssistantBubble = null;
      }
      break;
    case "partial":
      caption.classList.remove("hidden");
      caption.textContent = event.text;
      if (isDesktop) {
        showAnswerBubble(event.text, { captionMode: true });
      }
      break;
    case "level":
      setLevel(event.value);
      break;
    case "busy":
      flashBusy();
      break;
    case "assistant_partial":
      appendAssistantDelta(event.delta);
      break;
    case "user":
      caption.classList.add("hidden");
      caption.textContent = "";
      addBubble("user", event.text);
      if (isDesktop) {
        clearAnswerFadeTimers();
        hideAnswerBubble();
      }
      break;
    case "assistant":
      finalizeAssistantBubble(event.text);
      break;
    case "error":
      if (!appReady) {
        if (isDesktop) {
          addBubble("assistant", `Error: ${event.message}`);
          showAnswerBubble(`Error: ${event.message}`);
          scheduleAnswerFade();
        } else {
          loadingMessage.textContent = event.message;
        }
        break;
      }
      clearAssistantStream();
      addBubble("assistant", `Error: ${event.message}`);
      if (isDesktop) {
        showAnswerBubble(`Error: ${event.message}`);
        scheduleAnswerFade();
      }
      break;
  }
}

function connect() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${protocol}//${location.host}/ws`);

  ws.onopen = () => {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  };

  ws.onmessage = (msg) => {
    handleEvent(JSON.parse(msg.data));
  };

  ws.onclose = () => {
    clearAssistantStream();
    if (appReady) {
      setState("idle");
    }
    reconnectTimer = setTimeout(connect, 2000);
  };
}

function wsSend(payload) {
  if (!ws || ws.readyState !== WebSocket.OPEN || !appReady) return;
  ws.send(JSON.stringify(payload));
}

function send(action, extra = {}) {
  if (state !== "idle") return;
  if (isDesktop) {
    clearAnswerFadeTimers();
  }
  wsSend({ action, ...extra });
}

function sendStop() {
  if (state === "listening" || state === "thinking" || state === "speaking") {
    wsSend({ action: "stop" });
  }
}

sendBtn.addEventListener("click", () => {
  if (state === "thinking" || state === "speaking") {
    sendStop();
    return;
  }
  const text = textInput.value.trim();
  if (!text) return;
  textInput.value = "";
  send("send", { text });
});

textInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendBtn.click();
});

micBtn.addEventListener("click", () => {
  if (state === "listening") {
    sendStop();
  } else {
    send("listen");
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    sendStop();
  } else if (e.key === "m" && document.activeElement !== textInput && state === "idle") {
    e.preventDefault();
    send("listen");
  }
});

setState("loading");
connect();
