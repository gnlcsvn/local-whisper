"""
Settings window for LocalWhisper using WKWebView + HTML/CSS.

Same pattern as overlay.py: NSWindow hosts a WKWebView with embedded HTML.
Python<->JS bridge via WKScriptMessageHandler.
"""

import json
import logging

log = logging.getLogger("LocalWhisper")

from config import (
    MODEL_MAP, MODEL_SIZES_MB, SHORTCUT_PRESETS,
    LANGUAGES as LANG_CODES, RECORDING_DURATIONS,
    LLM_SIZE_MB,
)
from model_manager import format_size

_MODEL_KEYS = list(MODEL_MAP.keys())

_MODEL_DESCRIPTIONS = {
    "tiny": "Tiny -- fastest, least accurate",
    "small": "Small -- fast, good accuracy",
    "turbo": "Turbo -- balanced (recommended)",
    "medium": "Medium -- slower, better accuracy",
    "large": "Large -- slowest, best accuracy",
}

def _build_settings_html(config, model_cache_status, llm_cached, devices):
    """Build the full HTML string for the settings window."""

    # --- Model radios ---
    model_rows = []
    for key in _MODEL_KEYS:
        desc = _MODEL_DESCRIPTIONS.get(key, key)
        size = format_size(MODEL_SIZES_MB.get(key, 0))
        cached = model_cache_status.get(key) is True
        is_active = key == config.model_name
        checked = "checked" if is_active else ""
        disabled = "" if cached else "disabled"
        row_class = "" if cached else "model-row--disabled"
        if cached:
            delete_html = (
                "" if is_active
                else f' <button class="del-btn" data-action="delete" data-key="{key}">Delete</button>'
            )
            status_html = f'<span class="status-downloaded">Downloaded</span>{delete_html}'
        else:
            status_html = f'<button class="dl-btn" data-action="download" data-key="{key}">Download</button>'
        model_rows.append(f"""
            <div class="model-row {row_class}" data-key="{key}">
              <label class="model-main">
                <input type="radio" name="model" value="{key}" {checked} {disabled}
                       onchange="onModelSelect(this.value)">
                <span class="model-desc">{desc}</span>
                <span class="size-badge">{size}</span>
              </label>
              <div class="model-status" id="status-{key}">
                {status_html}
              </div>
            </div>""")

    models_html = "\n".join(model_rows)

    # --- LLM status ---
    llm_size = format_size(LLM_SIZE_MB)
    if llm_cached:
        llm_status_html = (
            '<span class="status-downloaded">Downloaded</span>'
            ' <button class="del-btn" data-action="delete-llm">Delete</button>'
        )
    else:
        llm_status_html = '<button class="dl-btn" data-action="download-llm">Download</button>'

    # --- Language options ---
    input_lang_options = []
    for code, name in LANG_CODES.items():
        sel = "selected" if code == config.language else ""
        input_lang_options.append(f'<option value="{code}" {sel}>{name}</option>')

    translate_checked = "checked" if config.translate_to_english else ""
    cleanup_checked = "checked" if config.cleanup else ""

    # --- Microphone options ---
    mic_options = ['<option value="default" selected>System Default</option>']
    for dev in (devices or []):
        dev_name = dev["name"].replace('"', '&quot;').replace("'", "&#39;")
        dev_idx = dev["index"]
        sel = "selected" if dev["name"] == config.input_device else ""
        if sel:
            # Deselect default if a specific device is selected
            mic_options[0] = '<option value="default">System Default</option>'
        mic_options.append(
            f'<option value="{dev_idx}" data-name="{dev_name}" {sel}>{dev["name"]}</option>'
        )

    # --- Recording duration options ---
    rec_options = []
    for secs, label in RECORDING_DURATIONS.items():
        sel = "selected" if secs == config.max_recording_seconds else ""
        rec_options.append(f'<option value="{secs}" {sel}>{label}</option>')

    # --- Shortcut options ---
    shortcut_options = []
    for pid, info in SHORTCUT_PRESETS.items():
        sel = "selected" if pid == config.shortcut else ""
        shortcut_options.append(f'<option value="{pid}" {sel}>{info["label"]}</option>')

    # Chevron SVG for custom selects (URL-encoded)
    chevron_svg = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='%238A87A8'%3E%3Cpath d='M2 4l4 4 4-4'/%3E%3C/svg%3E"

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  :root {{
    --bg-deep: #08060F;
    --bg-card: #0F0C1A;
    --bg-elevated: #161226;
    --indigo-dark: #15132B;
    --indigo-mid: #2D2B55;
    --indigo-bright: #6C63FF;
    --indigo-glow: #8B83FF;
    --text-primary: #EEEDF5;
    --text-secondary: #8A87A8;
    --text-muted: #5C5880;
    --accent-teal: #5AC8FA;
    --surface-glass: rgba(255,255,255,0.04);
    --border-subtle: rgba(255,255,255,0.06);
    --border-glass: rgba(140,130,255,0.12);
    --green: #32D74B;
  }}

  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  html, body {{
    background: var(--bg-deep);
    color: var(--text-primary);
    font: 13px/1.5 -apple-system, BlinkMacSystemFont, sans-serif;
    -webkit-user-select: none;
    user-select: none;
    overflow-y: auto;
    overflow-x: hidden;
  }}

  body {{ padding: 20px; }}

  .section-header {{
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
    padding-left: 4px;
  }}

  .section-box {{
    background: var(--surface-glass);
    border: 1px solid var(--border-glass);
    border-radius: 12px;
    margin-bottom: 20px;
    overflow: hidden;
  }}

  .row {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 16px;
    min-height: 44px;
  }}

  .row + .row {{
    border-top: 1px solid var(--border-subtle);
  }}

  .row-label {{
    font-size: 13px;
    color: var(--text-primary);
  }}

  /* Select styling */
  select {{
    appearance: none;
    -webkit-appearance: none;
    background: var(--bg-elevated);
    color: var(--text-primary);
    border: 1px solid var(--border-glass);
    border-radius: 8px;
    padding: 6px 32px 6px 12px;
    font: 13px -apple-system, BlinkMacSystemFont, sans-serif;
    background-image: url("{chevron_svg}");
    background-repeat: no-repeat;
    background-position: right 10px center;
    cursor: pointer;
    outline: none;
    min-width: 160px;
  }}

  select:focus {{
    border-color: var(--indigo-bright);
  }}

  select:disabled, select.dimmed {{
    opacity: 0.35;
    cursor: default;
  }}

  /* Model section */
  .model-row {{
    display: block;
    padding: 10px 16px 8px;
    cursor: pointer;
  }}

  .model-row + .model-row {{
    border-top: 1px solid var(--border-subtle);
  }}

  .model-main {{
    display: flex;
    align-items: center;
    gap: 8px;
  }}

  .model-main input[type="radio"] {{
    accent-color: var(--indigo-bright);
    margin: 0;
    width: 16px;
    height: 16px;
    cursor: pointer;
  }}

  .model-desc {{
    flex: 1;
    font-size: 13px;
    color: var(--text-primary);
  }}

  .size-badge {{
    font-size: 11px;
    color: var(--text-muted);
    background: var(--bg-elevated);
    padding: 2px 8px;
    border-radius: 6px;
    white-space: nowrap;
  }}

  .model-status {{
    padding: 4px 0 2px 24px;
    min-height: 22px;
  }}

  .status-downloaded {{
    font-size: 11px;
    color: var(--green);
    font-weight: 500;
  }}

  .dl-btn {{
    background: var(--indigo-bright);
    color: white;
    border: none;
    border-radius: 6px;
    padding: 4px 14px;
    font: 12px -apple-system, BlinkMacSystemFont, sans-serif;
    cursor: pointer;
  }}

  .dl-btn:hover {{
    background: var(--indigo-glow);
  }}

  .dl-btn:disabled {{
    opacity: 0.5;
    cursor: default;
  }}

  .del-btn {{
    background: transparent;
    color: var(--text-muted);
    border: 1px solid var(--border-glass);
    border-radius: 6px;
    padding: 2px 10px;
    font: 11px -apple-system, BlinkMacSystemFont, sans-serif;
    cursor: pointer;
    margin-left: 8px;
  }}

  .del-btn:hover {{
    color: #FF453A;
    border-color: #FF453A;
  }}

  .del-btn:disabled {{
    opacity: 0.5;
    cursor: default;
  }}

  /* Disabled model row (not downloaded) */
  .model-row--disabled .model-main {{
    opacity: 0.35;
  }}

  .model-row--disabled .model-main input {{
    pointer-events: none;
  }}

  .status-error {{
    font-size: 11px;
    color: #FF453A;
    font-weight: 500;
  }}

  .storage-info {{
    font-size: 11px;
    color: var(--text-muted);
    padding: 6px 4px 0;
    margin-bottom: 16px;
  }}

  .llm-detail {{
    font-size: 11px;
    color: var(--text-muted);
    margin-top: 2px;
  }}

  .llm-status {{
    display: flex;
    align-items: center;
    flex-shrink: 0;
  }}

  /* Spinner for downloading */
  .spinner {{
    display: inline-block;
    width: 14px;
    height: 14px;
    border: 2px solid var(--border-glass);
    border-top-color: var(--indigo-bright);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    vertical-align: middle;
    margin-right: 6px;
  }}

  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}

  .downloading-text {{
    font-size: 11px;
    color: var(--text-secondary);
    vertical-align: middle;
  }}

  /* Toggle switch */
  .toggle {{
    position: relative;
    width: 44px;
    height: 24px;
    flex-shrink: 0;
  }}

  .toggle input {{
    opacity: 0;
    width: 0;
    height: 0;
  }}

  .toggle .slider {{
    position: absolute;
    inset: 0;
    background: var(--text-muted);
    border-radius: 12px;
    transition: .3s;
    cursor: pointer;
  }}

  .toggle .slider::before {{
    content: '';
    position: absolute;
    height: 18px;
    width: 18px;
    left: 3px;
    bottom: 3px;
    background: white;
    border-radius: 50%;
    transition: .3s;
  }}

  .toggle input:checked + .slider {{
    background: var(--indigo-bright);
  }}

  .toggle input:checked + .slider::before {{
    transform: translateX(20px);
  }}

  /* Scrollbar */
  ::-webkit-scrollbar {{
    width: 6px;
  }}
  ::-webkit-scrollbar-track {{
    background: transparent;
  }}
  ::-webkit-scrollbar-thumb {{
    background: var(--text-muted);
    border-radius: 3px;
  }}
