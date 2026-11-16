#include "Character.hpp"
#include <Geode/utils/file.hpp>
#include <random>

using namespace geode::prelude;

namespace taf {
    namespace {
        constexpr int TAG_IDLE = 1;
        constexpr int TAG_EMOTE = 2;
        constexpr int TAG_FOCUS = 3;

        std::mt19937& rng() {
            static std::mt19937 gen{std::random_device{}()};
            return gen;
        }
        float rnd(float a, float b) {
            return std::uniform_real_distribution<float>(a, b)(rng());
        }

        matjson::Value const& rigData() {
            static matjson::Value data = []() -> matjson::Value {
                for (auto const& path : {Mod::get()->getConfigDir() / "rig.json", Mod::get()->getResourcesDir() / "rig.json"}) {
                    if (!path.exists()) continue;
                    auto txt = utils::file::readString(path);
                    if (!txt) continue;
                    auto parsed = matjson::parse(txt.unwrap());
                    if (parsed) return parsed.unwrap();
                    log::error("TAF: rig.json is invalid: {}", parsed.unwrapErr().message);
                }
                log::error("TAF: rig.json not found, characters will be empty");
                return matjson::Value::object();
            }();
            return data;
        }

        CCPoint point(matjson::Value const& v, std::string_view key, CCPoint def) {
            if (!v.contains(key) || !v[key].isArray() || v[key].size() < 2) return def;
            return {
                static_cast<float>(v[key][0].asDouble().unwrapOr(def.x)),
                static_cast<float>(v[key][1].asDouble().unwrapOr(def.y)),
            };
        }

        CCFiniteTimeAction* ease(CCActionInterval* a) { return CCEaseSineInOut::create(a); }
    }

    Character* Character::create(std::string const& rigId, bool mirrored) {
        auto ret = new Character();
        if (ret->init(rigId, mirrored)) {
            ret->autorelease();
            return ret;
        }
        delete ret;
        return nullptr;
    }

    CCSprite* Character::makeSprite(std::string const& file) {
        auto name = Mod::get()->expandSpriteName(file);
        CCSprite* spr = CCSprite::create(name.c_str());
        if (!spr) {
            // Missing art should never crash the game: use an invisible sprite.
            log::warn("TAF: missing sprite '{}'", name);
            spr = CCSprite::create();
        }
        return spr;
    }

    CCNode* Character::part(std::string const& id) const {
        auto it = m_parts.find(id);
        return it == m_parts.end() ? nullptr : it->second;
    }

    bool Character::init(std::string const& rigId, bool mirrored) {
        if (!CCNode::init()) return false;
        m_isChicken = rigId == "chicken";

        m_flip = CCNode::create();
        m_flip->setScaleX(mirrored ? -1.f : 1.f);
        this->addChild(m_flip);
        m_body = CCNode::create();
        m_flip->addChild(m_body);

        auto const& all = rigData();
        if (!all.contains(rigId)) {
            log::error("TAF: rig '{}' not found in rig.json", rigId);
            return true; // empty but valid node
        }
        auto const& rig = all[rigId];
        m_height = static_cast<float>(rig.contains("height") ? rig["height"].asDouble().unwrapOr(140.0) : 140.0);
        if (!rig.contains("parts") || !rig["parts"].isArray()) return true;

        // Two passes so children can always find their parent.
        for (int pass = 0; pass < 2; ++pass) {
            for (auto const& p : rig["parts"]) {
                std::string id = p.contains("id") ? p["id"].asString().unwrapOr("") : "";
                std::string parentId = p.contains("parent") ? p["parent"].asString().unwrapOr("") : "";
                if ((pass == 0) != parentId.empty()) continue;

                CCNode* parent = m_body;
                if (!parentId.empty()) {
                    parent = this->part(parentId);
                    if (!parent) continue;
                }

                auto pos = point(p, "pos", {0, 0});
                auto anchor = point(p, "anchor", {0.5f, 0.5f});
                int z = static_cast<int>(p.contains("z") ? p["z"].asInt().unwrapOr(0) : 0);

                if (id == "eyes" || id == "mouth") {
                    // A holder node with one sprite per expression / mouth shape.
                    auto holder = CCNode::create();
                    holder->setPosition(pos);
                    parent->addChild(holder, z);
                    m_parts[id] = holder;
                    m_basePos[id] = pos;

                    auto addVariant = [&](std::string const& file) {
                        auto spr = this->makeSprite(file);
                        spr->setAnchorPoint(anchor);
                        spr->setVisible(false);
                        holder->addChild(spr);
                        m_tintable.push_back(spr);
                        return spr;
                    };
                    if (id == "eyes" && rig.contains("eyes")) {
                        for (auto const& [state, file] : rig["eyes"]) {
                            m_eyes[state] = addVariant(file.asString().unwrapOr(""));
                        }
                    } else if (id == "mouth" && rig.contains("mouth") && rig["mouth"].isArray()) {
                        for (auto const& file : rig["mouth"]) {
                            m_mouths.push_back(addVariant(file.asString().unwrapOr("")));
                        }
                    }
                    continue;
                }

                auto spr = this->makeSprite(p.contains("sprite") ? p["sprite"].asString().unwrapOr("") : "");
                spr->setAnchorPoint(anchor);
                spr->setPosition(pos);
                if (p.contains("color") && p["color"].isArray() && p["color"].size() >= 3) {
                    spr->setColor({
                        static_cast<GLubyte>(p["color"][0].asInt().unwrapOr(255)),
                        static_cast<GLubyte>(p["color"][1].asInt().unwrapOr(255)),
                        static_cast<GLubyte>(p["color"][2].asInt().unwrapOr(255)),
                    });
                }
                if (p.contains("additive") && p["additive"].asBool().unwrapOr(false)) {
                    spr->setBlendFunc({GL_SRC_ALPHA, GL_ONE});
                } else {
                    m_tintable.push_back(spr);
                }
                parent->addChild(spr, z);
                m_parts[id] = spr;
                m_basePos[id] = pos;
            }
        }

        for (auto spr : m_tintable) m_baseColor[spr] = spr->getColor();

        this->setEyes("open");
        this->setMouth(0);
        m_blinkTimer = rnd(1.5f, 4.f);
        this->startIdle();
        this->scheduleUpdate();
        return true;
    }

