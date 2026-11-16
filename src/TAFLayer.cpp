#include "TAFLayer.hpp"
#include "TAFSettingsPopup.hpp"
#include "Settings.hpp"

using namespace geode::prelude;

namespace taf {
    TAFLayer* TAFLayer::create() {
        auto ret = new TAFLayer();
        if (ret->init()) {
            ret->autorelease();
            return ret;
        }
        delete ret;
        return nullptr;
    }

    CCScene* TAFLayer::scene() {
        auto scene = CCScene::create();
        scene->addChild(TAFLayer::create());
        return scene;
    }

    void TAFLayer::open() {
        CCDirector::get()->pushScene(CCTransitionFade::create(0.5f, TAFLayer::scene()));
    }

    bool TAFLayer::init() {
        if (!CCLayer::init()) return false;
        this->setID("taf-layer"_spr);

        auto loaded = loadScript();
        m_script = std::move(loaded.script);
        if (!loaded.warning.empty()) {
            Notification::create(fmt::format("TAF: {}", loaded.warning), NotificationIcon::Warning, 4.f)->show();
        }

        this->buildBackground();
        this->buildStage();
        this->buildControls();
        this->applySettings();
        this->refreshButtons();

        this->setKeypadEnabled(true);
        this->scheduleUpdate();

        // Start the first scene shortly after the transition finishes.
        this->runAction(CCSequence::create(
            CCDelayTime::create(0.8f),
            CallFuncExt::create([this] { this->startLine(0); }),
            nullptr
        ));
        return true;
    }

    // ------------------------------------------------------------------ building

    void TAFLayer::buildBackground() {
        auto win = CCDirector::get()->getWinSize();

        auto sky = CCLayerGradient::create({48, 30, 92, 255}, {245, 128, 72, 255});
        sky->setContentSize(win);
        this->addChild(sky, -10);

        // simple city skyline silhouettes
        float x = -10.f;
        int i = 0;
        static constexpr float heights[] = {70, 120, 90, 150, 80, 130, 60, 110, 95, 140, 75, 125};
        while (x < win.width + 10.f) {
            float w = 34.f + (i * 17 % 30);
            float h = heights[i % 12] * (win.height / 320.f);
            auto b = CCLayerColor::create({38, 24, 58, 255}, w, h);
            b->setPosition({x, 58.f});
            this->addChild(b, -9);
            // a few lit windows
            for (float wy = 12.f; wy < h - 10.f; wy += 16.f) {
                if ((i + static_cast<int>(wy)) % 3 == 0) {
                    auto lit = CCLayerColor::create({255, 200, 110, 120}, 4.f, 6.f);
                    lit->setPosition({x + w / 2.f - 2.f, 58.f + wy});
                    this->addChild(lit, -8);
                }
            }
            x += w + 4.f;
            ++i;
        }

        auto ground = CCLayerColor::create({22, 16, 34, 255}, win.width, 60.f);
        this->addChild(ground, -7);
        auto edge = CCLayerColor::create({255, 170, 90, 170}, win.width, 2.f);
        edge->setPosition({0.f, 58.f});
        this->addChild(edge, -6);

        // soft vignette so the UI reads well
        auto vignette = CCLayerGradient::create({0, 0, 0, 0}, {0, 0, 0, 110});
        vignette->setContentSize({win.width, 60.f});
        this->addChild(vignette, -5);
    }

    void TAFLayer::buildStage() {
        auto win = CCDirector::get()->getWinSize();
        if (m_stage) m_stage->removeFromParent();
        m_characters.clear();

        m_stage = CCNode::create();
        this->addChild(m_stage, 0);

        for (auto const& info : m_script.characters) {
            bool right = info.side == "right";
            auto ch = Character::create(info.rig, right);
            if (!ch) continue;
            float targetH = win.height * 0.46f;
            float scale = targetH / std::max(40.f, ch->rigHeight());
            auto holder = CCNode::create(); // keeps setFocused scaling separate from base scale
            holder->setScale(scale);
            holder->addChild(ch);
            holder->setPosition({win.width * (right ? 0.72f : 0.28f), 60.f});
            m_stage->addChild(holder, right ? 1 : 2);
            m_characters[info.id] = ch;
        }

        auto width = std::min(win.width * 0.82f, 460.f);
        if (m_subtitles) m_subtitles->removeFromParent();
        m_subtitles = SubtitleBox::create(width);
        this->addChild(m_subtitles, 10);
    }