</style>
</head>
<body>

  <!-- Model -->
  <div class="section-header">Whisper Model</div>
  <div class="section-box" id="model-section">
    {models_html}
  </div>
  <div class="storage-info" id="storage-info">Calculating storage&hellip;</div>

  <!-- Cleanup LLM -->
  <div class="section-header">Cleanup Model</div>
  <div class="section-box">
    <div class="row">
      <div>
        <span class="row-label">Llama 3.2 3B Instruct</span>
        <div class="llm-detail">{llm_size} &middot; used for &ldquo;Clean up text&rdquo;</div>
      </div>
      <div class="llm-status" id="llm-status">
        {llm_status_html}
      </div>
    </div>
  </div>

  <!-- Language -->
  <div class="section-header">Language</div>
  <div class="section-box">
    <div class="row">
      <span class="row-label">Input Language</span>
      <select id="input-lang" onchange="onInputLang(this.value)">
        {''.join(input_lang_options)}
      </select>
    </div>
    <div class="row">
      <span class="row-label">Translate to English</span>
      <label class="toggle">
        <input type="checkbox" id="translate-toggle" {translate_checked}
               onchange="onTranslateToEnglish(this.checked)">
        <span class="slider"></span>
      </label>
    </div>
  </div>

  <!-- Text Processing -->
  <div class="section-header">Text Processing</div>
  <div class="section-box">
    <div class="row">
      <span class="row-label">Clean up text</span>
      <label class="toggle">
        <input type="checkbox" id="cleanup-toggle" {cleanup_checked}
               onchange="onCleanup(this.checked)">
        <span class="slider"></span>
      </label>
    </div>
  </div>

  <!-- Audio -->
  <div class="section-header">Audio</div>
  <div class="section-box">
    <div class="row">
      <span class="row-label">Microphone</span>
      <select id="mic-select" onchange="onMicSelect(this)">
        {''.join(mic_options)}
      </select>
    </div>
    <div class="row">
      <span class="row-label">Max Recording</span>
      <select id="max-recording" onchange="onMaxRecording(this.value)">
        {''.join(rec_options)}
      </select>
    </div>
  </div>

  <!-- Shortcut -->
  <div class="section-header">Shortcut</div>
  <div class="section-box">
    <div class="row">
      <span class="row-label">Shortcut</span>
      <select id="shortcut-select" onchange="onShortcut(this.value)">
        {''.join(shortcut_options)}
      </select>
    </div>
  </div>

