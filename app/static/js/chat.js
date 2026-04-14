"use strict";

// ── E2E Encryption helpers (AES-256 via CryptoJS) ────────────────────────────
// The encryption key is derived from the room name + a shared app secret.
// In a real deployment you'd exchange keys via Diffie-Hellman.
const APP_SALT = "securechat-e2e-salt-v1";

function getRoomKey(roomName) {
  return CryptoJS.SHA256(APP_SALT + roomName).toString();
}

function encrypt(plaintext, key) {
  const iv  = CryptoJS.lib.WordArray.random(16);
  const enc = CryptoJS.AES.encrypt(plaintext, CryptoJS.enc.Hex.parse(key), {
    iv, mode: CryptoJS.mode.CBC, padding: CryptoJS.pad.Pkcs7,
  });
  return { ciphertext: enc.toString(), iv: iv.toString() };
}

function decrypt(ciphertext, iv, key) {
  try {
    const dec = CryptoJS.AES.decrypt(ciphertext, CryptoJS.enc.Hex.parse(key), {
      iv: CryptoJS.enc.Hex.parse(iv),
      mode: CryptoJS.mode.CBC,
      padding: CryptoJS.pad.Pkcs7,
    });
    return dec.toString(CryptoJS.enc.Utf8) || "[encrypted]";
  } catch {
    return "[encrypted]";
  }
}

// ── State ─────────────────────────────────────────────────────────────────────
let currentRoomId   = null;
let currentRoomName = null;
let pendingRoomId   = null;
let pendingRoomPrivate = false;
let roomKey         = null;

const socket = io({ transports: ["websocket", "polling"] });

// ── DOM refs ──────────────────────────────────────────────────────────────────
const messagesEl   = document.getElementById("messages");
const msgInput     = document.getElementById("msg-input");
const roomNameEl   = document.getElementById("room-name");
const roomIconEl   = document.getElementById("room-icon");
const userCountEl  = document.getElementById("user-count");
const onlineBadge  = document.getElementById("online-badge");
const chatView     = document.getElementById("chat-view");
const welcomeEl    = document.getElementById("welcome");

// ── Helpers ───────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s)
    .replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

function scrollBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function setOnline(count) {
  if (count === undefined) return;
  userCountEl.textContent = count;
  onlineBadge.textContent = count + " online";
}

function appendSystem(text) {
  const d = document.createElement("div");
  d.className = "sys-msg";
  d.textContent = text;
  messagesEl.appendChild(d);
  scrollBottom();
}

function appendMessage(msg) {
  const mine = msg.username === MY_USERNAME;

  // Date divider
  const lastDate = messagesEl.dataset.lastDate;
  if (msg.date && msg.date !== lastDate) {
    const div = document.createElement("div");
    div.className = "date-divider";
    div.textContent = msg.date === new Date().toISOString().slice(0,10) ? "Today" : msg.date;
    messagesEl.appendChild(div);
    messagesEl.dataset.lastDate = msg.date;
  }

  // Decrypt message
  let displayText = msg.content;
  if (msg.type === "text" && roomKey) {
    displayText = decrypt(msg.content, msg.iv, roomKey);
  }

  const wrap = document.createElement("div");
  wrap.className = `msg${mine ? " mine" : ""}`;

  let bodyHtml = "";
  if (msg.type === "file") {
    bodyHtml = `<a class="msg-file" href="${esc(msg.file_url)}" target="_blank">📎 ${esc(msg.file_name)}</a>`;
  } else {
    bodyHtml = `<div class="msg-text">${esc(displayText)}</div>`;
  }

  wrap.innerHTML = `
    <div class="msg-avatar">${esc(msg.avatar || msg.username[0].toUpperCase())}</div>
    <div class="msg-body">
      <div class="msg-meta">
        <span class="msg-user">${esc(msg.username)}</span>
        <span class="msg-time">${esc(msg.time)}</span>
      </div>
      ${bodyHtml}
    </div>`;

  messagesEl.appendChild(wrap);
  scrollBottom();
}

// ── Room selection ────────────────────────────────────────────────────────────
window.selectRoom = async function(roomId, roomName, isPrivate) {
  if (roomId === currentRoomId) return;

  // If private, check if already authenticated
  if (isPrivate) {
    pendingRoomId = roomId;
    pendingRoomName = roomName;
    document.getElementById("room-pwd-modal").style.display = "flex";
    document.getElementById("room-pwd-input").value = "";
    setTimeout(() => document.getElementById("room-pwd-input").focus(), 100);
    return;
  }

  await switchToRoom(roomId, roomName, false);
};

