/* A minimal stand-in for the browser, used only to smoke-test generated games in QuickJS.
 * It records drawing calls and lets the checker press keys and advance frames.
 * Nothing here can reach the network or the file system. */
var __aven = { draws: 0, logs: [], raf: [], listeners: {}, timers: [] };
var globalThis_ = globalThis;
var window = globalThis;
var self = globalThis;

function __noop() {}
function __addListener(target) {
  return function (type, fn) { (__aven.listeners[target + ":" + type] = __aven.listeners[target + ":" + type] || []).push(fn); };
}
function __context() {
  var ctx = {
    canvas: null, fillStyle: "#000", strokeStyle: "#000", lineWidth: 1, font: "10px sans-serif",
    textAlign: "left", textBaseline: "top", globalAlpha: 1, globalCompositeOperation: "source-over",
    shadowBlur: 0, shadowColor: "transparent", lineCap: "butt", lineJoin: "miter", imageSmoothingEnabled: true,
    measureText: function (text) { return { width: String(text).length * 8 }; },
    createLinearGradient: function () { return { addColorStop: __noop }; },
    createRadialGradient: function () { return { addColorStop: __noop }; },
    createPattern: function () { return {}; },
    getImageData: function (x, y, w, h) { return { data: new Uint8ClampedArray(Math.max(0, w * h * 4)), width: w, height: h }; },
    createImageData: function (w, h) { return { data: new Uint8ClampedArray(Math.max(0, w * h * 4)), width: w, height: h }; },
    isPointInPath: function () { return false; }
  };
  ["fillRect", "strokeRect", "fillText", "strokeText", "drawImage", "fill", "stroke", "putImageData"].forEach(function (name) {
    ctx[name] = function () { __aven.draws += 1; };
  });
  ["clearRect", "beginPath", "closePath", "moveTo", "lineTo", "arc", "arcTo", "rect", "ellipse", "quadraticCurveTo",
   "bezierCurveTo", "save", "restore", "translate", "scale", "rotate", "setTransform", "resetTransform", "transform",
   "clip", "setLineDash", "roundRect"].forEach(function (name) { ctx[name] = __noop; });
  return ctx;
}
function __element(tag) {
  var el = {
    tagName: String(tag).toUpperCase(), width: 300, height: 150, style: {}, children: [], textContent: "", innerHTML: "",
    addEventListener: __addListener("element"), removeEventListener: __noop,
    appendChild: function (child) { el.children.push(child); return child; },
    removeChild: __noop, setAttribute: __noop, focus: __noop,
    getBoundingClientRect: function () { return { left: 0, top: 0, width: el.width, height: el.height }; },
    classList: { add: __noop, remove: __noop, toggle: __noop, contains: function () { return false; } }
  };
  if (el.tagName === "CANVAS") {
    var ctx = __context();
    el.getContext = function () { ctx.canvas = el; return ctx; };
  }
  return el;
}
var __canvas = __element("canvas");
var document = {
  title: "", body: __element("body"), documentElement: __element("html"),
  getElementById: function (id) { return id === "game" ? __canvas : null; },
  querySelector: function (selector) { return selector === "canvas" || selector === "#game" ? __canvas : null; },
  createElement: function (tag) { return __element(tag); },
  addEventListener: __addListener("document"), removeEventListener: __noop
};
window.addEventListener = __addListener("window");
window.removeEventListener = __noop;
window.innerWidth = 1280;
window.innerHeight = 720;
window.devicePixelRatio = 1;
var console = {
  log: function () { __aven.logs.push(Array.prototype.join.call(arguments, " ")); },
  warn: function () { __aven.logs.push(Array.prototype.join.call(arguments, " ")); },
  error: function () { __aven.logs.push("ERROR " + Array.prototype.join.call(arguments, " ")); },
  info: function () {}
};
var performance = { now: function () { return __aven.now; } };
__aven.now = 0;
function requestAnimationFrame(fn) { __aven.raf.push(fn); return __aven.raf.length; }
function cancelAnimationFrame() {}
function setTimeout(fn, ms) { __aven.timers.push({ fn: fn, at: __aven.now + (ms || 0) }); return __aven.timers.length; }
function clearTimeout() {}
function setInterval(fn, ms) { __aven.timers.push({ fn: fn, at: __aven.now + (ms || 0), every: Math.max(1, ms || 1) }); return __aven.timers.length; }
function clearInterval() {}
var localStorage = (function () {
  var data = {};
  return {
    getItem: function (k) { return Object.prototype.hasOwnProperty.call(data, k) ? data[k] : null; },
    setItem: function (k, v) { data[k] = String(v); }, removeItem: function (k) { delete data[k]; }
  };
})();
function Image() { this.width = 0; this.height = 0; this.onload = null; }
Date.now = function () { return __aven.now; };

function __dispatch(type, code) {
  var event = { type: type, code: code, key: code, preventDefault: __noop, stopPropagation: __noop };
  ["window:" + type, "document:" + type].forEach(function (k) { (__aven.listeners[k] || []).forEach(function (fn) { fn(event); }); });
}
function __runFrames(count, presses) {
  for (var i = 0; i < count; i++) {
    (presses[i] || []).forEach(function (p) { __dispatch(p[0], p[1]); });
    __aven.now += 1000 / 60;
    var due = __aven.timers.filter(function (t) { return t.at <= __aven.now; });
    __aven.timers = __aven.timers.filter(function (t) { return t.at > __aven.now || t.every; });
    due.forEach(function (t) { if (t.every) t.at += t.every; t.fn(); });
    var callbacks = __aven.raf; __aven.raf = [];
    callbacks.forEach(function (fn) { fn(__aven.now); });
  }
  var game = window.AVEN && window.AVEN.games[0];
  return JSON.stringify({
    draws: __aven.draws,
    logs: __aven.logs.slice(-20),
    games: window.AVEN ? window.AVEN.games.length : 0,
    error: game && game.error ? String(game.error && game.error.stack ? game.error.message + "\n" + game.error.stack : game.error) : "",
    scene: game ? game.sceneName() : "",
    frames: game ? game.frame : 0
  });
}
