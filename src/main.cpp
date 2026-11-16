#include <Geode/Geode.hpp>
#include <Geode/modify/MenuLayer.hpp>
#include "TAFLayer.hpp"
#include "Settings.hpp"

using namespace geode::prelude;

// Adds the TAF button to the main menu (when the mod is enabled).
class $modify(TAFMenuLayer, MenuLayer) {
    bool init() {
        if (!MenuLayer::init()) return false;
        if (!taf::settings::enabled()) return true;

        auto icon = CCSprite::create("taf_icon.png"_spr);
        CCNode* btnSprite = nullptr;
        if (icon) {
            icon->setScale(0.9f);
            btnSprite = CircleButtonSprite::create(icon, CircleBaseColor::Cyan, CircleBaseSize::MediumAlt);
        }
        if (!btnSprite) {
            btnSprite = ButtonSprite::create("TAF");
        }
        auto btn = CCMenuItemSpriteExtra::create(btnSprite, this, menu_selector(TAFMenuLayer::onTAF));
        btn->setID("taf-button"_spr);

        // Prefer GD's bottom menu (node IDs are provided by Geode); otherwise
        // use our own small menu so we never fight with other mods' layouts.
        if (auto bottom = this->getChildByID("bottom-menu")) {
            bottom->addChild(btn);
            bottom->updateLayout();
        } else {
            auto menu = CCMenu::create();
            menu->setID("taf-menu"_spr);
            auto win = CCDirector::get()->getWinSize();
            menu->setPosition({win.width - 40.f, 95.f});
            menu->addChild(btn);
            this->addChild(menu, 10);
        }
        return true;
    }

    void onTAF(CCObject*) {
        taf::TAFLayer::open();
    }
};
