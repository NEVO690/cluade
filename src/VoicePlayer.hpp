#pragma once
#include <Geode/Geode.hpp>
#include <Geode/fmod/fmod.hpp>
#include <string>

namespace taf {
    // Plays one voice line at a time through GD's FMOD system and reports the
    // playback position, which drives subtitle timing and mouth movement.
    class VoicePlayer {
    public:
        ~VoicePlayer();

        // Returns false (and stays silent) if the file is missing or cannot be decoded.
        bool play(std::string const& path, float volume);
        void stop();
        void setPaused(bool paused);
        void setVolume(float volume);

        bool isActive() const;      // a sound is loaded and still playing (or paused)
        float position() const;     // seconds
        float length() const;       // seconds, 0 if nothing loaded

    private:
        FMOD::Sound* m_sound = nullptr;
        FMOD::Channel* m_channel = nullptr;
        float m_length = 0.f;
    };
}
