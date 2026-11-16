#pragma once
#include <string>
#include <vector>
#include <functional>

namespace taf::text {
    // Converts a logical-order line into the left-to-right visual order that
    // cocos bitmap labels draw. Lines without Hebrew are returned unchanged.
    std::string toVisual(std::string const& logical);

    // ASCII-only uppercase (Hebrew has no case, so it is left alone).
    std::string upperAscii(std::string s);

    // Greedy word wrap in logical order. `measure` returns the drawn width of a string.
    std::vector<std::string> wrap(
        std::string const& text, float maxWidth, std::function<float(std::string const&)> const& measure
    );

    bool containsHebrew(std::string const& s);
}