    void TAFLayer::buildControls() {
        auto win = CCDirector::get()->getWinSize();

        auto top = CCMenu::create();
        top->setPosition({0, 0});
        top->setID("top-menu"_spr);
        this->addChild(top, 20);

        auto backSpr = CCSprite::createWithSpriteFrameName("GJ_arrow_01_001.png");
        auto back = CCMenuItemSpriteExtra::create(backSpr, this, menu_selector(TAFLayer::onBack));
        back->setPosition({25.f, win.height - 25.f});
        top->addChild(back);

        auto optSpr = CCSprite::createWithSpriteFrameName("GJ_optionsBtn_001.png");
        optSpr->setScale(0.75f);
        auto opt = CCMenuItemSpriteExtra::create(optSpr, this, menu_selector(TAFLayer::onSettings));
        opt->setPosition({win.width - 27.f, win.height - 27.f});
        top->addChild(opt);

        auto title = CCLabelBMFont::create("TAF", "goldFont.fnt");
        title->setPosition({win.width / 2.f, win.height - 20.f});
        title->setScale(1.1f);
        this->addChild(title, 20);
        title->runAction(CCRepeatForever::create(CCSequence::create(
            CCEaseSineInOut::create(CCScaleTo::create(1.4f, 1.16f)),
            CCEaseSineInOut::create(CCScaleTo::create(1.4f, 1.1f)),
            nullptr
        )));

        m_sceneTitle = CCLabelBMFont::create("The Aura Farmer", "bigFont.fnt");
        m_sceneTitle->setScale(0.35f);
        m_sceneTitle->setPosition({win.width / 2.f, win.height - 44.f});
        this->addChild(m_sceneTitle, 20);

        auto arrowL = CCSprite::createWithSpriteFrameName("navArrowBtn_001.png");
        arrowL->setFlipX(true);
        arrowL->setScale(0.35f);
        m_scenePrevBtn = CCMenuItemSpriteExtra::create(arrowL, this, menu_selector(TAFLayer::onScenePrev));
        m_scenePrevBtn->setPosition({win.width / 2.f - 95.f, win.height - 44.f});
        top->addChild(m_scenePrevBtn);
        auto arrowR = CCSprite::createWithSpriteFrameName("navArrowBtn_001.png");
        arrowR->setScale(0.35f);
        m_sceneNextBtn = CCMenuItemSpriteExtra::create(arrowR, this, menu_selector(TAFLayer::onSceneNext));
        m_sceneNextBtn->setPosition({win.width / 2.f + 95.f, win.height - 44.f});
        top->addChild(m_sceneNextBtn);

        // bottom playback bar
        auto bar = CCMenu::create();
        bar->setPosition({0, 0});
        bar->setID("controls-menu"_spr);
        this->addChild(bar, 20);
        float cy = 28.f;
        float cx = win.width / 2.f;

        auto mk = [&](char const* frame, float scale, SEL_MenuHandler sel, float x, bool flip = false) {
            auto spr = CCSprite::createWithSpriteFrameName(frame);
            spr->setScale(scale);
            spr->setFlipX(flip);
            auto btn = CCMenuItemSpriteExtra::create(spr, this, sel);
            btn->setPosition({x, cy});
            bar->addChild(btn);
            return btn;
        };
        mk("GJ_arrow_02_001.png", 0.6f, menu_selector(TAFLayer::onPrev), cx - 75.f);
        m_playBtn = mk("GJ_playBtn2_001.png", 0.45f, menu_selector(TAFLayer::onPlayPause), cx);
        m_pauseBtn = mk("GJ_pauseBtn_001.png", 0.8f, menu_selector(TAFLayer::onPlayPause), cx);
        mk("GJ_arrow_02_001.png", 0.6f, menu_selector(TAFLayer::onNext), cx + 75.f, true);
        mk("GJ_replayBtn_001.png", 0.5f, menu_selector(TAFLayer::onReplay), cx + 130.f);
        mk("GJ_updateBtn_001.png", 0.55f, menu_selector(TAFLayer::onReplayLine), cx - 130.f);

        m_counter = CCLabelBMFont::create("0 / 0", "bigFont.fnt");
        m_counter->setScale(0.35f);
        m_counter->setAnchorPoint({1.f, 0.5f});
        m_counter->setPosition({win.width - 12.f, cy});
        this->addChild(m_counter, 20);

        m_status = CCLabelBMFont::create("", "chatFont.fnt");
        m_status->setScale(0.6f);
        m_status->setAnchorPoint({0.f, 0.5f});
        m_status->setPosition({12.f, cy});
        m_status->setOpacity(170);
        this->addChild(m_status, 20);
    }

