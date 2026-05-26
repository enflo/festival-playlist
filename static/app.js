const $ = (sel) => document.querySelector(sel);

const landingSection = $("#landing-section");
const playlistsSection = $("#playlists-section");
const uploadSection = $("#upload-section");
const reviewSection = $("#review-section");
const resultSection = $("#result-section");
const loginModal = $("#login-modal");
const errorBar = $("#error-bar");

let selectedFile = null;
let errorTimeout = null;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function showError(msg) {
  $("#error-msg").textContent = msg;
  errorBar.hidden = false;
  clearTimeout(errorTimeout);
  errorTimeout = setTimeout(clearError, 8000);
}

function clearError() {
  errorBar.hidden = true;
  clearTimeout(errorTimeout);
}

$("#error-dismiss").addEventListener("click", clearError);

function hideAll() {
  landingSection.hidden = true;
  playlistsSection.hidden = true;
  uploadSection.hidden = true;
  reviewSection.hidden = true;
  resultSection.hidden = true;
  clearError();
}

async function api(url, opts = {}) {
  const resp = await fetch(url, opts);
  const data = await resp.json();
  if (!resp.ok) {
    throw new Error(data.detail || `Request failed (${resp.status})`);
  }
  return data;
}

// ---------------------------------------------------------------------------
// Modal
// ---------------------------------------------------------------------------

function openLoginModal() {
  loginModal.hidden = false;
}

function closeLoginModal() {
  loginModal.hidden = true;
}

$("#modal-close").addEventListener("click", closeLoginModal);
loginModal.addEventListener("click", (e) => {
  if (e.target === loginModal) closeLoginModal();
});

// Both login buttons open the modal
$("#header-login-btn").addEventListener("click", openLoginModal);
$("#landing-login-btn").addEventListener("click", openLoginModal);

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

async function checkAuth() {
  try {
    const data = await api("/me");
    hideAll();
    console.log(data);
    if (data.logged_in) {
      $("#header-login-btn").hidden = true;
      $("#header-user").hidden = false;
      $("#header-username").textContent = data.display_name;
      $("#greeting").textContent = `Hi, ${data.display_name}`;
      playlistsSection.hidden = false;
      loadPlaylists();
    } else {
      $("#header-login-btn").hidden = false;
      $("#header-user").hidden = true;
      landingSection.hidden = false;
    }
  } catch {
    hideAll();
    $("#header-login-btn").hidden = false;
    $("#header-user").hidden = true;
    landingSection.hidden = false;
  }
}

async function loadPlaylists() {
  const list = $("#playlists-list");
  const noPlaylists = $("#no-playlists");
  const loading = $("#playlists-loading");
  list.innerHTML = "";
  noPlaylists.hidden = true;
  loading.hidden = false;

  try {
    const data = await api("/playlists");
    if (data.playlists.length === 0) {
      noPlaylists.hidden = false;
    } else {
      for (const p of data.playlists) {
        const li = document.createElement("li");
        li.className = "playlist-item";
        li.innerHTML = `
          ${p.image ? `<img src="${p.image}" alt="" class="playlist-thumb">` : '<div class="playlist-thumb placeholder"></div>'}
          <div class="playlist-info">
            <a href="${p.url}" target="_blank" rel="noopener">${p.name}</a>
            <span>${p.tracks} tracks</span>
          </div>
        `;
        list.appendChild(li);
      }
    }
  } catch {
    noPlaylists.hidden = false;
  } finally {
    loading.hidden = true;
  }
}

function showUpload() {
  selectedFile = null;
  preview.hidden = true;
  extractBtn.hidden = true;
  fileInput.value = "";
  dropZone.classList.remove("has-file");
  $("#drop-zone-text").textContent = "Drag & drop a lineup poster here, or click to select";
  hideAll();
  uploadSection.hidden = false;
}

$("#add-new-btn").addEventListener("click", showUpload);

$("#back-to-playlists").addEventListener("click", () => {
  hideAll();
  playlistsSection.hidden = false;
});

$("#logout-btn").addEventListener("click", async () => {
  await api("/logout", { method: "POST" });
  $("#header-username").textContent = "";
  checkAuth();
});

// ---------------------------------------------------------------------------
// File upload
// ---------------------------------------------------------------------------

const dropZone = $("#drop-zone");
const fileInput = $("#file-input");
const preview = $("#preview");
const extractBtn = $("#extract-btn");

dropZone.addEventListener("click", () => fileInput.click());

dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("dragover");
});

dropZone.addEventListener("dragleave", () => {
  dropZone.classList.remove("dragover");
});

dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("dragover");
  if (e.dataTransfer.files.length) {
    handleFile(e.dataTransfer.files[0]);
  }
});

fileInput.addEventListener("change", () => {
  if (fileInput.files.length) {
    handleFile(fileInput.files[0]);
  }
});

function handleFile(file) {
  selectedFile = file;
  preview.src = URL.createObjectURL(file);
  preview.hidden = false;
  extractBtn.hidden = false;
  extractBtn.disabled = false;
  dropZone.classList.add("has-file");
  $("#drop-zone-text").textContent = `${file.name} — click to change`;
  clearError();
}

