/* MAIKA Direct – sidebar panel (no build step, plain web component). */

const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const SENSITIVITY = [
  ["low", "Thấp"],
  ["medium", "Trung bình"],
  ["high", "Cao"],
];
const RESPONSE = [
  ["wakeword_response_default", "Mặc định"],
  ["wakeword_response_ringtone", "Nhạc báo"],
  ["wakeword_response_silent", "Im lặng"],
];
const QUICK = ["Mấy giờ rồi", "Thời tiết hôm nay thế nào", "Mở nhạc thư giãn", "Đọc tin tức"];

function ago(ts) {
  if (!ts) return "";
  const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
  if (s < 60) return `${s} giây trước`;
  if (s < 3600) return `${Math.round(s / 60)} phút trước`;
  if (s < 86400) return `${Math.round(s / 3600)} giờ trước`;
  return new Date(ts * 1000).toLocaleString("vi-VN");
}

class MaikaDirectPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._info = null;
    this._serial = null;
    this._settings = {};
    this._built = false;
    this._timer = null;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (!this._built) this._build();
    if (first) this._loadInfo();
    this._update();
  }
  get hass() {
    return this._hass;
  }
  set narrow(v) {
    this._narrow = v;
    const mb = this.shadowRoot.querySelector("ha-menu-button");
    if (mb) mb.narrow = v;
  }
  set panel(p) {
    this._panel = p;
  }

  connectedCallback() {
    this._timer = setInterval(() => this._loadInfo(), 5000);
  }
  disconnectedCallback() {
    clearInterval(this._timer);
  }

  // ------------------------------------------------------------- data
  async _ws(msg) {
    return this._hass.callWS(msg);
  }

  async _loadInfo() {
    if (!this._hass) return;
    try {
      this._info = await this._ws({ type: "maika_direct/info" });
    } catch (e) {
      this._info = { accounts: [], error: e.message || String(e) };
    }
    const speakers = this._speakers();
    if (!this._serial || !speakers.find((s) => s.serial === this._serial)) {
      this._serial = speakers[0]?.serial || null;
      if (this._serial) this._loadSettings();
    }
    this._renderChips();
    this._update();
  }

  _speakers() {
    return (this._info?.accounts || []).flatMap((a) => a.speakers.map((s) => ({ ...s, account: a })));
  }
  _current() {
    return this._speakers().find((s) => s.serial === this._serial) || null;
  }
  _state(id) {
    return id ? this._hass.states[id] : undefined;
  }

  async _loadSettings(attempt = 0) {
    const serial = this._serial;
    const req = (this._settingsReq = (this._settingsReq || 0) + 1);
    const box = this.$("#settings-status");
    box.className = "status";
    box.textContent = "Đang tải cài đặt…";
    try {
      const res = await this._ws({ type: "maika_direct/settings/get", serial });
      if (req !== this._settingsReq || serial !== this._serial) return;
      this._settings = res;
      this._fillSettings();
      box.textContent = res.writable ? "" : "Loa này chưa có ID nội bộ – không ghi được cài đặt.";
    } catch (e) {
      if (req !== this._settingsReq) return;
      if (attempt < 2) return setTimeout(() => this._loadSettings(attempt + 1), 2000);
      box.className = "status bad";
      box.textContent = `Không tải được cài đặt: ${e.message || e}`;
    }
  }

  // ------------------------------------------------------------ build
  $(sel) {
    return this.shadowRoot.querySelector(sel);
  }

  _build() {
    this._built = true;
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <div class="toolbar">
        <ha-menu-button></ha-menu-button>
        <div class="title"><span class="logo"></span>MAIKA</div>
        <div class="spacer"></div>
        <span id="stream" class="pill"></span>
      </div>
      <main>
        <div id="error" class="banner" hidden></div>
        <div id="chips" class="chips"></div>
        <div id="empty" class="card empty" hidden>
          Chưa có tài khoản MAIKA Direct nào được tải. Vào <b>Cài đặt → Thiết bị &amp; dịch vụ</b> để thêm.
        </div>
        <div id="grid" class="grid">
          <section class="card hero">
            <div class="hero-top">
              <div class="speaker-art"><div class="ring"></div><ha-icon icon="mdi:speaker"></ha-icon></div>
              <div class="hero-text">
                <h2 id="sp-name">–</h2>
                <div id="sp-meta" class="muted"></div>
                <div class="pills"><span id="sp-online" class="pill"></span><span id="sp-state" class="pill"></span></div>
              </div>
            </div>
            <div class="now">
              <img id="np-img" alt="" hidden />
              <div class="now-text">
                <div id="np-title" class="np-title">Không phát gì</div>
                <div id="np-artist" class="muted"></div>
              </div>
            </div>
            <div class="controls">
              <button class="icon" data-act="prev" title="Bài trước"><ha-icon icon="mdi:skip-previous"></ha-icon></button>
              <button class="icon big" data-act="toggle" title="Phát / tạm dừng"><ha-icon id="pp-icon" icon="mdi:play"></ha-icon></button>
              <button class="icon" data-act="next" title="Bài tiếp"><ha-icon icon="mdi:skip-next"></ha-icon></button>
            </div>
            <div class="row vol">
              <button class="icon" data-act="mute" title="Tắt tiếng"><ha-icon id="mute-icon" icon="mdi:volume-high"></ha-icon></button>
              <input id="volume" type="range" min="0" max="100" step="1" />
              <span id="vol-val" class="vol-val">–</span>
            </div>
            <div class="row actions">
              <button class="chip-btn" data-act="mic"><ha-icon id="mic-icon" icon="mdi:microphone"></ha-icon><span id="mic-label">Micro</span></button>
              <button class="chip-btn" data-act="refresh"><ha-icon icon="mdi:refresh"></ha-icon>Làm mới</button>
              <button class="chip-btn danger" data-act="restart"><ha-icon icon="mdi:restart"></ha-icon>Khởi động lại</button>
            </div>
          </section>

          <section class="card">
            <h3><ha-icon icon="mdi:chat-processing-outline"></ha-icon>Trò chuyện với loa</h3>
            <p class="muted small">Loa xử lý câu chữ như vừa nghe bạn nói.</p>
            <form id="chat-form" class="inline">
              <input id="chat-text" maxlength="500" placeholder="VD: bật nhạc Trịnh Công Sơn" />
              <button class="primary" type="submit">Gửi</button>
            </form>
            <div class="quick">${QUICK.map((q) => `<button class="tag" data-quick="${esc(q)}">${esc(q)}</button>`).join("")}</div>
            <div id="chat-status" class="status"></div>
            <div class="log">
              <div class="log-item"><div class="muted small">Bạn nói gần nhất</div><div id="last-cmd">–</div><div id="last-cmd-t" class="muted small"></div><div id="last-assist" class="assist" hidden></div></div>
              <div class="log-item"><div class="muted small">Loa trả lời gần nhất</div><div id="last-resp">–</div><div id="last-resp-t" class="muted small"></div></div>
            </div>
          </section>

          <section class="card">
            <h3><ha-icon icon="mdi:speaker-wireless"></ha-icon>Phát lên loa</h3>
            <label>Đọc thông báo (TTS)</label>
            <form id="tts-form" class="inline">
              <input id="tts-text" placeholder="VD: Đến giờ ăn cơm rồi" />
              <button class="primary" type="submit">Đọc</button>
            </form>
            <div id="tts-hint" class="muted small"></div>
            <label>Phát từ đường dẫn MP3</label>
            <form id="url-form" class="inline">
              <input id="url-text" placeholder="https://…/bai-hat.mp3" />
              <button class="primary" type="submit">Phát</button>
            </form>
            <div id="play-status" class="status"></div>
          </section>

          <section class="card">
            <h3><ha-icon icon="mdi:tune-variant"></ha-icon>Cài đặt loa</h3>
            <form id="settings-form" class="form">
              <label>Tên loa<input name="name" /></label>
              <label>Tên gọi<input name="calling_name" placeholder="VD: Maika" /></label>
              <label>Địa chỉ<input name="address" /></label>
              <label>Độ nhạy từ đánh thức
                <select name="wakeword_sensitivity_level"><option value="">(chưa rõ)</option>${SENSITIVITY.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select>
              </label>
              <label>Phản hồi khi gọi
                <select name="wakeword_response_type"><option value="">(chưa rõ)</option>${RESPONSE.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select>
              </label>
              <label>Giọng đọc<select name="tts_voice"></select></label>
              <div class="form-actions">
                <span id="settings-status" class="status"></span>
                <button class="primary" type="submit">Lưu cài đặt</button>
              </div>
            </form>
          </section>

          <section class="card">
            <h3><ha-icon icon="mdi:cog-outline"></ha-icon>Cấu hình tích hợp</h3>
            <form id="opt-form" class="form">
              <label>Địa chỉ Home Assistant cho loa tải nhạc / TTS
                <input name="media_base_url" placeholder="http://192.168.1.20:8123" />
                <span class="muted small">IP LAN của máy chạy Home Assistant. Bắt buộc khi HA chạy Docker (URL nội bộ là localhost/172.x).</span>
              </label>
              <label>Chu kỳ làm mới (giây)<input name="scan_interval" type="number" min="15" max="3600" /></label>
              <div class="subhead">Điều khiển nhà bằng giọng nói</div>
              <label class="check"><input name="assist_forward" type="checkbox" />
                <span>Chuyển câu nói với loa sang <b>Assist</b> của Home Assistant
                <span class="muted small">Thiết bị phải bật "chia sẻ với Assist" (Cài đặt → Trợ lý giọng nói → Chia sẻ).</span></span>
              </label>
              <label>Từ mở đầu (tuỳ chọn)
                <input name="assist_prefix" placeholder="để trống = mọi câu, VD: nhà ơi" />
                <span class="muted small">Chỉ câu bắt đầu bằng từ này mới gửi sang Assist (phần còn lại là lệnh).</span>
              </label>
              <label>Đọc kết quả lên loa bằng TTS
                <select name="assist_tts"><option value="">(không đọc)</option></select>
              </label>
              <div class="kv"><span class="muted">Tài khoản</span><span id="acc-title">–</span></div>
              <div class="kv"><span class="muted">Serial</span><span id="acc-serial">–</span></div>
              <div class="form-actions">
                <span id="opt-status" class="status"></span>
                <button class="primary" type="submit">Lưu &amp; tải lại</button>
              </div>
            </form>
          </section>
        </div>
      </main>`;

    const mb = this.$("ha-menu-button");
    mb.hass = this._hass;
    mb.narrow = this._narrow;

    this.shadowRoot.addEventListener("click", (ev) => {
      const act = ev.target.closest("[data-act]")?.dataset.act;
      if (act) this._action(act);
      const quick = ev.target.closest("[data-quick]")?.dataset.quick;
      if (quick) {
        this.$("#chat-text").value = quick;
        this._sendText();
      }
      const chip = ev.target.closest("[data-serial]")?.dataset.serial;
      if (chip && chip !== this._serial) {
        this._serial = chip;
        this._optsFilled = false;
        this._renderChips();
        this._update();
        this._loadSettings();
      }
    });
    const vol = this.$("#volume");
    vol.addEventListener("input", () => (this.$("#vol-val").textContent = `${vol.value}%`));
    vol.addEventListener("change", () =>
      this._service("media_player", "volume_set", { volume_level: Number(vol.value) / 100 })
    );
    this.$("#chat-form").addEventListener("submit", (e) => (e.preventDefault(), this._sendText()));
    this.$("#tts-form").addEventListener("submit", (e) => (e.preventDefault(), this._tts()));
    this.$("#url-form").addEventListener("submit", (e) => (e.preventDefault(), this._cast()));
    this.$("#settings-form").addEventListener("submit", (e) => (e.preventDefault(), this._saveSettings()));
    this.$("#opt-form").addEventListener("submit", (e) => (e.preventDefault(), this._saveOptions()));
  }

  _renderChips() {
    const speakers = this._speakers();
    const chips = this.$("#chips");
    chips.hidden = speakers.length < 2;
    chips.innerHTML = speakers
      .map(
        (s) =>
          `<button class="chip ${s.serial === this._serial ? "on" : ""}" data-serial="${esc(s.serial)}">
             <ha-icon icon="mdi:speaker"></ha-icon>${esc(s.name)}</button>`
      )
      .join("");
  }

  // ----------------------------------------------------------- update
  _update() {
    if (!this._built || !this._hass) return;
    const sp = this._current();
    const err = this.$("#error");
    err.hidden = !this._info?.error;
    err.textContent = this._info?.error ? `Lỗi: ${this._info.error}` : "";
    this.$("#empty").hidden = !!sp || !this._info;
    this.$("#grid").hidden = !sp;
    if (!sp) return;

    const acc = sp.account;
    const stream = this.$("#stream");
    stream.textContent = acc.stream_connected ? "Cloud: trực tiếp" : "Cloud: đang kết nối…";
    stream.className = `pill ${acc.stream_connected ? "ok" : "warn"}`;

    const mp = this._state(sp.entities.media_player);
    const attrs = mp?.attributes || {};
    this.$("#sp-name").textContent = sp.name;
    this.$("#sp-meta").textContent = [sp.model, sp.firmware && `FW ${sp.firmware}`].filter(Boolean).join(" · ");
    const online = this._state(sp.entities.online)?.state;
    const on = this.$("#sp-online");
    on.textContent = online === "on" ? "Trực tuyến" : online === "off" ? "Ngoại tuyến" : "Không rõ";
    on.className = `pill ${online === "on" ? "ok" : online === "off" ? "bad" : ""}`;
    const stateMap = { playing: "Đang phát", paused: "Tạm dừng", idle: "Rảnh", off: "Tắt", unavailable: "Mất kết nối" };
    const st = mp?.state;
    this.$("#sp-state").textContent = stateMap[st] || st || "–";
    this.shadowRoot.host.toggleAttribute("playing", st === "playing" && !attrs.is_volume_muted);

    this.$("#np-title").textContent = attrs.media_title || (st === "playing" ? "Đang phát" : "Không phát gì");
    this.$("#np-artist").textContent = attrs.media_artist || "";
    const img = this.$("#np-img");
    const pic = attrs.entity_picture;
    img.hidden = !pic;
    if (pic && img.getAttribute("src") !== pic) img.src = pic;
    this.$("#pp-icon").setAttribute("icon", st === "playing" ? "mdi:pause" : "mdi:play");

    const vol = this.$("#volume");
    if (attrs.volume_level != null && this.shadowRoot.activeElement !== vol) {
      vol.value = Math.round(attrs.volume_level * 100);
      this.$("#vol-val").textContent = `${vol.value}%`;
    }
    this.$("#mute-icon").setAttribute("icon", attrs.is_volume_muted ? "mdi:volume-off" : "mdi:volume-high");

    const mic = this._state(sp.entities.mic_mute)?.state;
    this.$("#mic-icon").setAttribute("icon", mic === "on" ? "mdi:microphone-off" : "mdi:microphone");
    this.$("#mic-label").textContent = mic === "on" ? "Micro đang tắt" : mic === "off" ? "Micro đang bật" : "Micro";
    this.$('[data-act="mic"]').classList.toggle("active", mic === "on");

    this.$("#last-cmd").textContent = sp.last_command?.text || "–";
    this.$("#last-cmd-t").textContent = ago(sp.last_command?.time);
    const a = sp.last_command?.assist;
    const la = this.$("#last-assist");
    la.hidden = !a;
    if (a) {
      la.className = `assist ${a.success ? "ok" : "bad"}`;
      la.textContent = `Assist: ${a.success ? "✓" : "✗"} ${a.speech || a.type}`;
    }
    this.$("#last-resp").textContent = sp.last_response?.text || "–";
    this.$("#last-resp-t").textContent = ago(sp.last_response?.time);

    const tts = this._ttsEntity();
    this.$("#tts-hint").textContent = tts
      ? `Dùng ${this._hass.states[tts]?.attributes?.friendly_name || tts}. Cần điền địa chỉ HA cho loa ở mục Cấu hình.`
      : "Chưa có dịch vụ TTS nào trong Home Assistant (VD: Google Translate).";

    this.$("#acc-title").textContent = acc.title;
    this.$("#acc-serial").textContent = sp.serial;
    if (!this._optsFilled) {
      this._optsFilled = true;
      this._field("#opt-form", "media_base_url").value = acc.options.media_base_url || "";
      this._field("#opt-form", "scan_interval").value = acc.options.scan_interval;
      this._field("#opt-form", "assist_forward").checked = !!acc.options.assist_forward;
      this._field("#opt-form", "assist_prefix").value = acc.options.assist_prefix || "";
      const ttsSel = this._field("#opt-form", "assist_tts");
      ttsSel.innerHTML =
        `<option value="">(không đọc)</option>` +
        (acc.tts_entities || [])
          .map((id) => `<option value="${esc(id)}">${esc(this._hass.states[id]?.attributes?.friendly_name || id)}</option>`)
          .join("");
      ttsSel.value = acc.options.assist_tts || "";
    }
  }

  _field(form, name) {
    return this.$(`${form} [name="${name}"]`);
  }

  _fillSettings() {
    const f = this.$("#settings-form");
    const fld = (k) => this._field("#settings-form", k);
    const { values = {}, voices = [] } = this._settings;
    fld("tts_voice").innerHTML =
      `<option value="">(giữ nguyên)</option>` +
      voices.map((v) => `<option value="${esc(v.value)}">${esc(v.label)}</option>`).join("");
    for (const key of ["name", "calling_name", "address", "wakeword_sensitivity_level", "wakeword_response_type", "tts_voice"]) {
      fld(key).value = values[key] ?? "";
    }
    f.querySelectorAll("input,select,button").forEach((el) => (el.disabled = !this._settings.writable));
  }

  _ttsEntity() {
    const ids = Object.keys(this._hass.states).filter((id) => id.startsWith("tts."));
    return ids.find((id) => id.includes("google")) || ids[0] || null;
  }

  // ---------------------------------------------------------- actions
  _flash(sel, text, ok = true) {
    const el = this.$(sel);
    el.textContent = text;
    el.className = `status ${ok ? "ok" : "bad"}`;
    clearTimeout(el._t);
    el._t = setTimeout(() => (el.textContent = ""), 5000);
  }

  async _service(domain, service, data = {}, entityKey = "media_player") {
    const sp = this._current();
    const entity_id = sp?.entities[entityKey];
    if (!entity_id) return;
    try {
      await this._hass.callService(domain, service, { entity_id, ...data });
    } catch (e) {
      this._flash("#play-status", e.message || String(e), false);
    }
  }

  async _action(act) {
    const sp = this._current();
    if (!sp) return;
    const mp = this._state(sp.entities.media_player);
    switch (act) {
      case "prev":
        return this._service("media_player", "media_previous_track");
      case "next":
        return this._service("media_player", "media_next_track");
      case "toggle":
        return this._service("media_player", mp?.state === "playing" ? "media_pause" : "media_play");
      case "mute":
        return this._service("media_player", "volume_mute", { is_volume_muted: !mp?.attributes?.is_volume_muted });
      case "mic": {
        const on = this._state(sp.entities.mic_mute)?.state === "on";
        return this._service("switch", on ? "turn_off" : "turn_on", {}, "mic_mute");
      }
      case "refresh":
        await this._service("button", "press", {}, "refresh");
        return this._loadInfo();
      case "restart":
        if (!confirmInline(this.$('[data-act="restart"]'))) return;
        return this._service("button", "press", {}, "restart");
    }
  }

  async _sendText() {
    const input = this.$("#chat-text");
    const text = input.value.trim();
    if (!text || !this._serial) return;
    try {
      await this._ws({ type: "maika_direct/send_text", serial: this._serial, text });
      input.value = "";
      this._flash("#chat-status", `Đã gửi: “${text}”`);
      setTimeout(() => this._loadInfo(), 2500);
    } catch (e) {
      this._flash("#chat-status", e.message || String(e), false);
    }
  }

  async _tts() {
    const text = this.$("#tts-text").value.trim();
    const tts = this._ttsEntity();
    const sp = this._current();
    if (!text || !tts || !sp) return;
    try {
      await this._hass.callService("tts", "speak", {
        entity_id: tts,
        media_player_entity_id: sp.entities.media_player,
        message: text,
        language: "vi",
      });
      this._flash("#play-status", "Đã gửi thông báo tới loa");
    } catch (e) {
      this._flash("#play-status", e.message || String(e), false);
    }
  }

  async _cast() {
    const url = this.$("#url-text").value.trim();
    if (!url || !this._serial) return;
    try {
      await this._ws({ type: "maika_direct/cast", serial: this._serial, url });
      this._flash("#play-status", "Đã gửi đường dẫn tới loa");
    } catch (e) {
      this._flash("#play-status", e.message || String(e), false);
    }
  }

  async _saveSettings() {
    const f = this.$("#settings-form");
    const old = this._settings.values || {};
    const changes = {};
    for (const key of ["name", "calling_name", "address", "wakeword_sensitivity_level", "wakeword_response_type", "tts_voice"]) {
      const v = (this._field("#settings-form", key).value || "").trim();
      if (v && v !== (old[key] ?? "")) changes[key] = v;
    }
    if (!Object.keys(changes).length) return this._flash("#settings-status", "Không có thay đổi");
    try {
      await this._ws({ type: "maika_direct/settings/set", serial: this._serial, changes });
      this._flash("#settings-status", "Đã lưu");
      this._settings.values = { ...old, ...changes };
      this._loadInfo();
    } catch (e) {
      this._flash("#settings-status", e.message || String(e), false);
    }
  }

  async _saveOptions() {
    const sp = this._current();
    const f = this.$("#opt-form");
    try {
      await this._ws({
        type: "maika_direct/options/set",
        entry_id: sp.account.entry_id,
        media_base_url: this._field("#opt-form", "media_base_url").value.trim(),
        scan_interval: Number(this._field("#opt-form", "scan_interval").value) || 60,
        assist_forward: this._field("#opt-form", "assist_forward").checked,
        assist_prefix: this._field("#opt-form", "assist_prefix").value.trim(),
        assist_tts: this._field("#opt-form", "assist_tts").value,
      });
      this._flash("#opt-status", "Đã lưu, đang tải lại tích hợp…");
      this._optsFilled = false;
      setTimeout(() => this._loadInfo(), 4000);
    } catch (e) {
      this._flash("#opt-status", e.message || String(e), false);
    }
  }
}

/* two-tap confirm without browser dialogs */
function confirmInline(btn) {
  if (btn.dataset.armed) {
    delete btn.dataset.armed;
    btn.classList.remove("armed");
    return true;
  }
  btn.dataset.armed = "1";
  btn.classList.add("armed");
  const label = btn.lastChild;
  const old = label.textContent;
  label.textContent = "Bấm lần nữa để xác nhận";
  setTimeout(() => {
    delete btn.dataset.armed;
    btn.classList.remove("armed");
    label.textContent = old;
  }, 3000);
  return false;
}

const STYLE = `
[hidden] { display: none !important; }
:host {
  --mk: #f26b1d; --mk-2: #ff9a3c;
  --mk-soft: color-mix(in srgb, var(--mk) 14%, transparent);
  display: block; min-height: 100%;
  background: var(--primary-background-color);
  color: var(--primary-text-color);
  font-family: var(--paper-font-body1_-_font-family, Roboto, system-ui, sans-serif);
}
* { box-sizing: border-box; }
.toolbar { display: flex; align-items: center; gap: 8px; height: var(--header-height, 56px); padding: 0 12px;
  background: var(--app-header-background-color, var(--primary-background-color));
  color: var(--app-header-text-color, var(--primary-text-color));
  border-bottom: 1px solid var(--divider-color); position: sticky; top: 0; z-index: 2; }
.title { display: flex; align-items: center; gap: 10px; font-size: 20px; font-weight: 500; }
.logo { width: 22px; height: 22px; border-radius: 7px; background: linear-gradient(135deg, var(--mk), var(--mk-2)); box-shadow: 0 0 0 3px var(--mk-soft); }
.spacer { flex: 1; }
main { padding: 16px; max-width: 1400px; margin: 0 auto; }
.grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 360px), 1fr)); align-items: start; }
.card { background: var(--card-background-color, var(--ha-card-background)); border-radius: var(--ha-card-border-radius, 16px);
  border: 1px solid var(--divider-color); padding: 18px; box-shadow: var(--ha-card-box-shadow, none); }
