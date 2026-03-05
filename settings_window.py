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
    LANGUAGES as LANG_CODES, TEXT_STYLES, RECORDING_DURATIONS,
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

# Languages without "auto" for the output dropdown
_OUTPUT_LANGUAGES = {code: name for code, name in LANG_CODES.items() if code != "auto"}


def _build_settings_html(config, model_cache_status, devices):
    """Build the full HTML string for the settings window."""

    # --- Model radios ---
    model_rows = []
    for key in _MODEL_KEYS:
        desc = _MODEL_DESCRIPTIONS.get(key, key)
        size = format_size(MODEL_SIZES_MB.get(key, 0))
        cached = model_cache_status.get(key) is True
        checked = "checked" if key == config.model_name else ""
        downloaded_class = "downloaded" if cached else ""
        status_html = (
            '<span class="status-downloaded">Downloaded</span>'
            if cached
            else f'<button class="dl-btn" onclick="onDownload(\'{key}\')">Download</button>'
        )
        model_rows.append(f"""
            <label class="model-row" data-key="{key}">
              <div class="model-main">
                <input type="radio" name="model" value="{key}" {checked}
                       onchange="onModelSelect(this.value)">
                <span class="model-desc">{desc}</span>
                <span class="size-badge">{size}</span>
              </div>
              <div class="model-status {downloaded_class}" id="status-{key}">
                {status_html}
              </div>
            </label>""")

    models_html = "\n".join(model_rows)

    # --- Language options ---
    input_lang_options = []
    for code, name in LANG_CODES.items():
        sel = "selected" if code == config.language else ""
        input_lang_options.append(f'<option value="{code}" {sel}>{name}</option>')

    output_lang_options = []
    for code, name in _OUTPUT_LANGUAGES.items():
        sel = "selected" if code == config.output_language else ""
        output_lang_options.append(f'<option value="{code}" {sel}>{name}</option>')

    translate_checked = "checked" if config.translate else ""
    output_disabled = "" if config.translate else "disabled"
    output_dimmed = "" if config.translate else "dimmed"

    # --- Text style options ---
    style_options = []
    for sid, label in TEXT_STYLES.items():
        sel = "selected" if sid == config.text_style else ""
        style_options.append(f'<option value="{sid}" {sel}>{label}</option>')

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
  <div class="section-header">Model</div>
  <div class="section-box" id="model-section">
    {models_html}
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
      <span class="row-label">Translate</span>
      <label class="toggle">
        <input type="checkbox" id="translate-toggle" {translate_checked}
               onchange="onTranslateToggle(this.checked)">
        <span class="slider"></span>
      </label>
    </div>
    <div class="row">
      <span class="row-label">Output Language</span>
      <select id="output-lang" class="{output_dimmed}" {output_disabled}
              onchange="onOutputLang(this.value)">
        {''.join(output_lang_options)}
      </select>
    </div>
  </div>

  <!-- Text Processing -->
  <div class="section-header">Text Processing</div>
  <div class="section-box">
    <div class="row">
      <span class="row-label">Style</span>
      <select id="text-style" onchange="onTextStyle(this.value)">
        {''.join(style_options)}
      </select>
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

  function onDownload(key) {{
    _msg.postMessage({{action: "model_download", value: key}});
  }}

  function onInputLang(code) {{
    _msg.postMessage({{action: "input_lang", value: code}});
  }}

  function onOutputLang(code) {{
    _msg.postMessage({{action: "output_lang", value: code}});
  }}

  function onTranslateToggle(enabled) {{
    var sel = document.getElementById('output-lang');
    sel.disabled = !enabled;
    sel.classList.toggle('dimmed', !enabled);
    _msg.postMessage({{action: "translate_toggle", value: enabled}});
  }}

  function onTextStyle(styleId) {{
    _msg.postMessage({{action: "text_style", value: styleId}});
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

  function updateModelStatus(key, isCached, isDownloading) {{
    var el = document.getElementById('status-' + key);
    if (!el) return;
    if (isDownloading) {{
      el.className = 'model-status';
      el.innerHTML = '<span class="spinner"></span><span class="downloading-text">Downloading...</span>';
      document.querySelectorAll('.dl-btn').forEach(function(b) {{ b.disabled = true; }});
    }} else if (isCached) {{
      el.className = 'model-status downloaded';
      el.innerHTML = '<span class="status-downloaded">Downloaded</span>';
      document.querySelectorAll('.dl-btn').forEach(function(b) {{ b.disabled = false; }});
    }} else {{
      el.className = 'model-status';
      var btn = document.createElement('button');
      btn.className = 'dl-btn';
      btn.textContent = 'Download';
      btn.onclick = function() {{ onDownload(key); }};
      el.innerHTML = '';
      el.appendChild(btn);
      document.querySelectorAll('.dl-btn').forEach(function(b) {{ b.disabled = false; }});
    }}
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

        elif action == "input_lang":
            app.on_settings_input_lang(body.get("value"))

        elif action == "output_lang":
            app.on_settings_output_lang(body.get("value"))

        elif action == "translate_toggle":
            app.on_settings_translate_toggle(bool(body.get("value")))

        elif action == "text_style":
            app.on_settings_text_style(body.get("value"))

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
        except Exception:
            log.exception("Settings window: failed to show")

    @property
    def is_visible(self) -> bool:
        if self._win is None:
            return False
        return self._win.isVisible()

    def update_model_status(self, model_key, is_cached, is_downloading=False):
        js = (
            f"updateModelStatus('{model_key}', "
            f"{str(is_cached).lower()}, "
            f"{str(is_downloading).lower()})"
        )
        self._eval_js(js)

    def update_model_selection(self, model_key):
        self._eval_js(f"selectModel('{model_key}')")

    def refresh_devices(self, devices):
        devices_json = json.dumps(devices)
        # Escape single quotes for JS string
        escaped = devices_json.replace("\\", "\\\\").replace("'", "\\'")
        self._eval_js(f"refreshDevices('{escaped}')")
