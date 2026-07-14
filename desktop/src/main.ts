import { getCurrentWindow } from "@tauri-apps/api/window";

import "./styles.css";
import idleGif from "./assets/idle.gif";
import listeningGif from "./assets/listening.gif";
import thinkingGif from "./assets/thinking.gif";
import speakingGif from "./assets/speaking.gif";

const BACKEND_HOST = "127.0.0.1:8000";
const ANSWER_FADE_MS = 10_000;
const ANSWER_FADE_TRANSITION_MS = 400;

type AgentState = "idle" | "loading" | "listening" | "thinking" | "speaking";

interface AgentEvent {
  type: string;
  state?: AgentState;
  text?: string;
  delta?: string;
  value?: number;
  message?: string;
}

const answerBubble = document.getElementById("answer-bubble") as HTMLElement;
const levelWrap = document.getElementById("level-wrap") as HTMLElement;
const levelFill = document.getElementById("level-fill") as HTMLElement;
const textInput = document.getElementById("text-input") as HTMLInputElement;
const sendBtn = document.getElementById("send-btn") as HTMLButtonElement;
const micBtn = document.getElementById("mic-btn") as HTMLButtonElement;
const closeBtn = document.getElementById("close-btn") as HTMLButtonElement;
const characterImg = document.getElementById("character-img") as HTMLImageElement;
const characterBadge = document.getElementById("character-badge") as HTMLElement;

const CHARACTER_GIFS: Record<AgentState, string> = {
  idle: idleGif,
  loading: idleGif,
  listening: listeningGif,
  thinking: thinkingGif,
  speaking: speakingGif,
};

let ws: WebSocket | null = null;
let state: AgentState = "loading";
let appReady = false;
let connected = false;
let reconnectTimer: number | null = null;
let assistantStreamText = "";
let answerFadeTimer: number | null = null;
let answerClearTimer: number | null = null;

function setBadge(text: string | null) {
  if (text) {
    characterBadge.textContent = text;
    characterBadge.classList.remove("hidden");
  } else {
    characterBadge.classList.add("hidden");
  }
}

function refreshBadge() {
  if (!connected) {
    setBadge("Offline");
  } else if (!appReady) {
    setBadge("Loading models…");
  } else {
    setBadge(null);
  }
}

function setCharacter(newState: AgentState) {
  const src = CHARACTER_GIFS[newState] ?? idleGif;
  if (characterImg.getAttribute("src") !== src) {
    characterImg.src = src;
  }
}

function clearAnswerFadeTimers() {
  if (answerFadeTimer !== null) {
    window.clearTimeout(answerFadeTimer);
    answerFadeTimer = null;
  }
  if (answerClearTimer !== null) {
    window.clearTimeout(answerClearTimer);
    answerClearTimer = null;
  }
}

function hideAnswerBubble() {
  clearAnswerFadeTimers();
  answerBubble.classList.add("hidden");
  answerBubble.classList.remove("fading", "streaming", "caption-mode");
  answerBubble.textContent = "";
}

function showAnswerBubble(
  text: string,
  { streaming = false, captionMode = false }: { streaming?: boolean; captionMode?: boolean } = {},
) {
  clearAnswerFadeTimers();
  answerBubble.textContent = text;
  answerBubble.classList.toggle("streaming", streaming);
  answerBubble.classList.toggle("caption-mode", captionMode);
  answerBubble.classList.remove("hidden", "fading");
}

function scheduleAnswerFade() {
  clearAnswerFadeTimers();
  answerFadeTimer = window.setTimeout(() => {
    answerBubble.classList.add("fading");
    answerBubble.classList.remove("streaming");
    answerClearTimer = window.setTimeout(() => {
      hideAnswerBubble();
    }, ANSWER_FADE_TRANSITION_MS);
  }, ANSWER_FADE_MS);
}

function setState(newState: AgentState) {
  state = newState;

  const idle = appReady && connected && newState === "idle";
  const generating = newState === "thinking" || newState === "speaking";
  const listening = newState === "listening";

  textInput.disabled = !idle;
  // Send doubles as Stop while a reply is being generated or spoken.
  sendBtn.disabled = !appReady || !connected || listening || newState === "loading";
  sendBtn.textContent = generating ? "Stop" : "Send";
  sendBtn.classList.toggle("stop", generating);
  // Mic doubles as Cancel while listening.
  micBtn.disabled = !appReady || !connected || generating || newState === "loading";
  micBtn.classList.toggle("active", listening);
  micBtn.title = listening ? "Cancel listening" : "Push to talk";

  levelWrap.classList.toggle("hidden", !listening);
  if (!listening) levelFill.style.width = "0%";

  setCharacter(newState);
  refreshBadge();

  if (idle && appReady) {
    window.setTimeout(() => textInput.focus(), 50);
  }
}

function setLevel(value: number) {
  // Typical speech RMS is ~0.02-0.25; scale so normal speech fills the bar.
  const pct = Math.min(100, value * 400);
  levelFill.style.width = `${pct}%`;
}

function handleEvent(event: AgentEvent) {
  switch (event.type) {
    case "ready":
      appReady = true;
      setState(state === "loading" ? "idle" : state);
      break;
    case "status":
      setState(event.state ?? "idle");
      if (event.state === "thinking") {
        showAnswerBubble("…", { streaming: true });
      } else if (event.state === "listening") {
        assistantStreamText = "";
        showAnswerBubble("Listening…", { captionMode: true });
      }
      break;
    case "partial":
      showAnswerBubble(event.text ?? "", { captionMode: true });
      break;
    case "level":
      setLevel(event.value ?? 0);
      break;
    case "busy":
      break;
    case "assistant_partial":
      assistantStreamText += event.delta ?? "";
      showAnswerBubble(assistantStreamText, { streaming: true });
      break;
    case "user":
      clearAnswerFadeTimers();
      hideAnswerBubble();
      assistantStreamText = "";
      break;
    case "assistant":
      assistantStreamText = "";
      showAnswerBubble(event.text ?? "", { streaming: false });
      scheduleAnswerFade();
      break;
    case "error":
      assistantStreamText = "";
      showAnswerBubble(`Error: ${event.message ?? "unknown error"}`);
      scheduleAnswerFade();
      break;
  }
}

function connect() {
  ws = new WebSocket(`ws://${BACKEND_HOST}/ws`);

  ws.onopen = () => {
    connected = true;
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    setState(state);
  };

  ws.onmessage = (msg) => {
    handleEvent(JSON.parse(msg.data) as AgentEvent);
  };

  ws.onclose = () => {
    connected = false;
    setState(appReady ? "idle" : state);
    reconnectTimer = window.setTimeout(connect, 2000);
  };
}

function wsSend(payload: Record<string, unknown>) {
  if (!ws || ws.readyState !== WebSocket.OPEN || !appReady) return;
  ws.send(JSON.stringify(payload));
}

function send(action: string, extra: Record<string, unknown> = {}) {
  if (state !== "idle") return;
  clearAnswerFadeTimers();
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

closeBtn.addEventListener("click", () => {
  void getCurrentWindow().close();
});

setState("loading");
connect();