    void Character::setEyes(std::string const& state) {
        auto target = m_eyes.count(state) ? state : std::string("open");
        for (auto& [name, spr] : m_eyes) spr->setVisible(name == target);
    }

    void Character::setMouth(int frame) {
        if (m_mouths.empty()) return;
        frame = std::clamp(frame, 0, static_cast<int>(m_mouths.size()) - 1);
        m_mouthFrame = frame;
        for (size_t i = 0; i < m_mouths.size(); ++i) m_mouths[i]->setVisible(static_cast<int>(i) == frame);
    }

    void Character::setTalking(bool talking) {
        if (m_talking == talking) return;
        m_talking = talking;
        m_mouthTimer = 0.f;
        if (!talking) this->setMouth(0);
    }

    void Character::update(float dt) {
        // Blinking (skipped while laughing, which keeps the eyes shut)
        m_blinkTimer -= dt;
        if (m_blinkTimer <= 0.f) {
            if (!m_blinking) {
                m_blinking = true;
                this->setEyes("closed");
                m_blinkTimer = 0.11f;
            } else {
                m_blinking = false;
                this->setEyes(m_eyeState);
                // occasional double blink
                m_blinkTimer = rnd(0.f, 1.f) < 0.15f ? 0.18f : rnd(2.f, 5.f);
            }
        }

        // Mouth flaps while speaking: random shapes at a speech-like rate
        if (m_talking && !m_mouths.empty()) {
            m_mouthTimer -= dt;
            if (m_mouthTimer <= 0.f) {
                int next;
                do { next = static_cast<int>(rnd(0.f, static_cast<float>(m_mouths.size()) - 0.001f)); }
                while (next == m_mouthFrame && m_mouths.size() > 1);
                this->setMouth(next);
                m_mouthTimer = rnd(0.06f, 0.12f);
            }
        }

        // The chicken occasionally does a little head peck when idle
        if (m_isChicken && !m_talking && m_emotion == "neutral") {
            m_peckTimer -= dt;
            if (m_peckTimer <= 0.f) {
                m_peckTimer = rnd(3.f, 6.f);
                if (auto head = this->part("head"); head && !head->getActionByTag(TAG_EMOTE)) {
                    auto peck = CCSequence::create(
                        CCEaseOut::create(CCRotateBy::create(0.08f, 14.f), 2.f),
                        CCEaseIn::create(CCRotateBy::create(0.12f, -14.f), 2.f),
                        nullptr
                    );
                    peck->setTag(TAG_EMOTE);
                    head->runAction(peck);
                }
            }
        }
    }

