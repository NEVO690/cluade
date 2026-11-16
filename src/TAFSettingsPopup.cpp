#include "TAFSettingsPopup.hpp"
#include "TAFLayer.hpp"
#include "Settings.hpp"
#include "Dialogue.hpp"
#include <Geode/ui/GeodeUI.hpp>
#include <Geode/utils/file.hpp>

using namespace geode::prelude;

namespace taf {
    namespace {
        constexpr float POPUP_W = 360.f;
        constexpr float POPUP_H = 250.f;
        constexpr float SUB_SIZE_MIN = 0.5f;
        constexpr float SUB_SIZE_MAX = 1.5f;
    }

    TAFSettingsPopup* TAFSettingsPopup::create(TAFLayer* layer) {
        auto ret = new TAFSettingsPopup();
        if (ret->init(layer)) {
            ret->autorelease();
            return ret;
        }
        delete ret;
        return nullptr;
    }

    bool TAFSettingsPopup::init(TAFLayer* layer) {
        if (!Popup::init(POPUP_W, POPUP_H)) return false;
        m_layer = layer;
        this->setTitle("TAF Settings");

        auto menu = CCMenu::create();
        menu->setPosition({0, 0});
        menu->setContentSize({POPUP_W, POPUP_H});
        m_mainLayer->addChild(menu, 5);

        float y = POPUP_H - 58.f;
        this->addToggle(menu, "Mod Enabled", "enabled", y);
        this->addToggle(menu, "Subtitles", "show-subtitles", y -= 30.f);
        this->addToggle(menu, "Subtitles On Top", "subtitles-top", y -= 30.f);
        this->addToggle(menu, "Uppercase", "subtitle-uppercase", y -= 30.f);
        this->addToggle(menu, "Auto Play Next", "auto-advance", y -= 30.f);

        m_volumeLabel = this->addSlider("Voice Volume", 265.f, POPUP_H - 62.f, settings::voiceVolume(),
            menu_selector(TAFSettingsPopup::onVolume), &m_volume);
        float sizeNorm = (settings::subtitleSize() - SUB_SIZE_MIN) / (SUB_SIZE_MAX - SUB_SIZE_MIN);
        m_sizeLabel = this->addSlider("Subtitle Size", 265.f, POPUP_H - 122.f, sizeNorm,
            menu_selector(TAFSettingsPopup::onSize), &m_size);
        this->updateSliderLabels();

        auto mkBtn = [&](char const* text, SEL_MenuHandler sel, float x) {
            auto spr = ButtonSprite::create(text, "goldFont.fnt", "GJ_button_04.png", 0.7f);
            spr->setScale(0.7f);
            auto btn = CCMenuItemSpriteExtra::create(spr, this, sel);
            btn->setPosition({x, 28.f});
            menu->addChild(btn);
        };
        mkBtn("Audio Folder", menu_selector(TAFSettingsPopup::onAudioFolder), 70.f);
        mkBtn("Reload", menu_selector(TAFSettingsPopup::onReload), POPUP_W / 2.f);
        mkBtn("All Settings", menu_selector(TAFSettingsPopup::onAllSettings), POPUP_W - 70.f);

        auto hint = CCLabelBMFont::create("Put voice files in the Audio Folder, then press Reload.", "chatFont.fnt");
        hint->setScale(0.5f);
        hint->setOpacity(190);
        hint->setPosition({POPUP_W / 2.f, 52.f});
        m_mainLayer->addChild(hint);
        return true;
    }

    void TAFSettingsPopup::addToggle(CCMenu* menu, char const* text, char const* key, float y) {
        auto toggle = CCMenuItemToggler::createWithStandardSprites(this, menu_selector(TAFSettingsPopup::onToggle), 0.65f);
        toggle->toggle(settings::get(key));
        toggle->setTag(static_cast<int>(m_keys.size()));
        toggle->setPosition({32.f, y});
        menu->addChild(toggle);
        m_keys.emplace_back(key);

        auto label = CCLabelBMFont::create(text, "bigFont.fnt");
        label->setScale(0.42f);
        label->setAnchorPoint({0.f, 0.5f});
        label->setPosition({52.f, y});
        m_mainLayer->addChild(label);
    }

    CCLabelBMFont* TAFSettingsPopup::addSlider(char const* text, float x, float y, float value, SEL_MenuHandler sel, Slider** out) {
        auto label = CCLabelBMFont::create(text, "bigFont.fnt");
        label->setScale(0.4f);
        label->setPosition({x, y});
        m_mainLayer->addChild(label);

        auto slider = Slider::create(this, sel, 0.65f);
        slider->setValue(std::clamp(value, 0.f, 1.f));
        slider->setPosition({x, y - 24.f});
        m_mainLayer->addChild(slider);
        *out = slider;
        return label;
    }

    void TAFSettingsPopup::updateSliderLabels() {
        if (m_volumeLabel) {
            m_volumeLabel->setString(fmt::format("Voice Volume: {}%", static_cast<int>(std::round(settings::voiceVolume() * 100))).c_str());
        }
        if (m_sizeLabel) {
            m_sizeLabel->setString(fmt::format("Subtitle Size: {:.2f}x", settings::subtitleSize()).c_str());
        }
    }

    void TAFSettingsPopup::onToggle(CCObject* sender) {
        auto toggle = static_cast<CCMenuItemToggler*>(sender);
        auto idx = static_cast<size_t>(toggle->getTag());
        if (idx >= m_keys.size()) return;
        // The callback fires *before* the toggler flips its state.
        settings::set(m_keys[idx], !toggle->isToggled());
        if (m_layer) m_layer->applySettings();
    }

    void TAFSettingsPopup::onVolume(CCObject*) {
        if (!m_volume) return;
        settings::setF("voice-volume", std::round(m_volume->getThumb()->getValue() * 100.f) / 100.f);
        this->updateSliderLabels();
        if (m_layer) m_layer->applySettings();
    }

    void TAFSettingsPopup::onSize(CCObject*) {
        if (!m_size) return;
        float v = SUB_SIZE_MIN + m_size->getThumb()->getValue() * (SUB_SIZE_MAX - SUB_SIZE_MIN);
        settings::setF("subtitle-size", std::round(v * 20.f) / 20.f);
        this->updateSliderLabels();
        if (m_layer) m_layer->applySettings();
    }

    void TAFSettingsPopup::onAudioFolder(CCObject*) {
        utils::file::openFolder(audioDir());
    }

    void TAFSettingsPopup::onReload(CCObject*) {
        if (m_layer) m_layer->reloadScript();
        this->onClose(nullptr);
    }

    void TAFSettingsPopup::onAllSettings(CCObject*) {
        openSettingsPopup(Mod::get());
    }
}
