const transcript = document.getElementById("transcript");
const caption = document.getElementById("caption");
const statusEl = document.getElementById("status");
const textInput = document.getElementById("text-input");
const sendBtn = document.getElementById("send-btn");
const micBtn = document.getElementById("mic-btn");

let ws = null;
let state = "idle";
let reconnectTimer = null;

const STATUS_LABELS = {
  idle: "Idle",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking…",
};

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
  transcript.scrollTop = transcript.scrollHeight;
}

function handleEvent(event) {
  switch (event.type) {
    case "status":
      setState(event.state);
      if (event.state !== "listening") {
        caption.classList.add("hidden");
        caption.textContent = "";
      }
      break;
    case "partial":
      caption.classList.remove("hidden");
      caption.textContent = event.text;
      break;
    case "user":
      caption.classList.add("hidden");
      caption.textContent = "";
      addBubble("user", event.text);
      break;
    case "assistant":
      addBubble("assistant", event.text);
      break;
    case "error":
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
