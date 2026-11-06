"""Builds data/maps/*.json from compact symmetric layouts.

Tile legend (also used by the in-game map editor):
  .  floor            #  wall (indestructible)     B  bush (hides brawlers)
  C  crate (breakable) X  barrel (breakable)        W  water (blocks walking only)
  P  power box (solo survival, breakable, drops power cube)
  1  team 1 spawn     2  team 2 spawn               S  solo spawn
  G  gem mine         O  orb spawn (goal rush)      A/R  goal of team 1 / team 2
  Z  zone centre (zone control)
Team maps: write the left 16 columns (column 15 = centre); the right side is mirrored.
Solo maps: write the top-left quadrant 18x13 (last column/row = centre); mirrored both ways.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "maps")

SWAP = {"1": "2", "2": "1", "A": "R", "R": "A"}

TEAM_MAPS = {
    "crystal_canyon": ("desert", ["gem_collection", "team_survival"], [
        "......BBB.......",
        "..##..BBB...##..",
        "..##........##..",
        "........CC......",
        "BB...#......BBB.",
        "BB...#..WW..BBB.",
        "..........#.....",
        ".1....BB..#.....",
        "......BB........",
        ".1..........C..G",
        "......BB........",
        ".1....BB..#.....",
        "..........#.....",
        "BB...#..WW..BBB.",
        "BB...#......BBB.",
        "........CC......",
        "..##........##..",
        "..##..BBB...##..",
        "......BBB.......",
    ]),
    "neon_mine": ("neon", ["gem_collection", "team_survival"], [
        "....#.....BB....",
        "....#.....BB....",
        ".BB...CC........",
        ".BB.......###...",
        "......#.........",
        "..#...#...BB....",
        "..#.......BB..W.",
        ".1...BBB......W.",
        ".....BBB...#....",
        ".1.........#...G",
        ".....BBB...#....",
        ".1...BBB......W.",
        "..#.......BB..W.",
        "..#...#...BB....",
        "......#.........",
        ".BB.......###...",
        ".BB...CC........",
        "....#.....BB....",
        "....#.....BB....",
    ]),
    "lava_rift": ("lava", ["team_survival", "gem_collection"], [
        "......WW........",
        "..BB..WW....##..",
        "..BB........##..",
        "......##........",
        ".....C##..BB....",
        "..........BB..C.",
        "##...BB.........",
        ".....BB...#.....",
        ".1........#..BBB",
        ".1...C.........G",
        ".1........#..BBB",
        ".....BB...#.....",
        "##...BB.........",
        "..........BB..C.",
        ".....C##..BB....",
        "......##........",
        "..BB........##..",
        "..BB..WW....##..",
        "......WW........",
    ]),
    "sky_temple": ("temple", ["team_survival", "zone_control"], [
        "........#.......",
        ".BBB....#...BB..",
        ".BBB........BB..",
        ".....##.........",
        "..#..##...CC..##",
        "..#............#",
        "......BB........",
        ".1....BB..#.....",
        "..........#..BB.",
        ".1..CC.......BBZ",
        "..........#..BB.",
        ".1....BB..#.....",
        "......BB........",
        "..#............#",
        "..#..##...CC..##",
        ".....##.........",
        ".BBB........BB..",
        ".BBB....#...BB..",
        "........#.......",
    ]),
    "beach_arena": ("beach", ["goal_rush"], [
        "....BBB.........",
        "....BBB...WW....",
        "..........WW....",
        "##....#.........",
        "......#....BB...",
        "..C........BB...",
        "##..............",
        "A#.1.....BB...#.",
        "A........BB...#.",
        "A..1...........O",
        "A........BB...#.",
        "A#.1.....BB...#.",
        "##..............",
        "..C........BB...",
        "......#....BB...",
        "##....#.........",
        "..........WW....",
        "....BBB...WW....",
        "....BBB.........",
    ]),
    "rooftop_rush": ("city", ["goal_rush"], [
        "......#.........",
        "..BB..#...BBB...",
        "..BB......BBB...",
        "........#.......",
        "##..CC..#.......",
        ".#..........##..",
        "##....BB....##..",
        "A#.1..BB........",
        "A..........#....",
        "A..1.......#...O",
        "A..........#....",
        "A#.1..BB........",
        "##....BB....##..",
        ".#..........##..",
        "##..CC..#.......",
        "........#.......",
        "..BB......BBB...",
        "..BB..#...BBB...",
        "......#.........",
    ]),
    "twin_peaks": ("meadow", ["zone_control", "team_survival"], [
        "......BB........",
        "..##..BB......#.",
        "..##..........#Z",
        "........CC......",
        "BB..............",
        "BB...##...BB....",
        ".....##...BB....",
        ".1..........#...",
        "......BB....#...",
        ".1....BB.......Z",
        "......BB....#...",
        ".1..........#...",
        ".....##...BB....",
        "BB...##...BB....",
        "BB..............",
        "........CC......",
        "..##..........#Z",
        "..##..BB......#.",
        "......BB........",
    ]),
    "candy_fort": ("candy", ["zone_control", "team_survival"], [
        "........BB......",
        ".BB.....BB..##..",
        ".BB.........##..",
        ".....CC.........",
        "..#........BB...",
        "..#...##...BB...",
        "......##........",
        ".1.........#....",
        ".........BB#....",
        ".1.......BB....Z",
        ".........BB#....",
        ".1.........#....",
        "......##........",
        "..#...##...BB...",
        "..#........BB...",
        ".....CC.........",
        ".BB.........##..",
        ".BB.....BB..##..",
        "........BB......",
    ]),
    "ruins_circuit": ("ruins", ["zone_control", "team_survival"], [
        "....BBBB........",
        "....BBBB....#...",
        "............#...",
        "..##....C.......",
        "..##........BB..",
        "......#.....BB..",
        "......#.........",
        ".1..........##..",
        "................",
        ".1.......Z.....Z",
        "................",
        ".1..........##..",
        "......#.........",
        "......#.....BB..",
        "..##........BB..",
        "..##....C.......",
        "............#...",
        "....BBBB....#...",
        "....BBBB........",
    ]),
}

SOLO_MAPS = {
    "mushroom_wilds": ("forest", [
        "......BBB.........",
        ".S....BBB....P...S",
        "...........##.....",
        "..##..P....##..BB.",
        "..##...........BB.",
        ".......BB.........",
        "BB.....BB...#..P..",
        "BB..........#.....",
        ".....P............",
        "....##....BBB.....",
        "....##....BBB..##.",
        "..P............##.",
        "BB.....P.....W....",
    ]),
    "frost_fields": ("snow", [
        "..................",
        ".S..WW.....BB....S",
        "....WW..P..BB.....",
        "..........###.....",
        ".BB..#............",
        ".BB..#...P...BB...",
        "......BB.....BB...",
        "..P...BB..#.......",
        "..........#....P..",
        "##....##..........",
        ".....#......BBB...",
        "..P..#...C..BBB...",
        "BB.......C....P...",
    ]),
    "swamp_showdown": ("swamp", [
        "....WWW...........",
        ".S..WWW....P.....S",
        "........BB........",
        "..P.....BB..##....",
        "BB..........##..P.",
        "BB..##............",
        "....##...WW...BB..",
        ".........WW...BB..",
        "..BB..P...........",
        "..BB.......##..##.",
        "...........##..##.",
        ".P....BBB.........",
        "......BBB....P....",
    ]),
}


def build_team(rows):
    out = []
    for i, r in enumerate(rows):
        if len(r) != 16:
            raise ValueError("row %d has %d chars: %r" % (i, len(r), r))
        right = "".join(SWAP.get(c, c) for c in reversed(r[:15]))
        out.append(r + right)
    return out


def build_solo(rows):
    if len(rows) != 13:
        raise ValueError("solo quadrant needs 13 rows")
    half = []
    for i, r in enumerate(rows):
        if len(r) != 18:
            raise ValueError("row %d has %d chars: %r" % (i, len(r), r))
        half.append(r + "".join(reversed(r[:17])))
    return half + list(reversed(half[:12]))


def main():
    os.makedirs(OUT, exist_ok=True)
    for mid, (theme, modes, rows) in TEAM_MAPS.items():
        tiles = build_team(rows)
        data = {"id": mid, "theme": theme, "modes": modes, "tiles": tiles, "builtin": True}
        with open(os.path.join(OUT, mid + ".json"), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
    for mid, (theme, rows) in SOLO_MAPS.items():
        tiles = build_solo(rows)
        data = {"id": mid, "theme": theme, "modes": ["solo_survival"], "tiles": tiles, "builtin": True}
        with open(os.path.join(OUT, mid + ".json"), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
    print("built", len(TEAM_MAPS) + len(SOLO_MAPS), "maps")


if __name__ == "__main__":
    sys.exit(main())
