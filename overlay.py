"""
Floating overlay window for LocalWhisper.

Shows animated SVG lock+waveform icons via a WKWebView overlay
in the top-right corner (Siri position) during recording/processing.
"""

import logging

log = logging.getLogger("LocalWhisper")

_SIZE = 120
_PAD = 8

_OVERLAY_HTML = """<!DOCTYPE html>
<html>
<head>
<style>
  * { margin: 0; padding: 0; }
  html, body { background: transparent; overflow: hidden; }
  .container {
    width: 120px; height: 120px;
    display: flex; align-items: center; justify-content: center;
  }
  .icon-surface {
    width: 120px; height: 120px;
    display: flex; align-items: center; justify-content: center;
    background: transparent;
  }
  .state { display: none; }
  .state.active { display: block; }

  @keyframes rec-bar-1 { 0%,100%{height:15.3px;y:72.9px} 50%{height:20.7px;y:70.2px} }
  @keyframes rec-bar-2 { 0%,100%{height:25.8px;y:64.1px} 50%{height:34.8px;y:59.6px} }
  @keyframes rec-bar-3 { 0%,100%{height:20px;y:69px} 50%{height:27px;y:65.5px} }
  @keyframes rec-bar-4 { 0%,100%{height:29.3px;y:61.7px} 50%{height:39.6px;y:56.6px} }
  @keyframes rec-bar-5 { 0%,100%{height:11.7px;y:74.7px} 50%{height:15.8px;y:72.7px} }
  .rb1 { animation: rec-bar-1 .5s ease-in-out infinite; }
  .rb2 { animation: rec-bar-2 .6s .1s ease-in-out infinite; }
  .rb3 { animation: rec-bar-3 .55s .05s ease-in-out infinite; }
  .rb4 { animation: rec-bar-4 .65s .15s ease-in-out infinite; }
  .rb5 { animation: rec-bar-5 .5s .08s ease-in-out infinite; }
  @keyframes rec-glow { 0%,100%{opacity:.12} 50%{opacity:.28} }
  .rg { animation: rec-glow 1.4s ease-in-out infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .proc-arc { animation: spin 1.2s linear infinite; transform-origin: 60px 79px; }
</style>
</head>
<body>
<div class="container"><div class="icon-surface">

  <svg class="state" id="recording" viewBox="0 0 120 120" width="110" height="110">
    <defs>
      <linearGradient id="rg" x1=".3" y1="0" x2=".6" y2="1">
        <stop offset="0%" stop-color="rgba(45,43,85,0.85)"/>
        <stop offset="100%" stop-color="rgba(21,19,43,0.70)"/>
      </linearGradient>
      <filter id="rf"><feGaussianBlur stdDeviation="5"/></filter>
    </defs>
    <ellipse class="rg" cx="60" cy="80" rx="32" ry="18" fill="#FF453A" opacity=".2" filter="url(#rf)"/>
    <path d="M36.8 49.2H41.1V37.3A19 19 0 0178.9 37.3V49.2H83.2Q92.4 49.2 92.4 58.6V95Q92.4 104.4 83.2 104.4H36.8Q27.6 104.4 27.6 95V58.6Q27.6 49.2 36.8 49.2ZM50 49.2V37.3A11 11 0 0170 37.3V49.2Z" fill="url(#rg)" fill-rule="evenodd" stroke="rgba(140,130,255,.25)" stroke-width=".7"/>
    <rect class="rb1" x="35.2" y="72.9" width="6.6" height="15.3" rx="3.3" fill="#FF8A80" opacity=".55"/>
    <rect class="rb2" x="46.3" y="64.1" width="6.6" height="25.8" rx="3.3" fill="#FF453A" opacity=".92"/>
    <rect class="rb3" x="57.4" y="69" width="6.6" height="20" rx="3.3" fill="#FF8A80" opacity=".55"/>
    <rect class="rb4" x="68.5" y="61.7" width="6.6" height="29.3" rx="3.3" fill="#FF453A" opacity=".92"/>
    <rect class="rb5" x="79.6" y="74.7" width="6.6" height="11.7" rx="3.3" fill="#FF8A80" opacity=".55"/>
  </svg>

  <svg class="state" id="processing" viewBox="0 0 120 120" width="110" height="110">
    <defs>
      <linearGradient id="pg" x1=".3" y1="0" x2=".6" y2="1">
        <stop offset="0%" stop-color="rgba(45,43,85,0.85)"/>
        <stop offset="100%" stop-color="rgba(21,19,43,0.70)"/>
      </linearGradient>
      <filter id="pf"><feGaussianBlur stdDeviation="5"/></filter>
    </defs>
    <ellipse cx="60" cy="80" rx="32" ry="18" fill="#BF5AF2" opacity=".15" filter="url(#pf)"/>
    <path d="M36.8 49.2H41.1V37.3A19 19 0 0178.9 37.3V49.2H83.2Q92.4 49.2 92.4 58.6V95Q92.4 104.4 83.2 104.4H36.8Q27.6 104.4 27.6 95V58.6Q27.6 49.2 36.8 49.2ZM50 49.2V37.3A11 11 0 0170 37.3V49.2Z" fill="url(#pg)" fill-rule="evenodd" stroke="rgba(140,130,255,.25)" stroke-width=".7"/>
    <circle cx="60" cy="79" r="18" fill="none" stroke="rgba(255,255,255,.08)" stroke-width="2"/>
    <circle class="proc-arc" cx="60" cy="79" r="18" fill="none" stroke="#BF5AF2" stroke-width="2.5" stroke-dasharray="28 85" stroke-linecap="round" opacity=".85"/>
  </svg>

</div></div>
</body>
</html>"""

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

    def show_recording(self):
        """Show the overlay with red pulsing bars animation."""
        if not self._ready:
            return
        def _do():
            self._wv.evaluateJavaScript_completionHandler_(
                _JS_SET_STATE % "recording", None
            )
            self._win.setAlphaValue_(1.0)
            self._win.orderFrontRegardless()
        self._callAfter(_do)

    def show_processing(self):
        """Show the overlay with purple spinner animation."""
        if not self._ready:
            return
        def _do():
            self._wv.evaluateJavaScript_completionHandler_(
                _JS_SET_STATE % "processing", None
            )
            self._win.setAlphaValue_(1.0)
            self._win.orderFrontRegardless()
        self._callAfter(_do)

    def hide(self):
        """Hide the overlay."""
        if not self._ready:
            return
        self._callAfter(self._win.setAlphaValue_, 0.0)
