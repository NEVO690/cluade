#pragma once
#include <Geode/Geode.hpp>

namespace taf {
    class TAFLayer;

    // Quick settings inside the TAF screen. Every change is saved to the
    // mod's Geode settings immediately and applied live.
    class TAFSettingsPopup : public geode::Popup {
    public:
        static TAFSettingsPopup* create(TAFLayer* layer);

    protected:
        bool init(TAFLayer* layer);
        void addToggle(cocos2d::CCMenu* menu, char const* text, char const* key, float y);
        cocos2d::CCLabelBMFont* addSlider(char const* text, float x, float y, float value, cocos2d::SEL_MenuHandler sel, Slider** out);
        void updateSliderLabels();

        void onToggle(cocos2d::CCObject* sender);
        void onVolume(cocos2d::CCObject* sender);
        void onSize(cocos2d::CCObject* sender);
        void onAudioFolder(cocos2d::CCObject*);
        void onReload(cocos2d::CCObject*);
        void onAllSettings(cocos2d::CCObject*);

        TAFLayer* m_layer = nullptr;
        Slider* m_volume = nullptr;
        Slider* m_size = nullptr;
        cocos2d::CCLabelBMFont* m_volumeLabel = nullptr;
        cocos2d::CCLabelBMFont* m_sizeLabel = nullptr;
        std::vector<std::string> m_keys; // toggle tag -> setting key
    };
}