    void Character::startIdle() {
        auto loop = [](CCNode* node, CCFiniteTimeAction* a, CCFiniteTimeAction* b) {
            if (!node) return;
            node->stopActionByTag(TAG_IDLE);
            auto act = CCRepeatForever::create(CCSequence::create(a, b, nullptr));
            act->setTag(TAG_IDLE);
            node->runAction(act);
        };
        float t = m_isChicken ? 0.9f : 1.3f;
        loop(this->part("torso"),
            ease(CCScaleTo::create(t, 1.f, 1.03f)), ease(CCScaleTo::create(t, 1.f, 1.f)));
        loop(this->part("head"),
            ease(CCRotateTo::create(t * 1.1f, m_isChicken ? 3.f : -2.f)), ease(CCRotateTo::create(t * 1.1f, m_isChicken ? -2.f : 2.f)));
        loop(this->part("arm_front"),
            ease(CCRotateTo::create(t * 1.2f, 5.f)), ease(CCRotateTo::create(t * 1.2f, -3.f)));
        loop(this->part("arm_back"),
            ease(CCRotateTo::create(t * 1.2f, -4.f)), ease(CCRotateTo::create(t * 1.2f, 4.f)));
        if (auto aura = this->part("aura")) {
            aura->stopActionByTag(TAG_IDLE);
            auto pulse = CCRepeatForever::create(CCSequence::create(
                CCSpawn::create(ease(CCScaleTo::create(1.6f, 1.06f)), CCFadeTo::create(1.6f, 230), nullptr),
                CCSpawn::create(ease(CCScaleTo::create(1.6f, 0.94f)), CCFadeTo::create(1.6f, 140), nullptr),
                nullptr
            ));
            pulse->setTag(TAG_IDLE);
            aura->runAction(pulse);
        }
    }

    void Character::resetPose(float time) {
        m_body->stopActionByTag(TAG_EMOTE);
        auto back = CCSpawn::create(
            CCEaseOut::create(CCMoveTo::create(time, {0, 0}), 2.f),
            CCEaseOut::create(CCScaleTo::create(time, 1.f), 2.f),
            CCEaseOut::create(CCRotateTo::create(time, 0.f), 2.f),
            nullptr
        );
        back->setTag(TAG_EMOTE);
        m_body->runAction(back);
        for (auto const& [id, node] : m_parts) {
            node->stopActionByTag(TAG_EMOTE);
            if (id == "eyes" || id == "mouth") continue;
            auto a = CCMoveTo::create(time, m_basePos[id]);
            a->setTag(TAG_EMOTE);
            node->runAction(a);
        }
        this->tintAll({255, 255, 255}, time);
    }

    void Character::tintAll(ccColor3B color, float time) {
        for (auto spr : m_tintable) {
            auto base = m_baseColor[spr];
            ccColor3B target = {
                static_cast<GLubyte>(base.r * color.r / 255),
                static_cast<GLubyte>(base.g * color.g / 255),
                static_cast<GLubyte>(base.b * color.b / 255),
            };
            spr->stopActionByTag(TAG_FOCUS);
            auto a = CCTintTo::create(time, target.r, target.g, target.b);
            a->setTag(TAG_FOCUS);
            spr->runAction(a);
        }
    }

    void Character::setFocused(bool focused) {
        if (m_focused == focused) return;
        m_focused = focused;
        this->tintAll(focused ? ccColor3B{255, 255, 255} : ccColor3B{175, 175, 190}, 0.25f);
        this->stopActionByTag(TAG_FOCUS);
        auto s = CCEaseSineInOut::create(CCScaleTo::create(0.25f, focused ? 1.f : 0.96f));
        s->setTag(TAG_FOCUS);
        this->runAction(s);
    }

