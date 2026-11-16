#include "Dialogue.hpp"
#include <Geode/utils/file.hpp>

using namespace geode::prelude;

namespace taf {
    CharacterInfo const* Script::character(std::string const& id) const {
        for (auto const& c : characters) {
            if (c.id == id) return &c;
        }
        return nullptr;
    }

    asp::fs::Path userDir() {
        return Mod::get()->getConfigDir();
    }

    asp::fs::Path audioDir() {
        auto dir = userDir() / "audio";
        if (!dir.exists()) {
            (void)utils::file::createDirectoryAll(dir);
        }
        return dir;
    }

    namespace {
        std::string str(matjson::Value const& v, std::string_view key, std::string def = "") {
            if (!v.contains(key)) return def;
            return v[key].asString().unwrapOr(def);
        }
        float num(matjson::Value const& v, std::string_view key, float def = 0.f) {
            if (!v.contains(key)) return def;
            return static_cast<float>(v[key].asDouble().unwrapOr(def));
        }

        Script fallbackScript() {
            Script s;
            s.characters.push_back({"aura", "Aura Farmer", "aura", "left", {90, 220, 255}});
            s.characters.push_back({"larry", "Larper Larry", "chicken", "right", {255, 90, 80}});
            Scene sc;
            sc.id = "taf";
            sc.title = "TAF";
            Line l1; l1.speaker = "aura"; l1.emotion = "aura"; l1.text = "[dialogue.json is missing or broken]";
            Line l2; l2.speaker = "larry"; l2.emotion = "angry"; l2.listener = "surprised"; l2.text = "[Add your lines in dialogue.json]";
            sc.lines = {l1, l2};
            s.scenes.push_back(sc);
            return s;
        }
    }

    Result<Script> parseScript(std::string const& json) {
        auto parsed = matjson::parse(json);
        if (!parsed) {
            return Err(fmt::format("JSON error: {}", parsed.unwrapErr().message));
        }
        auto root = parsed.unwrap();
        Script script;

        if (!root.contains("characters") || !root["characters"].isObject()) {
            return Err("\"characters\" is missing");
        }
        for (auto const& [id, c] : root["characters"]) {
            CharacterInfo info;
            info.id = id;
            info.name = str(c, "name", id);
            info.rig = str(c, "rig", id);
            info.side = str(c, "side", "left");
            if (c.contains("color") && c["color"].isArray() && c["color"].size() >= 3) {
                auto ch = [&](size_t i) {
                    return static_cast<GLubyte>(std::clamp<intmax_t>(c["color"][i].asInt().unwrapOr(255), 0, 255));
                };
                info.color = {ch(0), ch(1), ch(2)};
            }
            script.characters.push_back(info);
        }
        if (script.characters.empty()) return Err("no characters defined");

        if (!root.contains("scenes") || !root["scenes"].isArray()) {
            return Err("\"scenes\" is missing");
        }
        for (auto const& s : root["scenes"]) {
            Scene scene;
            scene.id = str(s, "id", "scene");
            scene.title = str(s, "title", scene.id);
            if (!s.contains("lines") || !s["lines"].isArray()) continue;
            for (auto const& l : s["lines"]) {
                Line line;
                line.speaker = str(l, "speaker");
                if (!script.character(line.speaker)) {
                    log::warn("TAF: line speaker '{}' is not a known character, skipping", line.speaker);
                    continue;
                }
                line.text = str(l, "text");
                line.audio = str(l, "audio");
                line.emotion = str(l, "emotion", "neutral");
                line.listener = str(l, "listener", "neutral");
                line.duration = std::max(0.f, num(l, "duration", 0.f));
                if (l.contains("cues") && l["cues"].isArray()) {
                    for (auto const& c : l["cues"]) {
                        Cue cue;
                        cue.start = std::max(0.f, num(c, "start"));
                        cue.end = std::max(cue.start + 0.05f, num(c, "end", cue.start + 1.f));
                        cue.text = str(c, "text");
                        line.cues.push_back(cue);
                    }
                    std::sort(line.cues.begin(), line.cues.end(), [](Cue const& a, Cue const& b) {
                        return a.start < b.start;
                    });
                }
                scene.lines.push_back(std::move(line));
            }
            if (!scene.lines.empty()) script.scenes.push_back(std::move(scene));
        }
        if (script.scenes.empty()) return Err("no scenes with valid lines");
        return Ok(std::move(script));
    }

    LoadResult loadScript() {
        LoadResult res;
        std::vector<std::pair<asp::fs::Path, std::string>> candidates = {
            {userDir() / "dialogue.json", "custom"},
            {Mod::get()->getResourcesDir() / "dialogue.json", "built-in"},
        };
        for (auto const& [path, source] : candidates) {
            if (!path.exists()) continue;
            auto content = utils::file::readString(path);
            if (!content) {
                res.warning = fmt::format("Could not read {} dialogue file", source);
                continue;
            }
            auto parsed = parseScript(content.unwrap());
            if (!parsed) {
                res.warning = fmt::format("{} dialogue.json: {}", source, parsed.unwrapErr());
                log::error("TAF: {}", res.warning);
                continue;
            }
            res.script = std::move(parsed.unwrap());
            res.source = source;
            return res;
        }
        if (res.warning.empty()) res.warning = "dialogue.json not found";
        res.script = fallbackScript();
        res.source = "fallback";
        return res;
    }

    std::string findAudio(std::string const& name) {
        if (name.empty()) return "";
        std::vector<asp::fs::Path> candidates = {
            audioDir() / name,
            userDir() / name,
            Mod::get()->getResourcesDir() / name,
        };
        for (auto const& p : candidates) {
            if (p.exists()) return p.string();
        }
        return "";
    }

    float estimateDuration(std::string const& text) {
        // ~14 characters per second of reading + a short pause
        size_t chars = 0;
        for (unsigned char c : text) {
            if ((c & 0xC0) != 0x80) ++chars; // count UTF-8 code points
        }
        return std::clamp(0.9f + static_cast<float>(chars) / 14.f, 1.4f, 9.f);
    }
}