// ---------------------------------------------------------------------------
// Extract artists
// ---------------------------------------------------------------------------

extractBtn.addEventListener("click", async () => {
  if (!selectedFile) return;
  clearError();
  extractBtn.disabled = true;
  $("#extract-loading").hidden = false;

  try {
    const form = new FormData();
    form.append("file", selectedFile);
    const data = await api("/extract", { method: "POST", body: form });
    $("#playlist-name").value = data.playlist_name || "Festival Playlist";
    uploadSection.hidden = true;
    showReview(data.artists);
  } catch (err) {
    showError(err.message);
    extractBtn.disabled = false;
  } finally {
    $("#extract-loading").hidden = true;
  }
});

// ---------------------------------------------------------------------------
// Review artists
// ---------------------------------------------------------------------------

function updateArtistCount() {
  const all = $("#artist-list").querySelectorAll("input[type=checkbox]");
  const checked = $("#artist-list").querySelectorAll("input[type=checkbox]:checked");
  $("#artist-count").textContent = `${checked.length} of ${all.length} selected`;
}

function showReview(artists) {
  reviewSection.hidden = false;
  const list = $("#artist-list");
  list.innerHTML = "";
  for (const name of artists) {
    addArtistItem(list, name, true);
  }
  updateArtistCount();
}

function addArtistItem(list, name, checked) {
  const li = document.createElement("li");
  const cb = document.createElement("input");
  cb.type = "checkbox";
  cb.checked = checked;
  cb.addEventListener("change", updateArtistCount);
  const label = document.createElement("span");
  label.textContent = name;
  li.appendChild(cb);
  li.appendChild(label);
  list.appendChild(li);
}

$("#select-all-btn").addEventListener("click", () => {
  for (const cb of $("#artist-list").querySelectorAll("input[type=checkbox]")) {
    cb.checked = true;
  }
  updateArtistCount();
});

$("#deselect-all-btn").addEventListener("click", () => {
  for (const cb of $("#artist-list").querySelectorAll("input[type=checkbox]")) {
    cb.checked = false;
  }
  updateArtistCount();
});

$("#back-to-upload").addEventListener("click", () => {
  reviewSection.hidden = true;
  uploadSection.hidden = false;
});

$("#add-artist-btn").addEventListener("click", () => {
  const input = $("#add-artist-input");
  const name = input.value.trim();
  if (name) {
    addArtistItem($("#artist-list"), name, true);
    updateArtistCount();
    input.value = "";
  }
});

$("#add-artist-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") $("#add-artist-btn").click();
});

// ---------------------------------------------------------------------------
// Create playlist
// ---------------------------------------------------------------------------

$("#create-btn").addEventListener("click", async () => {
  clearError();
  const items = $("#artist-list").querySelectorAll("li");
  const artists = [];
  for (const li of items) {
    if (li.querySelector("input").checked) {
      artists.push(li.querySelector("span").textContent);
    }
  }
  if (!artists.length) {
    showError("Select at least one artist");
    return;
  }

  const playlistName = $("#playlist-name").value.trim() || "Festival Playlist";
  const tracksPerArtist = Math.min(Math.max(parseInt($("#tracks-per-artist").value) || 3, 1), 10);
  $("#create-btn").disabled = true;
  $("#create-loading").hidden = false;

  try {
    const data = await api("/create-playlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ artists, playlist_name: playlistName, tracks_per_artist: tracksPerArtist }),
    });

    reviewSection.hidden = true;
    resultSection.hidden = false;

    $("#playlist-link").href = data.playlist_url;
    $("#track-count").textContent = `${data.tracks_added} tracks added from ${artists.length - data.artists_not_found.length} artists`;

    if (data.artists_not_found.length) {
      $("#not-found-wrapper").hidden = false;
      const ul = $("#not-found-list");
      ul.innerHTML = "";
      for (const a of data.artists_not_found) {
        const li = document.createElement("li");
        li.textContent = a;
        ul.appendChild(li);
      }
    } else {
      $("#not-found-wrapper").hidden = true;
    }
  } catch (err) {
    showError(err.message);
  } finally {
    $("#create-btn").disabled = false;
    $("#create-loading").hidden = true;
  }
});

// ---------------------------------------------------------------------------
// Restart
// ---------------------------------------------------------------------------

$("#restart-btn").addEventListener("click", () => {
  selectedFile = null;
  preview.hidden = true;
  extractBtn.hidden = true;
  fileInput.value = "";
  hideAll();
  playlistsSection.hidden = false;
  loadPlaylists();
});

// ---------------------------------------------------------------------------
// Cookie banner
// ---------------------------------------------------------------------------

function initCookieBanner() {
  if (localStorage.getItem("cookies_accepted")) return;
  const banner = $("#cookie-banner");
  banner.hidden = false;
  $("#cookie-accept").addEventListener("click", () => {
    localStorage.setItem("cookies_accepted", "1");
    banner.hidden = true;
  });
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

checkAuth();
initCookieBanner();
