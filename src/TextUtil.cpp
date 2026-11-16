#include "TextUtil.hpp"
#include <algorithm>
#include <cctype>

namespace {
    std::u32string decode(std::string const& s) {
        std::u32string out;
        out.reserve(s.size());
        for (size_t i = 0; i < s.size();) {
            unsigned char c = static_cast<unsigned char>(s[i]);
            char32_t cp = 0;
            int extra = 0;
            if (c < 0x80) { cp = c; extra = 0; }
            else if ((c >> 5) == 0x6) { cp = c & 0x1F; extra = 1; }
            else if ((c >> 4) == 0xE) { cp = c & 0x0F; extra = 2; }
            else if ((c >> 3) == 0x1E) { cp = c & 0x07; extra = 3; }
            else { ++i; continue; } // invalid byte: skip
            bool ok = true;
            for (int k = 1; k <= extra; ++k) {
                if (i + k >= s.size()) { ok = false; break; }
                unsigned char cc = static_cast<unsigned char>(s[i + k]);
                if ((cc >> 6) != 0x2) { ok = false; break; }
                cp = (cp << 6) | (cc & 0x3F);
            }
            if (!ok) { ++i; continue; }
            out.push_back(cp);
            i += extra + 1;
        }
        return out;
    }

    std::string encode(std::u32string const& s) {
        std::string out;
        out.reserve(s.size() * 2);
        for (char32_t cp : s) {
            if (cp < 0x80) out.push_back(static_cast<char>(cp));
            else if (cp < 0x800) {
                out.push_back(static_cast<char>(0xC0 | (cp >> 6)));
                out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
            } else if (cp < 0x10000) {
                out.push_back(static_cast<char>(0xE0 | (cp >> 12)));
                out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
                out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
            } else {
                out.push_back(static_cast<char>(0xF0 | (cp >> 18)));
                out.push_back(static_cast<char>(0x80 | ((cp >> 12) & 0x3F)));
                out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
                out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
            }
        }
        return out;
    }

    bool isHebrew(char32_t c) { return c >= 0x0590 && c <= 0x05FF; }
    bool isLTR(char32_t c) { return (c < 0x80 && std::isalnum(static_cast<int>(c))) || (c >= 0xC0 && c < 0x590); }

    char32_t mirror(char32_t c) {
        switch (c) {
            case U'(': return U')'; case U')': return U'(';
            case U'[': return U']'; case U']': return U'[';
            case U'{': return U'}'; case U'}': return U'{';
            case U'<': return U'>'; case U'>': return U'<';
            default: return c;
        }
    }
}

namespace taf::text {
    bool containsHebrew(std::string const& s) {
        for (char32_t c : decode(s)) if (isHebrew(c)) return true;
        return false;
    }

    std::string toVisual(std::string const& logical) {
        auto s = decode(logical);
        bool hasHeb = std::any_of(s.begin(), s.end(), isHebrew);
        if (!hasHeb) return logical;

        // Simplified bidi for an RTL paragraph: reverse everything, mirror
        // brackets, then restore left-to-right order inside Latin/number runs
        // (a run may contain inner spaces/punctuation between LTR characters).
        std::u32string r(s.rbegin(), s.rend());
        for (auto& c : r) c = mirror(c);

        size_t i = 0;
        while (i < r.size()) {
            if (!isLTR(r[i])) { ++i; continue; }
            size_t j = i, lastLtr = i;
            while (j < r.size() && !isHebrew(r[j])) {
                if (isLTR(r[j])) lastLtr = j;
                ++j;
            }
            // run is [i, lastLtr]; un-mirror brackets inside it and reverse back
            for (size_t k = i; k <= lastLtr; ++k) r[k] = mirror(r[k]);
            std::reverse(r.begin() + i, r.begin() + lastLtr + 1);
            i = lastLtr + 1;
        }
        return encode(r);
    }

    std::string upperAscii(std::string s) {
        for (auto& ch : s) {
            if (ch >= 'a' && ch <= 'z') ch = static_cast<char>(ch - 'a' + 'A');
        }
        return s;
    }

    std::vector<std::string> wrap(
        std::string const& text, float maxWidth, std::function<float(std::string const&)> const& measure
    ) {
        std::vector<std::string> lines;
        std::string current;
        size_t pos = 0;
        auto flush = [&] {
            if (!current.empty()) lines.push_back(current);
            current.clear();
        };
        while (pos <= text.size()) {
            size_t sp = text.find_first_of(" \n", pos);
            std::string word = text.substr(pos, sp == std::string::npos ? std::string::npos : sp - pos);
            if (!word.empty()) {
                std::string candidate = current.empty() ? word : current + " " + word;
                if (!current.empty() && measure(toVisual(candidate)) > maxWidth) {
                    flush();
                    current = word;
                } else {
                    current = candidate;
                }
            }
            if (sp == std::string::npos) break;
            if (text[sp] == '\n') flush();
            pos = sp + 1;
        }
        flush();
        if (lines.empty()) lines.push_back("");
        return lines;
    }
}
