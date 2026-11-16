#pragma once
#include <Geode/Geode.hpp>
#include "Character.hpp"
#include "Dialogue.hpp"
#include "SubtitleBox.hpp"
#include "VoicePlayer.hpp"
#include <unordered_map>

namespace taf {
    // The dedicated TAF screen: stage with both characters, synced dialogue
    // playback with subtitles, and playback controls.
    class TAFLayer : public cocos2d::CCLayer {
    public:
        static TAFLayer* create();
        static cocos2d::CCScene* scene();
        static void open();

        void applySettings();  // called by the settings popup after every change
        void reloadScript();

    protected:
        bool init() override;
        void update(float dt) override;
        void keyBackClicked() override;
        void onExit() override;

        void buildBackground();
        void buildStage();
        void buildControls();

        void startLine(size_t index);
        void finishScene();
        void setPaused(bool paused);
        void refreshButtons();
        Scene const* currentScene() const;

        void onBack(cocos2d::CCObject*);
        void onSettings(cocos2d::CCObject*);
        void onPlayPause(cocos2d::CCObject*);
        void onNext(cocos2d::CCObject*);
        void onPrev(cocos2d::CCObject*);
        void onReplay(cocos2d::CCObject*);
        void onReplayLine(cocos2d::CCObject*);
        void onSceneNext(cocos2d::CCObject*);
        void onScenePrev(cocos2d::CCObject*);

        Script m_script;
        std::unordered_map<std::string, Character*> m_characters;
        cocos2d::CCNode* m_stage = nullptr;
        SubtitleBox* m_subtitles = nullptr;
        VoicePlayer m_voice;

        cocos2d::CCLabelBMFont* m_counter = nullptr;
        cocos2d::CCLabelBMFont* m_sceneTitle = nullptr;
        cocos2d::CCLabelBMFont* m_status = nullptr;
        CCMenuItemSpriteExtra* m_playBtn = nullptr;
        CCMenuItemSpriteExtra* m_pauseBtn = nullptr;
        CCMenuItemSpriteExtra* m_sceneNextBtn = nullptr;
        CCMenuItemSpriteExtra* m_scenePrevBtn = nullptr;

        size_t m_sceneIdx = 0;
        size_t m_lineIdx = 0;
        std::vector<Cue> m_cues;
        float m_lineTime = 0.f;
        float m_lineDuration = 0.f;
        float m_waitTimer = 0.f;
        bool m_hasVoice = false;
        bool m_playing = false;
        bool m_paused = false;
        bool m_lineDone = false;
        bool m_finished = false;
    };
}
