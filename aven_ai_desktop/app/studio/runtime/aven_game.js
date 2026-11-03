/* AVEN game engine 1.0 - a small 2D canvas engine for games made with Made With AVEN.
 *
 * Games create one game object and register scenes:
 *
 *   const game = AVEN.createGame({ width: 960, height: 540, background: "#0b1020", title: "My game" });
 *   game.scene("play", {
 *     enter(game, data) { game.state.player = { x: 100, y: 100, w: 32, h: 32 }; },
 *     update(game, dt) { if (game.input.down("right")) game.state.player.x += 200 * dt; },
 *     draw(game) { game.clear(); game.rect(game.state.player.x, game.state.player.y, 32, 32, "#7b6cff"); },
 *   });
 *   game.start("play");
 *
 * Runs in a browser and in AVEN's checking sandbox. No network access, no external files.
 */
(function (global) {
  "use strict";

  var KEY_NAMES = {
    ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down",
    KeyA: "a", KeyD: "d", KeyW: "w", KeyS: "s", Space: "space", Enter: "enter", NumpadEnter: "enter",
    ShiftLeft: "shift", ShiftRight: "shift", ControlLeft: "ctrl", ControlRight: "ctrl",
    Escape: "escape", Tab: "tab", Backspace: "backspace"
  };
  // Movement aliases: "left" is also A, "up" is also W, and so on.
  var ALIASES = { left: ["left", "a"], right: ["right", "d"], up: ["up", "w"], down: ["down", "s"] };

  function keyName(event) {
    if (KEY_NAMES[event.code]) return KEY_NAMES[event.code];
    if (/^Key[A-Z]$/.test(event.code || "")) return event.code.slice(3).toLowerCase();
    if (/^Digit[0-9]$/.test(event.code || "")) return event.code.slice(5);
    return String(event.key || "").toLowerCase();
  }

  function clamp(value, min, max) { return value < min ? min : value > max ? max : value; }
  function lerp(a, b, t) { return a + (b - a) * t; }

  function createGame(options) {
    options = options || {};
    var width = options.width || 960;
    var height = options.height || 540;
    var doc = global.document;
    var canvas = options.canvas || (doc && doc.getElementById && doc.getElementById("game"));
    if (!canvas && doc) {
      canvas = doc.createElement("canvas");
      if (doc.body && doc.body.appendChild) doc.body.appendChild(canvas);
    }
    canvas.width = width;
    canvas.height = height;
    var ctx = canvas.getContext("2d");
    if (doc && options.title) doc.title = options.title;

    var held = {};
    var pressedNow = {};
    var mouse = { x: 0, y: 0, down: false, clicked: false };

    function onKey(down) {
      return function (event) {
        var name = keyName(event);
        if (down && !held[name]) pressedNow[name] = true;
        held[name] = down;
        if (["left", "right", "up", "down", "space"].indexOf(name) >= 0 && event.preventDefault) event.preventDefault();
      };
    }
    if (global.addEventListener) {
      global.addEventListener("keydown", onKey(true));
      global.addEventListener("keyup", onKey(false));
      global.addEventListener("blur", function () { held = {}; });
    }
    if (canvas.addEventListener) {
      var toCanvas = function (event) {
        var rect = canvas.getBoundingClientRect ? canvas.getBoundingClientRect() : { left: 0, top: 0, width: width, height: height };
        mouse.x = (event.clientX - rect.left) * (width / (rect.width || width));
        mouse.y = (event.clientY - rect.top) * (height / (rect.height || height));
      };
      canvas.addEventListener("mousemove", toCanvas);
      canvas.addEventListener("mousedown", function (e) { toCanvas(e); mouse.down = true; mouse.clicked = true; });
      canvas.addEventListener("mouseup", function () { mouse.down = false; });
    }

    var input = {
      mouse: mouse,
      down: function (name) {
        var names = ALIASES[name] || [name];
        for (var i = 0; i < names.length; i++) if (held[names[i]]) return true;
        return false;
      },
      pressed: function (name) {
        var names = ALIASES[name] || [name];
        for (var i = 0; i < names.length; i++) if (pressedNow[names[i]]) return true;
        return false;
      },
      axisX: function () { return (input.down("right") ? 1 : 0) - (input.down("left") ? 1 : 0); },
      axisY: function () { return (input.down("down") ? 1 : 0) - (input.down("up") ? 1 : 0); }
    };

    var scenes = {};
    var current = null;
    var currentName = "";
    var audio = null;

    var game = {
      width: width, height: height, canvas: canvas, ctx: ctx, input: input,
      state: {}, time: 0, frame: 0, error: null,
      camera: { x: 0, y: 0 },

      scene: function (name, definition) { scenes[name] = definition || {}; return game; },
      start: function (name, data) { game.switchTo(name, data); requestFrame(); return game; },
      switchTo: function (name, data) {
        if (!scenes[name]) throw new Error("No scene named '" + name + "'");
        if (current && current.exit) current.exit(game);
        current = scenes[name];
        currentName = name;
        game.camera.x = 0; game.camera.y = 0;
        if (current.enter) current.enter(game, data);
      },
      sceneName: function () { return currentName; },

      // math helpers
      clamp: clamp, lerp: lerp,
      random: function (min, max) { return min + Math.random() * (max - min); },
      randomInt: function (min, max) { return Math.floor(min + Math.random() * (max - min + 1)); },
      pick: function (list) { return list[Math.floor(Math.random() * list.length)]; },
      distance: function (a, b) { var dx = a.x - b.x, dy = a.y - b.y; return Math.sqrt(dx * dx + dy * dy); },
      overlap: function (a, b) { return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y; },
      circlesOverlap: function (a, b) { var r = a.r + b.r; var dx = a.x - b.x, dy = a.y - b.y; return dx * dx + dy * dy < r * r; },

      // camera
      follow: function (target, smoothing) {
        var tx = clamp(target.x + (target.w || 0) / 2 - width / 2, 0, Math.max(0, (game.worldWidth || width) - width));
        var ty = clamp(target.y + (target.h || 0) / 2 - height / 2, 0, Math.max(0, (game.worldHeight || height) - height));
        var s = smoothing === undefined ? 0.15 : smoothing;
        game.camera.x = lerp(game.camera.x, tx, s);
        game.camera.y = lerp(game.camera.y, ty, s);
      },
      world: function (drawFn) {
        ctx.save();
        ctx.translate(-Math.round(game.camera.x), -Math.round(game.camera.y));
        try { drawFn(); } finally { ctx.restore(); }
      },

      // drawing
      clear: function (color) {
        ctx.fillStyle = color || options.background || "#000000";
        ctx.fillRect(0, 0, width, height);
      },
      rect: function (x, y, w, h, color) { ctx.fillStyle = color || "#ffffff"; ctx.fillRect(x, y, w, h); },
      strokeRect: function (x, y, w, h, color, lineWidth) {
        ctx.strokeStyle = color || "#ffffff"; ctx.lineWidth = lineWidth || 1; ctx.strokeRect(x, y, w, h);
      },
      circle: function (x, y, r, color) {
        ctx.fillStyle = color || "#ffffff"; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
      },
      line: function (x1, y1, x2, y2, color, lineWidth) {
        ctx.strokeStyle = color || "#ffffff"; ctx.lineWidth = lineWidth || 1;
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
      },
      text: function (value, x, y, style) {
        style = style || {};
        ctx.fillStyle = style.color || "#ffffff";
        ctx.font = (style.bold ? "bold " : "") + (style.size || 20) + "px " + (style.font || "sans-serif");
        ctx.textAlign = style.align || "left";
        ctx.textBaseline = style.baseline || "top";
        ctx.fillText(String(value), x, y);
      },

      // sound: short generated tones (no files)
      beep: function (frequency, duration, volume) {
        try {
          var AudioCtx = global.AudioContext || global.webkitAudioContext;
          if (!AudioCtx) return;
          audio = audio || new AudioCtx();
          var osc = audio.createOscillator(), gain = audio.createGain();
          osc.frequency.value = frequency || 440;
          gain.gain.value = volume === undefined ? 0.05 : volume;
          osc.connect(gain); gain.connect(audio.destination);
          osc.start(); osc.stop(audio.currentTime + (duration || 0.1));
        } catch (e) { /* sound is optional */ }
      },

      // saving small values such as a high score
      save: function (key, value) {
        try { global.localStorage.setItem("aven:" + key, JSON.stringify(value)); } catch (e) { /* storage is optional */ }
      },
      load: function (key, fallback) {
        try {
          var raw = global.localStorage.getItem("aven:" + key);
          return raw === null ? fallback : JSON.parse(raw);
        } catch (e) { return fallback; }
      }
    };

    var STEP = 1 / 60;
    var last = null;
    var pending = false;

    function showError(error) {
      game.error = error;
      if (global.console && global.console.error) global.console.error(error && error.stack ? error.stack : String(error));
      try {
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.fillStyle = "rgba(10, 0, 0, 0.85)"; ctx.fillRect(0, 0, width, height);
        game.text("The game stopped because of an error:", 24, 24, { color: "#ff8080", size: 18 });
        game.text(String(error && error.message ? error.message : error), 24, 54, { color: "#ffffff", size: 16 });
      } catch (e) { /* nothing more to do */ }
    }

    function tick(timestamp) {
      pending = false;
      if (game.error) return;
      if (last === null) last = timestamp;
      var elapsed = Math.min(0.25, Math.max(0, (timestamp - last) / 1000));
      last = timestamp;
      try {
        while (elapsed >= STEP - 1e-9) {
          game.time += STEP;
          game.frame += 1;
          if (current && current.update) current.update(game, STEP);
          pressedNow = {};
          mouse.clicked = false;
          elapsed -= STEP;
        }
        last -= elapsed * 1000;  // carry the remainder
        if (current && current.draw) current.draw(game);
      } catch (error) {
        showError(error);
        return;
      }
      requestFrame();
    }

    function requestFrame() {
      if (pending) return;
      pending = true;
      (global.requestAnimationFrame || function (fn) { return global.setTimeout(function () { fn(Date.now()); }, 16); })(tick);
    }

    games.push(game);
    return game;
  }

  var games = [];
  global.AVEN = { version: "1.0", createGame: createGame, games: games, clamp: clamp, lerp: lerp };
})(typeof window !== "undefined" ? window : globalThis);
