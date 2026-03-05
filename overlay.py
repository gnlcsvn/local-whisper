"""
Floating overlay window for LocalWhisper.

Shows animated SVG lock+waveform icons via a WKWebView overlay
in the top-right corner (Siri position) during recording/processing/translating.
"""

import logging

log = logging.getLogger("LocalWhisper")

_SIZE = 120
_PAD = 8

# Lock path shared by all states
_LOCK_PATH = (
    "M 36.8 44.2 L 41.1 44.2 L 41.1 32.3 A 19 19 0 0 1 78.9 32.3"
    " L 78.9 44.2 L 83.2 44.2 Q 92.4 44.2 92.4 53.6 L 92.4 90"
    " Q 92.4 99.4 83.2 99.4 L 36.8 99.4 Q 27.6 99.4 27.6 90"
    " L 27.6 53.6 Q 27.6 44.2 36.8 44.2 Z"
    " M 50 44.2 L 50 32.3 A 11 11 0 0 1 70 32.3 L 70 44.2 Z"
)

_OVERLAY_HTML = (
    '<!DOCTYPE html>\n<html>\n<head>\n<style>\n'
    '  * { margin: 0; padding: 0; }\n'
    '  html, body { background: transparent; overflow: hidden; }\n'
    '  .container {\n'
    '    width: 120px; height: 120px;\n'
    '    display: flex; align-items: center; justify-content: center;\n'
    '  }\n'
    '  .state { display: none; }\n'
    '  .state.active { display: block; }\n'
    '\n'
    '  /* Recording bar pulse */\n'
    '  @keyframes rb1 { 0%,100%{height:15.3px;y:67.9px} 50%{height:20.7px;y:65.2px} }\n'
    '  @keyframes rb2 { 0%,100%{height:25.8px;y:59.1px} 50%{height:34.8px;y:54.6px} }\n'
    '  @keyframes rb3 { 0%,100%{height:20px;y:64px} 50%{height:27px;y:60.5px} }\n'
    '  @keyframes rb4 { 0%,100%{height:29.3px;y:56.7px} 50%{height:39.6px;y:51.6px} }\n'
    '  @keyframes rb5 { 0%,100%{height:11.7px;y:69.7px} 50%{height:15.8px;y:67.7px} }\n'
    '  .rb1 { animation: rb1 .5s ease-in-out infinite; }\n'
    '  .rb2 { animation: rb2 .6s .1s ease-in-out infinite; }\n'
    '  .rb3 { animation: rb3 .55s .05s ease-in-out infinite; }\n'
    '  .rb4 { animation: rb4 .65s .15s ease-in-out infinite; }\n'
    '  .rb5 { animation: rb5 .5s .08s ease-in-out infinite; }\n'
    '\n'
    '  /* Processing spinner */\n'
    '  @keyframes spin { to { transform: rotate(360deg); } }\n'
    '  .proc-arc { animation: spin 1.2s linear infinite; transform-origin: 60px 74px; }\n'
    '\n'
    '  /* Translating dual arcs */\n'
    '  @keyframes spin-ccw { to { transform: rotate(-360deg); } }\n'
    '  .trans-cw { animation: spin 2s linear infinite; transform-origin: 60px 74px; }\n'
    '  .trans-ccw { animation: spin-ccw 2s linear infinite; transform-origin: 60px 74px; }\n'
    '  .trans-letter {\n'
    '    font-family: -apple-system, sans-serif;\n'
    '    font-weight: 600;\n'
    '    text-anchor: middle;\n'
    '    dominant-baseline: central;\n'
    '    transition: opacity 0.5s ease-in-out;\n'
    '  }\n'
    '</style>\n</head>\n<body>\n'
    '<div class="container">\n'
    '\n'
    '  <!-- RECORDING -->\n'
    '  <svg class="state" id="recording" viewBox="0 0 120 120" width="110" height="110">\n'
    '    <defs>\n'
    '      <linearGradient id="rgl" x1=".3" y1="0" x2=".6" y2="1">'
    '<stop offset="0%" stop-color="rgba(255,255,255,0.18)"/><stop offset="100%" stop-color="rgba(255,255,255,0.08)"/></linearGradient>\n'
    '      <filter id="rsh"><feDropShadow dx="0" dy="1.5" stdDeviation="2" flood-opacity=".3"/></filter>\n'
    '    </defs>\n'
    '    <g filter="url(#rsh)">\n'
    f'      <path d="{_LOCK_PATH}" fill="url(#rgl)" fill-rule="evenodd" stroke="rgba(255,255,255,0.15)" stroke-width=".5"/>\n'
    '    </g>\n'
    '    <rect class="rb1" x="35.2" y="67.9" width="6.6" height="15.3" rx="3.3" fill="#FF8A80" opacity=".55"/>\n'
    '    <rect class="rb2" x="46.3" y="59.1" width="6.6" height="25.8" rx="3.3" fill="#FF453A" opacity=".92"/>\n'
    '    <rect class="rb3" x="57.4" y="64" width="6.6" height="20" rx="3.3" fill="#FF8A80" opacity=".55"/>\n'
    '    <rect class="rb4" x="68.5" y="56.7" width="6.6" height="29.3" rx="3.3" fill="#FF453A" opacity=".92"/>\n'
    '    <rect class="rb5" x="79.6" y="69.7" width="6.6" height="11.7" rx="3.3" fill="#FF8A80" opacity=".55"/>\n'
    '  </svg>\n'
    '\n'
    '  <!-- PROCESSING -->\n'
    '  <svg class="state" id="processing" viewBox="0 0 120 120" width="110" height="110">\n'
    '    <defs>\n'
    '      <linearGradient id="pgl" x1=".3" y1="0" x2=".6" y2="1">'
    '<stop offset="0%" stop-color="rgba(255,255,255,0.18)"/><stop offset="100%" stop-color="rgba(255,255,255,0.08)"/></linearGradient>\n'
    '      <filter id="psh"><feDropShadow dx="0" dy="1.5" stdDeviation="2" flood-opacity=".3"/></filter>\n'
    '    </defs>\n'
    '    <g filter="url(#psh)">\n'
    f'      <path d="{_LOCK_PATH}" fill="url(#pgl)" fill-rule="evenodd" stroke="rgba(255,255,255,0.15)" stroke-width=".5"/>\n'
    '    </g>\n'
    '    <circle cx="60" cy="74" r="18" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="6.6"/>\n'
    '    <circle class="proc-arc" cx="60" cy="74" r="18" fill="none" stroke="#BF5AF2" stroke-width="6.6" stroke-dasharray="28 85" stroke-linecap="round" opacity=".85"/>\n'
    '  </svg>\n'
    '\n'
    '  <!-- TRANSLATING -->\n'
    '  <svg class="state" id="translating" viewBox="0 0 120 120" width="110" height="110">\n'
    '    <defs>\n'
    '      <linearGradient id="tgl" x1=".3" y1="0" x2=".6" y2="1">'
    '<stop offset="0%" stop-color="rgba(255,255,255,0.18)"/><stop offset="100%" stop-color="rgba(255,255,255,0.08)"/></linearGradient>\n'
    '      <filter id="tsh"><feDropShadow dx="0" dy="1.5" stdDeviation="2" flood-opacity=".3"/></filter>\n'
    '    </defs>\n'
    '    <g filter="url(#tsh)">\n'
    f'      <path d="{_LOCK_PATH}" fill="url(#tgl)" fill-rule="evenodd" stroke="rgba(255,255,255,0.15)" stroke-width=".5"/>\n'
    '    </g>\n'
    '    <circle cx="60" cy="74" r="18" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="6.6"/>\n'
    '    <circle class="trans-cw" cx="60" cy="74" r="18" fill="none" stroke="#5AC8FA" stroke-width="6.6" stroke-dasharray="22 91" stroke-linecap="round" opacity=".8"/>\n'
    '    <circle class="trans-ccw" cx="60" cy="74" r="18" fill="none" stroke="#6C63FF" stroke-width="6.6" stroke-dasharray="22 91" stroke-linecap="round" opacity=".7"/>\n'
    '    <text id="tl" class="trans-letter" x="60" y="75" font-size="16" fill="#EEEDF5" opacity=".35">\u0414</text>\n'
    '  </svg>\n'
    '\n'
    '</div>\n'
    '<script>\n'
    "var letters=['\\u0414','\\u6587','\\u3042','\\ud55c','\\u03A3','\\u00C4'];\n"
    'var li=0;\n'
    'setInterval(function(){\n'
    "  var el=document.getElementById('tl');\n"
    '  if(!el)return;\n'
    "  el.setAttribute('opacity','0');\n"
    '  setTimeout(function(){\n'
    '    li=(li+1)%letters.length;\n'
    '    el.textContent=letters[li];\n'
    "    el.setAttribute('opacity','0.35');\n"
    '  },500);\n'
    '},1800);\n'
    '</script>\n'
    '</body>\n</html>'
)

