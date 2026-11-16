#pragma once
#include <Geode/Geode.hpp>
#include <unordered_map>
#include <vector>

namespace taf {
    // A layered 2D puppet built from rig.json. Each body part is its own sprite,
    // so the character can breathe, blink, talk and react instead of being a
    // static picture. Characters face right; `mirrored` makes one face left.
    class Character : public cocos2d::CCNode {
    public:
        static Character* create(std::string const& rigId, bool mirrored);

        void setTalking(bool talking);
        bool isTalking() const { return m_talking; }

        // neutral, happy, angry, hit, laugh, aura, attack, surprised
        void playEmotion(std::string const& emotion);

        // Listener characters are dimmed slightly so the speaker stands out.
        void setFocused(bool focused);

        float rigHeight() const { return m_height; }

    protected:
        bool init(std::string const& rigId, bool mirrored);
        void update(float dt) override;

        cocos2d::CCSprite* makeSprite(std::string const& file);
        cocos2d::CCNode* part(std::string const& id) const;
        void setEyes(std::string const& state);
        void setMouth(int frame);
        void startIdle();
        void resetPose(float time);
        void tintAll(cocos2d::ccColor3B color, float time);

        cocos2d::CCNode* m_flip = nullptr;   // mirrors the whole puppet
        cocos2d::CCNode* m_body = nullptr;   // whole-body moves (jump, lunge, shake)
        std::unordered_map<std::string, cocos2d::CCNode*> m_parts;
        std::unordered_map<std::string, cocos2d::CCPoint> m_basePos;
        std::unordered_map<std::string, cocos2d::CCSprite*> m_eyes;   // state -> sprite
        std::vector<cocos2d::CCSprite*> m_mouths;                      // closed, mid, open
        std::vector<cocos2d::CCSprite*> m_tintable;
        std::unordered_map<cocos2d::CCSprite*, cocos2d::ccColor3B> m_baseColor;

        std::string m_eyeState = "open";
        std::string m_emotion = "neutral";
        bool m_talking = false;
        bool m_blinking = false;
        bool m_focused = true;
        float m_blinkTimer = 2.f;
        float m_mouthTimer = 0.f;
        float m_peckTimer = 3.f;
        float m_height = 140.f;
        int m_mouthFrame = 0;
        bool m_isChicken = false;
    };
}
