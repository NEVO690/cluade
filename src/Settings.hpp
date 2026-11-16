#pragma once
#include <Geode/Geode.hpp>

// Small typed accessors around the mod settings declared in mod.json,
// so the rest of the code never repeats string keys.
namespace taf::settings {
    inline bool get(std::string_view key) {
        return geode::Mod::get()->getSettingValue<bool>(key);
    }
    inline float getF(std::string_view key) {
        return static_cast<float>(geode::Mod::get()->getSettingValue<double>(key));
    }
    inline void set(std::string_view key, bool v) {
        geode::Mod::get()->setSettingValue<bool>(key, v);
    }
    inline void setF(std::string_view key, float v) {
        geode::Mod::get()->setSettingValue<double>(key, static_cast<double>(v));
    }

    inline bool enabled()        { return get("enabled"); }
    inline bool showSubtitles()  { return get("show-subtitles"); }
    inline bool subtitlesTop()   { return get("subtitles-top"); }
    inline bool uppercase()      { return get("subtitle-uppercase"); }
    inline bool autoAdvance()    { return get("auto-advance"); }
    inline float subtitleSize()  { return getF("subtitle-size"); }
    inline float voiceVolume()   { return getF("voice-volume"); }
}