_JS_SET_STATE = """
document.querySelectorAll('.state').forEach(e => e.classList.remove('active'));
document.getElementById('%s').classList.add('active');
"""


class OverlayWindow:
    """Floating WKWebView overlay that shows animated SVG states.

    All framework imports are deferred to init() so that a failure
    to load WebKit doesn't prevent the app from starting.
    """

    def __init__(self, resource_path_fn=None):
        self._win = None
        self._wv = None
        self._ready = False

        try:
            from AppKit import (
                NSWindow,
                NSColor,
                NSScreen,
                NSWindowCollectionBehaviorCanJoinAllSpaces,
                NSWindowCollectionBehaviorFullScreenAuxiliary,
            )
            from Foundation import NSMakeRect
            from WebKit import WKWebView, WKWebViewConfiguration
            from PyObjCTools.AppHelper import callAfter

            self._callAfter = callAfter

            screen = NSScreen.mainScreen()
            if screen is None:
                log.warning("Overlay: NSScreen.mainScreen() returned None")
                return

            sf = screen.frame()
            vf = screen.visibleFrame()
            x = sf.size.width - _SIZE - _PAD
            y = vf.origin.y + vf.size.height - _SIZE

            self._win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(x, y, _SIZE, _SIZE),
                0,  # borderless
                2,  # NSBackingStoreBuffered
                False,
            )
            self._win.setOpaque_(False)
            self._win.setBackgroundColor_(NSColor.clearColor())
            self._win.setLevel_(25)
            self._win.setHasShadow_(False)
            self._win.setIgnoresMouseEvents_(True)
            self._win.setCollectionBehavior_(
                NSWindowCollectionBehaviorCanJoinAllSpaces
                | NSWindowCollectionBehaviorFullScreenAuxiliary
            )

            config = WKWebViewConfiguration.alloc().init()
            self._wv = WKWebView.alloc().initWithFrame_configuration_(
                NSMakeRect(0, 0, _SIZE, _SIZE), config
            )
            self._wv.setValue_forKey_(False, "drawsBackground")
            self._wv.loadHTMLString_baseURL_(_OVERLAY_HTML, None)
            self._win.setContentView_(self._wv)

            self._win.setAlphaValue_(0.0)
            self._ready = True
            log.info("Overlay: initialized successfully")

        except Exception:
            log.exception("Overlay: failed to initialize, overlay disabled")

    def _show_state(self, state_id):
        """Show the overlay with the given state SVG."""
        if not self._ready:
            return
        def _do():
            self._wv.evaluateJavaScript_completionHandler_(
                _JS_SET_STATE % state_id, None
            )
            self._win.setAlphaValue_(1.0)
            self._win.orderFrontRegardless()
        self._callAfter(_do)

    def show_recording(self):
        """Show the overlay with red pulsing bars animation."""
        self._show_state("recording")

    def show_processing(self):
        """Show the overlay with purple spinner animation."""
        self._show_state("processing")

    def show_translating(self):
        """Show the overlay with teal dual-arc translation animation."""
        self._show_state("translating")

    def hide(self):
        """Hide the overlay."""
        if not self._ready:
            return
        self._callAfter(self._win.setAlphaValue_, 0.0)