<script>
  var _msg = window.webkit.messageHandlers.settings;

  function onModelSelect(key) {{
    _msg.postMessage({{action: "model_select", value: key}});
  }}

  /* Event delegation for all buttons — more reliable in WKWebView than inline onclick */
  document.addEventListener('click', function(e) {{
    var btn = e.target.closest('.dl-btn, .del-btn');
    if (!btn || btn.disabled) return;
    e.preventDefault();
    e.stopPropagation();
    var action = btn.getAttribute('data-action');
    var key = btn.getAttribute('data-key');
    if (action === 'download' && key) {{
      _msg.postMessage({{action: "model_download", value: key}});
    }} else if (action === 'delete' && key) {{
      _msg.postMessage({{action: "model_delete", value: key}});
    }} else if (action === 'download-llm') {{
      _msg.postMessage({{action: "llm_download"}});
    }} else if (action === 'delete-llm') {{
      _msg.postMessage({{action: "llm_delete"}});
    }}
  }});

  function onInputLang(code) {{
    _msg.postMessage({{action: "input_lang", value: code}});
  }}

  function onTranslateToEnglish(enabled) {{
    _msg.postMessage({{action: "translate_to_english", value: enabled}});
  }}

  function onCleanup(enabled) {{
    _msg.postMessage({{action: "cleanup_toggle", value: enabled}});
  }}

  function onMaxRecording(secs) {{
    _msg.postMessage({{action: "max_recording", value: parseInt(secs)}});
  }}

  function onMicSelect(sel) {{
    var opt = sel.options[sel.selectedIndex];
    if (opt.value === 'default') {{
      _msg.postMessage({{action: "mic_select", name: null, index: null}});
    }} else {{
      _msg.postMessage({{
        action: "mic_select",
        name: opt.getAttribute('data-name'),
        index: parseInt(opt.value)
      }});
    }}
  }}

  function onShortcut(presetId) {{
    _msg.postMessage({{action: "shortcut", value: presetId}});
  }}

  /* Functions called from Python via evaluateJavaScript */

  function updateModelStatus(key, isCached, isDownloading, isActive, errorMessage) {{
    var el = document.getElementById('status-' + key);
    var row = el ? el.closest('.model-row') : null;
    if (!el) return;

    if (isDownloading) {{
      el.innerHTML = '<span class="spinner"></span><span class="downloading-text">Downloading\u2026</span>';
    }} else if (errorMessage) {{
      el.innerHTML = '<span class="status-error">' + errorMessage + '</span>' +
        ' <button class="dl-btn" data-action="download" data-key="' + key + '">Retry</button>';
      if (row) {{
        row.classList.add('model-row--disabled');
        var r = row.querySelector('input[type="radio"]');
        if (r) {{ r.disabled = true; r.checked = false; }}
      }}
    }} else if (isCached) {{
      var html = '<span class="status-downloaded">Downloaded</span>';
      if (!isActive) {{
        html += ' <button class="del-btn" data-action="delete" data-key="' + key + '">Delete</button>';
      }}
      el.innerHTML = html;
      if (row) {{
        row.classList.remove('model-row--disabled');
        var r = row.querySelector('input[type="radio"]');
        if (r) r.disabled = false;
      }}
    }} else {{
      el.innerHTML = '<button class="dl-btn" data-action="download" data-key="' + key + '">Download</button>';
      if (row) {{
        row.classList.add('model-row--disabled');
        var r = row.querySelector('input[type="radio"]');
        if (r) {{ r.disabled = true; r.checked = false; }}
      }}
    }}
  }}

  function updateLLMStatus(isCached, isDownloading, errorMessage) {{
    var el = document.getElementById('llm-status');
    if (!el) return;
    if (isDownloading) {{
      el.innerHTML = '<span class="spinner"></span><span class="downloading-text">Downloading...</span>';
    }} else if (errorMessage) {{
      el.innerHTML = '<span class="status-error">' + errorMessage + '</span>' +
        ' <button class="dl-btn" data-action="download-llm">Retry</button>';
    }} else if (isCached) {{
      el.innerHTML = '<span class="status-downloaded">Downloaded</span>' +
        ' <button class="del-btn" data-action="delete-llm">Delete</button>';
    }} else {{
      el.innerHTML = '<button class="dl-btn" data-action="download-llm">Download</button>';
    }}
  }}

  function updateStorageInfo(text) {{
    var el = document.getElementById('storage-info');
    if (el) el.textContent = text;
  }}

  function selectModel(key) {{
    var radios = document.querySelectorAll('input[name="model"]');
    radios.forEach(function(r) {{ r.checked = (r.value === key); }});
  }}

  function revertModelSelection(key) {{
    selectModel(key);
  }}

  function refreshDevices(devicesJson) {{
    var devices = JSON.parse(devicesJson);
    var sel = document.getElementById('mic-select');
    var current = sel.value;
    sel.innerHTML = '<option value="default">System Default</option>';
    devices.forEach(function(d) {{
      var opt = document.createElement('option');
      opt.value = d.index;
      opt.setAttribute('data-name', d.name);
      opt.textContent = d.name;
      sel.appendChild(opt);
    }});
    // Try to re-select the previously selected device
    var found = false;
    for (var i = 0; i < sel.options.length; i++) {{
      if (sel.options[i].value === current) {{
        sel.selectedIndex = i;
        found = true;
        break;
      }}
    }}
    if (!found) sel.selectedIndex = 0;
  }}