    // ------------------------------------------------------------------ settings

    void TAFLayer::applySettings() {
        auto win = CCDirector::get()->getWinSize();
        m_voice.setVolume(settings::voiceVolume());
        if (m_subtitles) {
            float y = settings::subtitlesTop() ? win.height - 92.f : 92.f;
            m_subtitles->setPosition({win.width / 2.f, y});
            m_subtitles->applySettings();
            if (!settings::showSubtitles()) m_subtitles->hide();
        }
    }

    void TAFLayer::reloadScript() {
        m_voice.stop();
        auto loaded = loadScript();
        m_script = std::move(loaded.script);
        m_sceneIdx = 0;
        this->buildStage();
        this->applySettings();
        Notification::create(
            loaded.warning.empty() ? fmt::format("TAF: loaded {} dialogue", loaded.source) : fmt::format("TAF: {}", loaded.warning),
            loaded.warning.empty() ? NotificationIcon::Success : NotificationIcon::Warning,
            2.5f
        )->show();
        this->startLine(0);
    }

    // ------------------------------------------------------------------ playback

    Scene const* TAFLayer::currentScene() const {
        if (m_script.scenes.empty()) return nullptr;
        return &m_script.scenes[std::min(m_sceneIdx, m_script.scenes.size() - 1)];
    }

    void TAFLayer::startLine(size_t index) {
        auto scene = this->currentScene();
        if (!scene || scene->lines.empty()) return;
        index = std::min(index, scene->lines.size() - 1);
        auto const& line = scene->lines[index];

        m_lineIdx = index;
        m_lineTime = 0.f;
        m_waitTimer = 0.f;
        m_lineDone = false;
        m_finished = false;
        m_playing = true;
        m_paused = false;

        auto audioPath = findAudio(line.audio);
        m_hasVoice = !audioPath.empty() && m_voice.play(audioPath, settings::voiceVolume());
        if (!m_hasVoice) m_voice.stop();

        float cuesEnd = 0.f;
        for (auto const& c : line.cues) cuesEnd = std::max(cuesEnd, c.end);

        if (m_hasVoice) m_lineDuration = std::max(m_voice.length(), cuesEnd);
        else if (line.duration > 0.f) m_lineDuration = line.duration;
        else if (cuesEnd > 0.f) m_lineDuration = cuesEnd + 0.2f;
        else m_lineDuration = estimateDuration(line.text);

        m_cues = line.cues;
        if (m_cues.empty()) m_cues.push_back({0.f, m_lineDuration, line.text});

        for (auto& [id, ch] : m_characters) {
            bool speaking = id == line.speaker;
            ch->setTalking(false);
            ch->setFocused(speaking);
            ch->playEmotion(speaking ? line.emotion : line.listener);
        }

        m_counter->setString(fmt::format("{} / {}", index + 1, scene->lines.size()).c_str());
        m_status->setString(m_hasVoice ? "voice" : (line.audio.empty() ? "" : "no audio file - subtitles only"));
        this->refreshButtons();
    }

    void TAFLayer::finishScene() {
        m_playing = false;
        m_finished = true;
        m_voice.stop();
        m_subtitles->hide();
        for (auto& [id, ch] : m_characters) {
            ch->setTalking(false);
            ch->setFocused(true);
            ch->playEmotion("neutral");
        }
        this->refreshButtons();
    }

