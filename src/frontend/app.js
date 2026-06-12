const transcript = document.getElementById("transcript");
const caption = document.getElementById("caption");
const statusEl = document.getElementById("status");
const textInput = document.getElementById("text-input");
const sendBtn = document.getElementById("send-btn");
const micBtn = document.getElementById("mic-btn");

let ws = null;
let state = "idle";
let reconnectTimer = null;
let typingIndicator = null;
let activeAssistantBubble = null;

const STATUS_LABELS = {
  idle: "Idle",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking…",
};

function scrollTranscript() {
  transcript.scrollTop = transcript.scrollHeight;
}

function setState(newState) {
  state = newState;
  statusEl.textContent = STATUS_LABELS[newState] || newState;
  statusEl.className = `status ${newState}`;
  const enabled = newState === "idle";
  textInput.disabled = !enabled;
  sendBtn.disabled = !enabled;
  micBtn.disabled = !enabled;
  micBtn.classList.toggle("active", newState === "listening");
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
}

function ensureAssistantBubble() {
  removeTypingIndicator();
  if (!activeAssistantBubble) {
    activeAssistantBubble = document.createElement("div");
    activeAssistantBubble.className = "bubble assistant streaming";
    transcript.appendChild(activeAssistantBubble);
  }
}

function updateAssistantBubble(text) {
  ensureAssistantBubble();
  activeAssistantBubble.textContent = text;
  scrollTranscript();
}

function finalizeAssistantBubble(text) {
  ensureAssistantBubble();
  activeAssistantBubble.textContent = text;
  activeAssistantBubble.classList.remove("streaming");
  activeAssistantBubble = null;
  scrollTranscript();
}

function handleEvent(event) {
  switch (event.type) {
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
    case "assistant_partial":
      updateAssistantBubble(event.text);
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
    setState("idle");
    reconnectTimer = setTimeout(connect, 2000);
  };
}

function send(action, extra = {}) {
  if (!ws || ws.readyState !== WebSocket.OPEN || state !== "idle") return;
  ws.send(JSON.stringify({ action, ...extra }));
}

sendBtn.addEventListener("click", () => {
  const text = textInput.value.trim();
  if (!text) return;
  textInput.value = "";
  send("send", { text });
});

textInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendBtn.click();
});

micBtn.addEventListener("click", () => send("listen"));

connect();