async function switchToRoom(roomId, roomName, isPrivate) {
  if (currentRoomId) socket.emit("leave", { room_id: currentRoomId });

  currentRoomId   = roomId;
  currentRoomName = roomName;
  roomKey         = getRoomKey(roomName);

  // Update UI
  roomNameEl.textContent   = roomName;
  roomIconEl.textContent   = isPrivate ? "🔒" : "#";
  messagesEl.innerHTML     = "";
  messagesEl.dataset.lastDate = "";

  document.querySelectorAll(".room-btn").forEach(b => {
    b.classList.toggle("active", parseInt(b.dataset.id) === roomId);
  });

  welcomeEl.style.display  = "none";
  chatView.style.display   = "flex";
  chatView.style.flexDirection = "column";

  msgInput.placeholder = `Message #${roomName}...`;
  msgInput.focus();

  // Load history
  try {
    const res  = await fetch(`/api/rooms/${roomId}/history`);
    const msgs = await res.json();
    if (Array.isArray(msgs)) msgs.forEach(appendMessage);
  } catch {}

  socket.emit("join", { room_id: roomId });
}

// ── Room password modal ───────────────────────────────────────────────────────
window.submitRoomPwd = async function() {
  const pwd = document.getElementById("room-pwd-input").value;
  try {
    const res = await fetch(`/api/rooms/${pendingRoomId}/join`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: pwd }),
    });
    if (res.ok) {
      closeRoomPwd();
      await switchToRoom(pendingRoomId, pendingRoomName, true);
    } else {
      const d = await res.json();
      alert(d.error || "Wrong password");
    }
  } catch { alert("Error joining room"); }
};

window.closeRoomPwd = function() {
  document.getElementById("room-pwd-modal").style.display = "none";
};

// ── New room modal ────────────────────────────────────────────────────────────
window.openNewRoom = function() {
  document.getElementById("new-room-modal").style.display = "flex";
  setTimeout(() => document.getElementById("new-room-name").focus(), 100);
};

window.closeNewRoom = function() {
  document.getElementById("new-room-modal").style.display = "none";
};

window.createRoom = async function() {
  const name = document.getElementById("new-room-name").value.trim();
  const desc = document.getElementById("new-room-desc").value.trim();
  const pwd  = document.getElementById("new-room-pwd").value;

  if (!name) return alert("Room name required");

  try {
    const res = await fetch("/api/rooms", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description: desc, password: pwd }),
    });
    const d = await res.json();
    if (!res.ok) return alert(d.error || "Error creating room");
    closeNewRoom();
  } catch { alert("Error creating room"); }
};

// ── Send message ──────────────────────────────────────────────────────────────
window.sendMessage = function() {
  const text = msgInput.value.trim();
  if (!text || !currentRoomId) return;

  const { ciphertext, iv } = encrypt(text, roomKey);
  socket.emit("message", {
    room_id: currentRoomId,
    content: ciphertext,
    iv,
    type: "text",
  });
  msgInput.value = "";
};

// ── File upload ───────────────────────────────────────────────────────────────
window.uploadFile = async function(input) {
  if (!input.files.length || !currentRoomId) return;
  const file = input.files[0];
  const form = new FormData();
  form.append("file", file);

  appendSystem("Uploading file…");

  try {
    const res  = await fetch("/api/upload", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) return appendSystem("Upload failed: " + (data.error || "unknown error"));

    const { ciphertext, iv } = encrypt(data.name, roomKey);
    socket.emit("message", {
      room_id:   currentRoomId,
      content:   ciphertext,
      iv,
      type:      "file",
      file_url:  data.url,
      file_name: data.name,
    });
  } catch { appendSystem("Upload error"); }

  input.value = "";
};

// ── Socket events ─────────────────────────────────────────────────────────────
socket.on("connect", () => {
  if (currentRoomId) socket.emit("join", { room_id: currentRoomId });
});

socket.on("disconnect", () => appendSystem("⚠ Disconnected — reconnecting…"));

socket.on("message", (msg) => {
  if (!currentRoomId) return;
  appendMessage(msg);
});

socket.on("system", ({ msg, count }) => {
  appendSystem(msg);
  setOnline(count);
});

socket.on("room_created", (room) => {
  // Add new room to sidebar dynamically
  const nav = document.querySelector(".rooms");
  const btn = document.createElement("button");
  btn.className = "room-btn";
  btn.dataset.id = room.id;
  btn.dataset.name = room.name;
  btn.dataset.private = room.private;
  btn.onclick = () => selectRoom(room.id, room.name, room.private);
  btn.innerHTML = `<span class="hash">${room.private ? "🔒" : "#"}</span><span class="room-label">${esc(room.name)}</span>`;
  nav.appendChild(btn);
});

socket.on("error", ({ msg }) => appendSystem("⚠ " + msg));

socket.on("joined", () => {});

// ── Keyboard shortcuts ────────────────────────────────────────────────────────
msgInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

document.getElementById("room-pwd-input")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") submitRoomPwd();
});

// Close modals on overlay click
document.querySelectorAll(".modal-overlay").forEach(overlay => {
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.style.display = "none";
  });
});