    void TAFLayer::update(float dt) {
        if (!m_playing || m_paused) return;
        auto scene = this->currentScene();
        if (!scene) return;
        auto const& line = scene->lines[m_lineIdx];

        // The voice clip is the master clock when it is playing.
        bool voiceOn = m_hasVoice && m_voice.isActive();
        if (voiceOn) m_lineTime = std::max(m_lineTime, m_voice.position());
        else m_lineTime += dt;

        Cue const* active = nullptr;
        for (auto const& c : m_cues) {
            if (m_lineTime >= c.start && m_lineTime < c.end) { active = &c; break; }
        }

        auto speaker = m_characters.count(line.speaker) ? m_characters[line.speaker] : nullptr;
        bool talking = active && m_lineTime < m_lineDuration && (!m_hasVoice || voiceOn);
        if (speaker) speaker->setTalking(talking);

        if (active && settings::showSubtitles()) {
            auto info = m_script.character(line.speaker);
            m_subtitles->show(info ? info->name : "", info ? info->color : ccColor3B{255, 255, 255}, active->text);
        } else {
            m_subtitles->hide();
        }

        if (m_lineTime >= m_lineDuration) {
            if (!m_lineDone) {
                m_lineDone = true;
                m_waitTimer = 0.45f;
                if (speaker) speaker->setTalking(false);
            }
            if (settings::autoAdvance()) {
                m_waitTimer -= dt;
                if (m_waitTimer <= 0.f) {
                    if (m_lineIdx + 1 < scene->lines.size()) this->startLine(m_lineIdx + 1);
                    else this->finishScene();
                }
            }
        }
    }

    void TAFLayer::setPaused(bool paused) {
        m_paused = paused;
        m_voice.setPaused(paused);
        if (paused) {
            for (auto& [id, ch] : m_characters) ch->setTalking(false);
        }
        this->refreshButtons();
    }

    void TAFLayer::refreshButtons() {
        bool showPause = m_playing && !m_paused;
        if (m_playBtn) m_playBtn->setVisible(!showPause);
        if (m_pauseBtn) m_pauseBtn->setVisible(showPause);
        bool many = m_script.scenes.size() > 1;
        if (m_scenePrevBtn) m_scenePrevBtn->setVisible(many);
        if (m_sceneNextBtn) m_sceneNextBtn->setVisible(many);
        if (auto scene = this->currentScene(); scene && m_sceneTitle) {
            m_sceneTitle->setString(many ? scene->title.c_str() : "The Aura Farmer");
        }
    }

    // ------------------------------------------------------------------ buttons

    void TAFLayer::onPlayPause(CCObject*) {
        if (!m_playing) {
            this->startLine(m_finished ? 0 : m_lineIdx);
            return;
        }
        this->setPaused(!m_paused);
    }

    void TAFLayer::onNext(CCObject*) {
        auto scene = this->currentScene();
        if (!scene) return;
        if (m_lineIdx + 1 < scene->lines.size()) this->startLine(m_lineIdx + 1);
        else this->finishScene();
    }

    void TAFLayer::onPrev(CCObject*) {
        this->startLine(m_lineIdx > 0 ? m_lineIdx - 1 : 0);
    }

    void TAFLayer::onReplay(CCObject*) {
        this->startLine(0);
    }

    void TAFLayer::onReplayLine(CCObject*) {
        this->startLine(m_lineIdx);
    }

    void TAFLayer::onSceneNext(CCObject*) {
        if (m_script.scenes.empty()) return;
        m_sceneIdx = (m_sceneIdx + 1) % m_script.scenes.size();
        this->startLine(0);
    }

    void TAFLayer::onScenePrev(CCObject*) {
        if (m_script.scenes.empty()) return;
        m_sceneIdx = (m_sceneIdx + m_script.scenes.size() - 1) % m_script.scenes.size();
        this->startLine(0);
    }

    void TAFLayer::onSettings(CCObject*) {
        if (m_playing && !m_paused) this->setPaused(true);
        if (auto popup = TAFSettingsPopup::create(this)) popup->show();
    }

    void TAFLayer::onBack(CCObject*) {
        m_voice.stop();
        CCDirector::get()->popSceneWithTransition(0.5f, PopTransition::kPopTransitionFade);
    }

    void TAFLayer::keyBackClicked() {
        this->onBack(nullptr);
    }

    void TAFLayer::onExit() {
        m_voice.stop();
        CCLayer::onExit();
    }
}