    void Character::playEmotion(std::string const& emotion) {
        m_emotion = emotion;
        this->resetPose(0.15f);
        m_eyeState = "open";

        auto run = [&](CCNode* node, CCFiniteTimeAction* action) {
            if (!node || !action) return;
            auto seq = CCSequence::create(CCDelayTime::create(0.15f), action, nullptr);
            seq->setTag(TAG_EMOTE);
            node->stopActionByTag(TAG_EMOTE);
            node->runAction(seq);
        };
        auto flash = [&](ccColor3B c, float hold) {
            for (auto spr : m_tintable) {
                auto base = m_baseColor[spr];
                auto seq = CCSequence::create(
                    CCDelayTime::create(0.15f),
                    CCTintTo::create(0.06f, c.r, c.g, c.b),
                    CCDelayTime::create(hold),
                    CCTintTo::create(0.3f, base.r, base.g, base.b),
                    nullptr
                );
                seq->setTag(TAG_FOCUS);
                spr->stopActionByTag(TAG_FOCUS);
                spr->runAction(seq);
            }
        };
        auto armSwing = [&](float angle, float time) {
            if (auto arm = this->part("arm_front")) {
                arm->stopActionByTag(TAG_IDLE);
                run(arm, CCSequence::create(
                    CCEaseOut::create(CCRotateTo::create(time, angle), 2.f),
                    CCDelayTime::create(0.25f),
                    CCEaseInOut::create(CCRotateTo::create(0.35f, 0.f), 2.f),
                    CallFuncExt::create([this] { this->startIdle(); }),
                    nullptr
                ));
            }
        };

        if (emotion == "angry") {
            m_eyeState = "angry";
            run(m_body, CCSequence::create(
                CCMoveBy::create(0.04f, {3, 0}), CCMoveBy::create(0.04f, {-6, 0}),
                CCMoveBy::create(0.04f, {6, 0}), CCMoveBy::create(0.04f, {-6, 0}),
                CCMoveBy::create(0.04f, {3, 0}),
                CCEaseSineOut::create(CCScaleTo::create(0.2f, 1.04f)),
                nullptr
            ));
            flash({255, 150, 140}, 0.4f);
        } else if (emotion == "hit") {
            m_eyeState = "closed";
            run(m_body, CCSequence::create(
                CCSpawn::create(
                    CCEaseOut::create(CCMoveBy::create(0.12f, {-26, 6}), 2.f),
                    CCRotateTo::create(0.12f, -10.f),
                    CCScaleTo::create(0.12f, 1.1f, 0.88f),
                    nullptr
                ),
                CCSpawn::create(
                    CCEaseBounceOut::create(CCMoveTo::create(0.45f, {-12, 0})),
                    CCEaseOut::create(CCRotateTo::create(0.45f, 0.f), 2.f),
                    CCScaleTo::create(0.3f, 1.f),
                    nullptr
                ),
                CCDelayTime::create(0.5f),
                CCEaseInOut::create(CCMoveTo::create(0.4f, {0, 0}), 2.f),
                CallFuncExt::create([this] { m_eyeState = "open"; this->setEyes("open"); }),
                nullptr
            ));
            flash({255, 70, 70}, 0.1f);
        } else if (emotion == "laugh") {
            m_eyeState = "closed";
            run(m_body, CCRepeat::create(CCSequence::create(
                CCEaseOut::create(CCMoveBy::create(0.14f, {0, 7}), 2.f),
                CCEaseIn::create(CCMoveBy::create(0.14f, {0, -7}), 2.f),
                nullptr
            ), 4));
            if (auto head = this->part("head")) {
                head->stopActionByTag(TAG_IDLE);
                run(head, CCSequence::create(
                    CCEaseOut::create(CCRotateTo::create(0.2f, 10.f), 2.f),
                    CCDelayTime::create(0.9f),
                    CCEaseInOut::create(CCRotateTo::create(0.3f, 0.f), 2.f),
                    CallFuncExt::create([this] { m_eyeState = "open"; this->startIdle(); }),
                    nullptr
                ));
            }
        } else if (emotion == "aura") {
            if (auto aura = this->part("aura")) {
                aura->stopActionByTag(TAG_IDLE);
                run(aura, CCSequence::create(
                    CCSpawn::create(CCEaseOut::create(CCScaleTo::create(0.35f, 1.45f), 2.f), CCFadeTo::create(0.35f, 255), nullptr),
                    CCDelayTime::create(0.6f),
                    CCEaseInOut::create(CCScaleTo::create(0.6f, 1.f), 2.f),
                    CallFuncExt::create([this] { this->startIdle(); }),
                    nullptr
                ));
            }
            run(m_body, CCSequence::create(
                CCEaseOut::create(CCScaleTo::create(0.3f, 1.06f), 2.f),
                CCDelayTime::create(0.6f),
                CCEaseInOut::create(CCScaleTo::create(0.4f, 1.f), 2.f),
                nullptr
            ));
            armSwing(m_isChicken ? -60.f : -150.f, 0.3f);
        } else if (emotion == "attack") {
            m_eyeState = "angry";
            run(m_body, CCSequence::create(
                CCEaseIn::create(CCMoveBy::create(0.12f, {-10, 0}), 2.f),
                CCEaseOut::create(CCMoveBy::create(0.16f, {80, 4}), 3.f),
                CCDelayTime::create(0.25f),
                CCEaseInOut::create(CCMoveTo::create(0.45f, {0, 0}), 2.f),
                nullptr
            ));
            armSwing(m_isChicken ? -120.f : -110.f, 0.18f);
        } else if (emotion == "surprised") {
            run(m_body, CCSequence::create(
                CCEaseOut::create(CCMoveBy::create(0.15f, {0, 18}), 2.f),
                CCEaseBounceOut::create(CCMoveTo::create(0.4f, {0, 0})),
                nullptr
            ));
            if (auto eyes = this->part("eyes")) {
                run(eyes, CCSequence::create(
                    CCScaleTo::create(0.1f, 1.3f), CCDelayTime::create(0.8f), CCScaleTo::create(0.25f, 1.f), nullptr
                ));
            }
        } else if (emotion == "happy") {
            run(m_body, CCSequence::create(
                CCEaseOut::create(CCMoveBy::create(0.18f, {0, 10}), 2.f),
                CCEaseBounceOut::create(CCMoveTo::create(0.4f, {0, 0})),
                nullptr
            ));
            armSwing(m_isChicken ? -40.f : -70.f, 0.25f);
        }
        // "neutral" (or unknown) just returns to the idle pose.

        this->setEyes(m_blinking ? "closed" : m_eyeState);
    }
}