.card h3 { display: flex; align-items: center; gap: 8px; margin: 0 0 12px; font-size: 16px; font-weight: 600; }
.card h3 ha-icon { color: var(--mk); --mdc-icon-size: 20px; }
.empty { text-align: center; padding: 32px; }
.banner { background: var(--error-color); color: #fff; padding: 10px 14px; border-radius: 12px; margin-bottom: 12px; }
.muted { color: var(--secondary-text-color); }
.small { font-size: 12px; }
.pill { display: inline-flex; align-items: center; font-size: 12px; padding: 3px 10px; border-radius: 999px;
  background: var(--secondary-background-color); color: var(--secondary-text-color); white-space: nowrap; }
.pill.ok { background: color-mix(in srgb, var(--success-color, #43a047) 18%, transparent); color: var(--success-color, #43a047); }
.pill.warn { background: color-mix(in srgb, var(--warning-color, #ffa000) 18%, transparent); color: var(--warning-color, #ffa000); }
.pill.bad { background: color-mix(in srgb, var(--error-color, #db4437) 18%, transparent); color: var(--error-color, #db4437); }
.pills { display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; }
.chips { display: flex; gap: 8px; overflow-x: auto; margin-bottom: 14px; }
.chip { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--divider-color); background: var(--card-background-color);
  color: var(--primary-text-color); padding: 8px 14px; border-radius: 999px; cursor: pointer; font: inherit; white-space: nowrap; }
.chip.on { border-color: var(--mk); background: var(--mk-soft); color: var(--mk); }
.hero { grid-row: span 2; }
.hero-top { display: flex; gap: 16px; align-items: center; }
.hero-text h2 { margin: 0; font-size: 22px; }
.speaker-art { position: relative; width: 76px; height: 76px; flex: none; border-radius: 22px; display: grid; place-items: center;
  background: linear-gradient(145deg, var(--mk), var(--mk-2)); color: #fff; --mdc-icon-size: 40px; }
.ring { position: absolute; inset: -4px; border-radius: 26px; border: 2px solid var(--mk); opacity: 0; }
:host([playing]) .ring { animation: pulse 1.8s ease-out infinite; }
@keyframes pulse { 0% { transform: scale(.95); opacity: .7; } 100% { transform: scale(1.25); opacity: 0; } }
@media (prefers-reduced-motion: reduce) { :host([playing]) .ring { animation: none; opacity: .5; } }
.now { display: flex; gap: 12px; align-items: center; margin: 20px 0 8px; padding: 12px; border-radius: 14px; background: var(--secondary-background-color); min-height: 64px; }
.now img { width: 48px; height: 48px; border-radius: 10px; object-fit: cover; }
.np-title { font-weight: 600; }
.controls { display: flex; justify-content: center; gap: 18px; margin: 12px 0; }
button { font: inherit; }
button.icon { width: 44px; height: 44px; border-radius: 50%; border: none; cursor: pointer; display: grid; place-items: center;
  background: var(--secondary-background-color); color: var(--primary-text-color); }
button.icon.big { width: 60px; height: 60px; background: linear-gradient(135deg, var(--mk), var(--mk-2)); color: #fff; --mdc-icon-size: 30px; }
button.icon:hover { filter: brightness(1.1); }
.row { display: flex; align-items: center; gap: 10px; margin-top: 10px; }
.vol input { flex: 1; accent-color: var(--mk); }
.vol-val { width: 44px; text-align: right; font-variant-numeric: tabular-nums; }
.actions { flex-wrap: wrap; margin-top: 16px; }
.chip-btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 12px; border-radius: 12px; cursor: pointer;
  border: 1px solid var(--divider-color); background: transparent; color: var(--primary-text-color); --mdc-icon-size: 18px; }
.chip-btn.active { border-color: var(--mk); color: var(--mk); background: var(--mk-soft); }
.chip-btn.danger.armed { border-color: var(--error-color); color: var(--error-color); }
.inline { display: flex; gap: 8px; }
input, select { width: 100%; font: inherit; color: var(--primary-text-color); background: var(--input-fill-color, var(--secondary-background-color));
  border: 1px solid var(--divider-color); border-radius: 10px; padding: 10px 12px; outline: none; }
input:focus, select:focus { border-color: var(--mk); box-shadow: 0 0 0 3px var(--mk-soft); }
input[type=range] { padding: 0; border: none; background: none; box-shadow: none; }
button.primary { border: none; border-radius: 10px; padding: 10px 16px; cursor: pointer; color: #fff; white-space: nowrap;
  background: linear-gradient(135deg, var(--mk), var(--mk-2)); font-weight: 600; }
button.primary:disabled { opacity: .5; cursor: default; }
.quick { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.tag { border: 1px dashed var(--divider-color); background: transparent; color: var(--secondary-text-color); padding: 5px 10px; border-radius: 999px; cursor: pointer; font-size: 13px; }
.tag:hover { color: var(--mk); border-color: var(--mk); }
.status { font-size: 13px; min-height: 18px; display: block; margin-top: 6px; }
.status.ok { color: var(--success-color, #43a047); } .status.bad { color: var(--error-color); }
.log { display: grid; gap: 10px; margin-top: 12px; }
.log-item { padding: 10px 12px; border-radius: 12px; background: var(--secondary-background-color); }
.form { display: grid; gap: 12px; }
label { display: grid; gap: 6px; font-size: 13px; color: var(--secondary-text-color); }
section > label { margin: 12px 0 6px; }
.form-actions { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 4px; }
.form-actions .status { margin: 0; }
.subhead { margin-top: 6px; font-weight: 600; color: var(--primary-text-color); font-size: 14px; }
label.check { display: flex; gap: 10px; align-items: flex-start; }
label.check input { width: auto; margin-top: 3px; accent-color: var(--mk); }
label.check span { display: grid; gap: 4px; color: var(--primary-text-color); }
.assist { margin-top: 6px; font-size: 13px; }
.assist.ok { color: var(--success-color, #43a047); } .assist.bad { color: var(--secondary-text-color); }
.kv { display: flex; justify-content: space-between; font-size: 13px; gap: 8px; }
.kv span:last-child { text-align: right; word-break: break-all; }
@media (max-width: 600px) { main { padding: 10px; } .hero { grid-row: auto; } }
`;

if (!customElements.get("maika-direct-panel")) customElements.define("maika-direct-panel", MaikaDirectPanel);
