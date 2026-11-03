const game = AVEN.createGame({ width: 640, height: 360, background: "#102030", title: "Coin Run" });
game.scene("title", {
  update(g) { if (g.input.pressed("enter") || g.input.pressed("space")) g.switchTo("play"); },
  draw(g) { g.clear(); g.text("COIN RUN", 320, 120, { align: "center", size: 40, bold: true }); g.text("Press Enter", 320, 200, { align: "center" }); },
});
game.scene("play", {
  enter(g) { g.state.p = { x: 50, y: 50, w: 20, h: 20 }; g.state.score = 0; },
  update(g, dt) { const p = g.state.p; p.x += g.input.axisX() * 150 * dt; p.y += g.input.axisY() * 150 * dt; },
  draw(g) { g.clear(); g.rect(g.state.p.x, g.state.p.y, 20, 20, "#7b6cff"); g.text("Score " + g.state.score, 10, 10); },
});
game.start("title");
