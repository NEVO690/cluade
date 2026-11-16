#include "VoicePlayer.hpp"

using namespace geode::prelude;

namespace taf {
    VoicePlayer::~VoicePlayer() {
        this->stop();
    }

    bool VoicePlayer::play(std::string const& path, float volume) {
        this->stop();
        if (path.empty()) return false;

        auto engine = FMODAudioEngine::sharedEngine();
        if (!engine || !engine->m_system) return false;

        FMOD::Sound* sound = nullptr;
        auto res = engine->m_system->createSound(path.c_str(), FMOD_DEFAULT, nullptr, &sound);
        if (res != FMOD_OK || !sound) {
            log::warn("TAF: could not load voice file '{}' (FMOD error {})", path, static_cast<int>(res));
            return false;
        }

        unsigned int lenMs = 0;
        sound->getLength(&lenMs, FMOD_TIMEUNIT_MS);

        FMOD::Channel* channel = nullptr;
        res = engine->m_system->playSound(sound, nullptr, true, &channel);
        if (res != FMOD_OK || !channel) {
            sound->release();
            log::warn("TAF: could not play voice file '{}'", path);
            return false;
        }
        channel->setVolume(std::clamp(volume, 0.f, 1.f));
        channel->setPaused(false);

        m_sound = sound;
        m_channel = channel;
        m_length = static_cast<float>(lenMs) / 1000.f;
        return true;
    }

    void VoicePlayer::stop() {
        if (m_channel) {
            m_channel->stop(); // harmless if the channel already finished
            m_channel = nullptr;
        }
        if (m_sound) {
            m_sound->release();
            m_sound = nullptr;
        }
        m_length = 0.f;
    }

    void VoicePlayer::setPaused(bool paused) {
        if (m_channel) m_channel->setPaused(paused);
    }

    void VoicePlayer::setVolume(float volume) {
        if (m_channel) m_channel->setVolume(std::clamp(volume, 0.f, 1.f));
    }

    bool VoicePlayer::isActive() const {
        if (!m_channel) return false;
        bool playing = false;
        if (m_channel->isPlaying(&playing) != FMOD_OK) return false;
        return playing;
    }

    float VoicePlayer::position() const {
        if (!m_channel) return 0.f;
        unsigned int ms = 0;
        if (m_channel->getPosition(&ms, FMOD_TIMEUNIT_MS) != FMOD_OK) return m_length;
        return static_cast<float>(ms) / 1000.f;
    }

    float VoicePlayer::length() const {
        return m_length;
    }
}
