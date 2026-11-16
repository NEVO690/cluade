#pragma once
#include <Geode/Geode.hpp>
#include <string>
#include <vector>

namespace taf {
    struct Cue {
        float start = 0.f;
        float end = 0.f;
        std::string text;
    };

    struct Line {
        std::string speaker;     // character id
        std::string text;
        std::string audio;       // file name, optional
        std::string emotion = "neutral";
        std::string listener = "neutral";
        float duration = 0.f;    // optional; 0 = automatic
        std::vector<Cue> cues;   // optional; empty = one cue for the whole line
    };

    struct Scene {
        std::string id;
        std::string title;
        std::vector<Line> lines;
    };

    struct CharacterInfo {
        std::string id;
        std::string name;
        std::string rig;
        std::string side = "left";
        cocos2d::ccColor3B color = {255, 255, 255};
    };

    struct Script {
        std::vector<CharacterInfo> characters;
        std::vector<Scene> scenes;

        CharacterInfo const* character(std::string const& id) const;
    };

    // Where the user can drop their own files:
    //   <config dir>/dialogue.json  -> replaces the built-in dialogue
    //   <config dir>/audio/*.ogg|mp3|wav -> voice lines
    asp::fs::Path userDir();
    asp::fs::Path audioDir();

    struct LoadResult {
        Script script;
        std::string source;   // "custom" / "built-in" / "fallback"
        std::string warning;  // non-empty when something was wrong
    };

    geode::Result<Script> parseScript(std::string const& json);
    LoadResult loadScript();

    // Finds an audio file for a line; returns empty string when missing.
    std::string findAudio(std::string const& name);

    // Estimated reading time when there is neither audio nor an explicit duration.
    float estimateDuration(std::string const& text);
}