</script>
</body>
</html>"""


class _MessageHandler:
    """Placeholder - actual ObjC class created at import time below."""
    pass


# Deferred WebKit/ObjC imports and class creation
_WK_READY = False
_NSObject = None
_WKWebView = None
_WKWebViewConfiguration = None
_NSWindow = None
_NSColor = None
_NSScreen = None
_NSMakeRect = None
_callAfter = None
_MessageHandlerClass = None


def _ensure_webkit():
    """Lazily import WebKit and AppKit classes. Returns True if successful."""
    global _WK_READY, _NSObject, _WKWebView, _WKWebViewConfiguration
    global _NSWindow, _NSColor, _NSScreen, _NSMakeRect, _callAfter
    global _MessageHandlerClass

    if _WK_READY:
        return True

    try:
        from AppKit import (
            NSWindow as _Win,
            NSColor as _Col,
            NSScreen as _Scr,
            NSWindowStyleMaskTitled,
            NSWindowStyleMaskClosable,
        )
        from Foundation import NSMakeRect as _Rect, NSObject as _Obj
        from WebKit import WKWebView as _WV, WKWebViewConfiguration as _WVC
        from PyObjCTools.AppHelper import callAfter as _ca
        import objc

        _NSObject = _Obj
        _WKWebView = _WV
        _WKWebViewConfiguration = _WVC
        _NSWindow = _Win
        _NSColor = _Col
        _NSScreen = _Scr
        _NSMakeRect = _Rect
        _callAfter = _ca

        # Create ObjC message handler class
        class _MH(_Obj):
            _sw = objc.ivar()

            def userContentController_didReceiveScriptMessage_(self, controller, message):
                body = message.body()
                sw = self._sw
                if sw is None:
                    return
                try:
                    sw._handle_message(body)
                except Exception:
                    log.exception("Settings message handler error")

        _MessageHandlerClass = _MH
        _WK_READY = True
        return True

    except Exception:
        log.exception("Settings window: failed to import WebKit/AppKit")
        return False


# Keep strong refs to prevent garbage collection
_prevent_gc = []


class SettingsWindow:
    def __init__(self, app):
        self._app = app
        self._win = None
        self._wv = None
        self._handler = None
        self._built = False

    def _build(self):
        if self._built:
            return
        if not _ensure_webkit():
            return

        from AppKit import NSWindowStyleMaskTitled, NSWindowStyleMaskClosable

        screen = _NSScreen.mainScreen()
        sx = int((screen.frame().size.width - 520) / 2) if screen else 200
        sy = int((screen.frame().size.height - 640) / 2) if screen else 200

        mask = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
        self._win = _NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            _NSMakeRect(sx, sy, 520, 640), mask, 2, False,
        )
        self._win.setTitle_("Settings")
        self._win.setReleasedWhenClosed_(False)

        # Hide miniaturize + zoom buttons
        for i in (1, 2):
            b = self._win.standardWindowButton_(i)
            if b:
                b.setHidden_(True)

        # Set window background to match HTML
        self._win.setBackgroundColor_(
            _NSColor.colorWithRed_green_blue_alpha_(
                0x08 / 255.0, 0x06 / 255.0, 0x0F / 255.0, 1.0
            )
        )

        # WKWebView with message handler
        config = _WKWebViewConfiguration.alloc().init()
        self._handler = _MessageHandlerClass.alloc().init()
        self._handler._sw = self
        _prevent_gc.append(self._handler)
        config.userContentController().addScriptMessageHandler_name_(
            self._handler, "settings"
        )

        self._wv = _WKWebView.alloc().initWithFrame_configuration_(
            _NSMakeRect(0, 0, 520, 640), config
        )
        self._wv.setValue_forKey_(False, "drawsBackground")

        html = _build_settings_html(
            self._app._config,
            self._app._model_cache_status,
            bool(self._app._llm_cache_status),
            self._app._last_input_devices,
        )
        self._wv.loadHTMLString_baseURL_(html, None)
        self._win.setContentView_(self._wv)
        self._built = True

    def _handle_message(self, body):
        """Route JS messages to app callbacks."""
        action = body.get("action")
        if action is None:
            return

        app = self._app

        if action == "model_select":
            key = body.get("value")
            cached = app._model_cache_status.get(key)
            if cached is not True:
                # Revert selection in JS
                self._eval_js(f"revertModelSelection('{app._config.model_name}')")
                return
            app.on_settings_model_select(key)

        elif action == "model_download":
            key = body.get("value")
            self.update_model_status(key, is_cached=False, is_downloading=True)
            app.on_settings_download_model(key)

        elif action == "model_delete":
            key = body.get("value")
            self._eval_js(
                f"document.getElementById('status-{key}').innerHTML = "
                f"'<span class=\"downloading-text\">Deleting\u2026</span>'"
            )
            app.on_settings_delete_model(key)

        elif action == "llm_download":
            self.update_llm_status(is_cached=False, is_downloading=True)
            app.on_settings_download_llm()

        elif action == "llm_delete":
            self._eval_js(
                "document.getElementById('llm-status').innerHTML = "
                "'<span class=\"downloading-text\">Deleting\u2026</span>'"
            )
            app.on_settings_delete_llm()

        elif action == "input_lang":
            app.on_settings_input_lang(body.get("value"))

        elif action == "translate_to_english":
            app.on_settings_translate_to_english(bool(body.get("value")))

        elif action == "cleanup_toggle":
            app.on_settings_cleanup_toggle(bool(body.get("value")))

        elif action == "max_recording":
            app.on_settings_max_recording(int(body.get("value")))

        elif action == "mic_select":
            name = body.get("name")
            index = body.get("index")
            # Convert from JS null to Python None
            if name is not None:
                name = str(name)
            if index is not None:
                index = int(index)
            app.on_settings_mic_select(name, index)

        elif action == "shortcut":
            app.on_settings_shortcut(body.get("value"))

    def _eval_js(self, js):
        """Evaluate JavaScript in the WKWebView on the main thread."""
        if not self._built or self._wv is None:
            return

        def _do():
            self._wv.evaluateJavaScript_completionHandler_(js, None)

        _callAfter(_do)

    # ── Public API ────────────────────────────────────────────

    def show(self):
        try:
            self._build()
            if self._win is None:
                return
            self._win.makeKeyAndOrderFront_(None)
            from AppKit import NSApp
            NSApp.activateIgnoringOtherApps_(True)
            # Refresh model/LLM status and storage info
            self._app._check_model_cache_status()
        except Exception:
            log.exception("Settings window: failed to show")

    @property
    def is_visible(self) -> bool:
        if self._win is None:
            return False
        return self._win.isVisible()

    def update_model_status(self, model_key, is_cached, is_downloading=False,
                            is_active=False, error_message=None):
        error_js = f"'{error_message}'" if error_message else "null"
        js = (
            f"updateModelStatus('{model_key}', "
            f"{str(is_cached).lower()}, "
            f"{str(is_downloading).lower()}, "
            f"{str(is_active).lower()}, "
            f"{error_js})"
        )
        self._eval_js(js)

    def update_llm_status(self, is_cached, is_downloading=False, error_message=None):
        error_js = f"'{error_message}'" if error_message else "null"
        js = (
            f"updateLLMStatus("
            f"{str(is_cached).lower()}, "
            f"{str(is_downloading).lower()}, "
            f"{error_js})"
        )
        self._eval_js(js)

    def update_storage_info(self, text):
        escaped = text.replace("'", "\\'")
        self._eval_js(f"updateStorageInfo('{escaped}')")

    def update_model_selection(self, model_key):
        self._eval_js(f"selectModel('{model_key}')")

    def refresh_devices(self, devices):
        devices_json = json.dumps(devices)
        # Escape single quotes for JS string
        escaped = devices_json.replace("\\", "\\\\").replace("'", "\\'")
        self._eval_js(f"refreshDevices('{escaped}')")
