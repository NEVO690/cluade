#pragma once
#include <Geode/Geode.hpp>

namespace taf {
    // Speaker name + subtitle text on a translucent panel.
    // Supports Hebrew (right-to-left) and English, word wrap, size and
    // position settings, and fades between cues.
    class SubtitleBox : public cocos2d::CCNodeRGBA {
    public:
        static SubtitleBox* create(float width);

        void show(std::string const& speaker, cocos2d::ccColor3B color, std::string const& text);
        void hide();
        void applySettings(); // re-reads size / uppercase and re-lays out

    protected:
        bool init(float width);
        void layout();

        float m_width = 400.f;
        std::string m_speaker;
        std::string m_text;
        cocos2d::ccColor3B m_color = {255, 255, 255};
        bool m_shown = false;

        cocos2d::extension::CCScale9Sprite* m_bg = nullptr;
        cocos2d::CCLabelBMFont* m_name = nullptr;
        cocos2d::CCNodeRGBA* m_lines = nullptr;
    };
}
