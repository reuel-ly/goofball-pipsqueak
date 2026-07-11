const isDesktop = new URLSearchParams(location.search).get("desktop") === "1";
const titlebar = document.getElementById("titlebar");
const closeBtn = document.getElementById("close-btn");
const characterStage = document.getElementById("character-stage");
const characterImg = document.getElementById("character-img");
const chatPanel = document.getElementById("chat-panel");
const transcript = document.getElementById("transcript");
const caption = document.getElementById("caption");
const statusEl = document.getElementById("status");
const textInput = document.getElementById("text-input");
const sendBtn = document.getElementById("send-btn");
const micBtn = document.getElementById("mic-btn");
const loadingScreen = document.getElementById("loading-screen");
const loadingMessage = document.getElementById("loading-message");
const levelWrap = document.getElementById("level-wrap");
const levelFill = document.getElementById("level-fill");

if (isDesktop) {
  document.documentElement.classList.add("desktop-mode");
  titlebar.classList.remove("hidden");
  characterStage.classList.remove("hidden");
  chatPanel.classList.add("closed");
  loadingScreen.classList.add("hidden");
  closeBtn.addEventListener("click", () => {
    window.pywebview.api.close();
  });
}

let ws = null;
let state = "idle";
let appReady = false;
let chatOpen = !isDesktop;
let reconnectTimer = null;
let typingIndicator = null;
let activeAssistantBubble = null;
let assistantStreamText = "";
let busyFlashTimer = null;

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

function setChatOpen(open) {
  if (!isDesktop) return;
  chatOpen = open;
  chatPanel.classList.toggle("closed", !open);
  characterStage.setAttribute("aria-expanded", String(open));
  if (open && appReady) {
    setTimeout(() => textInput.focus(), 180);
  }
}

if (isDesktop) {
  characterStage.setAttribute("role", "button");
  characterStage.setAttribute("aria-label", "Toggle chat");
  characterStage.setAttribute("aria-expanded", "false");
  characterStage.tabIndex = 0;
  characterStage.addEventListener("click", () => setChatOpen(!chatOpen));
  characterStage.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setChatOpen(!chatOpen);
    }
  });
}

function setCharacter(newState) {
  const src = CHARACTER_GIFS[newState] ?? "/assets/idle.gif";
  if (characterImg.getAttribute("src") !== src) characterImg.src = src;
}

function scrollTranscript() {
  transcript.scrollTop = transcript.scrollHeight;
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
}

function finalizeAssistantBubble(text) {
  ensureAssistantBubble();
  activeAssistantBubble.textContent = text;
  activeAssistantBubble.classList.remove("streaming");
  activeAssistantBubble = null;
  assistantStreamText = "";
  scrollTranscript();
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
      break;
    case "status":
      setState(event.state);
      if (event.state === "thinking") {
        showTypingIndicator();
      } else if (event.state === "listening") {
        clearAssistantStream();
        caption.classList.add("hidden");
        caption.textContent = "";
      } else if (event.state === "idle") {
        removeTypingIndicator();
        activeAssistantBubble = null;
      }
      break;
    case "partial":
      caption.classList.remove("hidden");
      caption.textContent = event.text;
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
      break;
    case "assistant":
      finalizeAssistantBubble(event.text);
      break;
    case "error":
      if (!appReady) {
        if (isDesktop) {
          setChatOpen(true);
          addBubble("assistant", `Error: ${event.message}`);
        } else {
          loadingMessage.textContent = event.message;
        }
        break;
      }
      clearAssistantStream();
      addBubble("assistant", `Error: ${event.message}`);
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
