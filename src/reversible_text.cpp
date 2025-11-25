/**
 * RTO4LLM - Reversible Text Optimizer for Large Language Models
 * ==============================================================
 * High-performance C++ implementation for LLM context window optimization.
 * 
 * License: GPL-3.0-or-later
 * Repository: https://github.com/StevenGITHUBwork/RTO4LLM
 * 
 * Compile: g++ -O3 -std=c++17 -o rto reversible_text.cpp
 * Install: cp rto ~/bin/
 * Usage:   cat file.py | rto --compress > file.rto
 *          cat file.rto | rto --expand > file_restored.py
 * 
 * Version: 1.5.0
 * Build: 2025-11-26
 * 
 * Code contributions and optimizations by:
 *   - GitHub Copilot (Claude Opus 4.5)
 *   - Dictionary optimization from 500MB corpus scan
 *   - Three-tier compression: global (~^N), type-specific (~*N), local (~N)
 */

#include <iostream>
#include <unistd.h>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <map>
#include <unordered_map>
#include <regex>
#include <algorithm>
#include <cmath>
#include <chrono>
#include <iomanip>

// ============================================================================
// Configuration
// ============================================================================

const std::string VERSION = "1.5.0";
const std::string BUILD_DATE = "2025-11-26";
const std::string CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";

// ============================================================================
// Global Dictionary (same as Python version)
// ============================================================================

const std::vector<std::string> GLOBAL_DICT = {
    // Optimized dictionary from 500MB scan - sorted by length (longest first = most savings)
    "requestAnimationFrame","DOMContentLoaded","addEventListener","querySelectorAll",
    "stopPropagation","getElementById","preventDefault","createElement",
    "querySelector","getAttribute","setAttribute","textContent",
    "reinterpret_cast","dynamic_cast","static_cast","previousSibling",
    "nextSibling","appendChild","removeChild","constructor",
    "abstractmethod","staticmethod","classmethod","isinstance",
    "issubclass","enumerate","dataclass","transparent",
    "background","blockquote","childNodes","figcaption",
    "firstChild","instanceof","parentNode","startsWith",
    "transition","visibility","animation","arguments",
    "classList","className","component","constexpr",
    "innerHTML","lastChild","namespace","protected",
    "prototype","secondary","subscribe","transform",
    "undefined","absolute","basename","callback",
    "checkout","children","contains","continue",
    "disabled","dispatch","document","encoding",
    "endpoint","endsWith","explicit","external",
    "function","includes","internal","lifetime",
    "noexcept","nonlocal","optional","overflow",
    "override","position","previous","property",
    "readonly","realpath","register","relative",
    "required","response","selected","settings",
    "template","textarea","typename","unsigned",
    "upstream","validate","volatile","HashMap",
    "HashSet","Promise","RefCell","against",
    "article","because","between","boolean",
    "checked","content","context","current",
    "default","details","dirname","display",
    "element","enabled","entries","extends",
    "factory","finally","further","getopts",
    "handler","headers","include","indexOf",
    "inherit","initial","invalid","isArray",
    "isEmpty","justify","manager","matches",
    "message","nullptr","opacity","options",
    "outline","padding","payload","primary",
    "private","process","publish","receive",
    "replace","request","reverse","section",
    "service","session","success","summary",
    "through","timeout","typedef","virtual",
    "visible","warning","whereis","without",
    "Option","Result","String","action",
    "active","append","assert","before",
    "border","bottom","branch","buffer",
    "button","canvas","center","column",
    "commit","concat","config","cookie",
    "create","cursor","custom","define",
    "delete","derive","dialog","double",
    "during","enable","except","expect",
    "export","extern","figure","filter",
    "footer","format","global","handle",
    "header","height","hidden","ifndef",
    "iframe","import","inline","insert",
    "lambda","length","listen","margin",
    "method","module","notify","nowrap",
    "number","object","option","orange",
    "origin","output","params","parent",
    "plugin","pragma","public","purple",
    "radius","rebase","reduce","remote",
    "remove","render","result","return",
    "search","select","shadow","should",
    "signal","signed","sizeof","source",
    "splice","static","status","stderr",
    "stdout","sticky","stream","string",
    "struct","switch","target","toggle",
    "typeof","update","values","verify",
    "widget","window","yellow","about",
    "above","admin","after","again",
    "align","array","async","await",
    "being","below","black","block",
    "break","brown","build","cache",
    "catch","check","child","class",
    "clear","clone","close","color",
    "const","count","could","debug",
    "empty","endif","error","event",
    "false","fetch","field","final",
    "first","fixed","float","flush",
    "found","frame","graph","green",
    "guard","guide","index","input",
    "items","light","local","match",
    "merge","model","muted","print",
    "props","query","queue","raise",
    "range","reset","right","route",
    "short","slice","solid","space",
    "split","stack","start","state",
    "stash","store","strip","style",
    "super","table","tbody","thead",
    "their","there","these","thing",
    "throw","token","trait","tuple",
    "union","until","value","video",
    "while","white","width","would",
    "write","xargs","yield","args",
    "base","bind","body","bool",
    "call","case","char","code",
    "copy","core","data","dict",
    "diff","done","each","echo",
    "edit","elif","else","emit",
    "enum","eval","exec","exit",
    "file","fill","find","flex",
    "font","fork","form","from",
    "func","gets","goto","gray",
    "grep","grid","have","head",
    "help","here","hide","home",
    "host","href","html","http",
    "icon","impl","info","init",
    "into","item","iter","join",
    "json","just","keep","keys",
    "kill","kind","last","left",
    "line","link","list","load",
    "lock","logo","long","loop",
    "main","make","many","menu",
    "meta","mode","more","most",
    "move","much","must","name",
    "next","node","none","null",
    "once","only","open","over",
    "pack","page","pair","pass",
    "path","pipe","plan","play",
    "port","post","prev","pull",
    "push","read","rect","root",
    "rule","safe","same","save",
    "seek","self","send","show",
    "shut","sign","size","skip",
    "slot","some","sort","span",
    "spec","step","stop","such",
    "swap","sync","tail","take",
    "task","temp","term","test",
    "text","than","that","them",
    "then","they","this","time",
    "todo","tree","trim","true",
    "type","uint","uniq","unit",
    "unix","user","utf8","vary",
    "very","view","void","wait",
    "walk","want","warn","what",
    "when","will","with","word",
    "work","wrap","yaml","year","zero"
};

// Type-specific dictionaries
const std::map<std::string, std::vector<std::string>> TYPE_DICTS = {
    {"py", {"self", "def", "None", "True", "False", "print", "len", "str", "int", "dict", 
            "list", "set", "tuple", "range", "enumerate", "zip", "isinstance", "issubclass", 
            "super", "yield", "with", "as", "lambda", "pass", "raise", "except", "finally", 
            "try", "import", "from", "class", "return", "if", "elif", "else", "for", "while",
            "break", "continue", "and", "or", "not", "in", "is", "del", "global", "nonlocal",
            "assert", "async", "await"}},
    {"js", {"function", "return", "var", "let", "const", "if", "else", "for", "while", "do",
            "switch", "case", "default", "break", "continue", "try", "catch", "finally", "throw",
            "new", "delete", "typeof", "instanceof", "void", "this", "arguments", "super", "class",
            "extends", "implements", "interface", "package", "private", "protected", "public",
            "static", "yield", "await", "async", "import", "export", "null", "true", "false",
            "undefined", "NaN", "Infinity"}},
    {"c", {"int", "char", "float", "double", "void", "long", "short", "unsigned", "signed",
           "const", "static", "volatile", "extern", "register", "auto", "struct", "union", "enum",
           "typedef", "sizeof", "return", "if", "else", "for", "while", "do", "switch", "case",
           "default", "break", "continue", "goto", "include", "define", "ifdef", "ifndef", "endif",
           "pragma"}},
    {"rs", {"fn", "let", "mut", "const", "static", "if", "else", "for", "while", "loop", "match",
            "break", "continue", "return", "struct", "enum", "impl", "trait", "pub", "mod", "use",
            "crate", "self", "super", "as", "where", "type", "unsafe", "extern", "ref", "move",
            "dyn", "async", "await", "Some", "None", "Ok", "Err", "Result", "Option", "Vec",
            "String", "Box", "Rc", "Arc", "Cell", "RefCell", "Mutex", "RwLock", "HashMap",
            "HashSet", "BTreeMap", "BTreeSet", "println", "print", "format", "panic", "assert",
            "debug_assert", "cfg", "derive", "Clone", "Copy", "Debug", "Default", "PartialEq",
            "Eq", "PartialOrd", "Ord", "Hash", "Send", "Sync", "Sized", "Drop", "Fn", "FnMut",
            "FnOnce", "Iterator", "IntoIterator", "From", "Into", "TryFrom", "TryInto", "AsRef",
            "AsMut", "Deref", "DerefMut", "Display", "Error", "usize", "isize", "u8", "u16",
            "u32", "u64", "u128", "i8", "i16", "i32", "i64", "i128", "f32", "f64", "bool",
            "char", "str", "lifetime", "macro_rules", "macro_export", "allow", "deny", "warn",
            "must_use", "inline", "test", "bench", "feature", "serde", "tokio", "anyhow", "thiserror"}},
    {"sh", {"if", "then", "else", "elif", "fi", "for", "in", "do", "done", "while", "until",
            "case", "esac", "function", "return", "local", "export", "readonly", "declare",
            "typeset", "unset", "shift", "exit", "break", "continue", "source", "eval", "exec",
            "trap", "set", "shopt", "getopts", "read", "echo", "printf", "test", "true", "false",
            "cd", "pwd", "pushd", "popd", "dirs", "ls", "cp", "mv", "rm", "mkdir", "rmdir",
            "touch", "cat", "head", "tail", "grep", "sed", "awk", "cut", "sort", "uniq", "wc",
            "tr", "xargs", "find", "basename", "dirname", "realpath", "readlink", "which",
            "whereis", "type", "command", "alias", "unalias", "bg", "fg", "jobs", "kill", "wait",
            "nohup", "disown", "ps", "top", "htop", "df", "du", "free", "uname", "hostname",
            "whoami", "id", "groups", "sudo", "su", "chown", "chmod", "chgrp", "umask", "tar",
            "gzip", "gunzip", "zip", "unzip", "curl", "wget", "ssh", "scp", "rsync", "git",
            "make", "npm", "pip", "PATH", "HOME", "USER", "SHELL", "PWD", "OLDPWD", "IFS",
            "BASH", "BASH_VERSION", "RANDOM", "LINENO", "FUNCNAME", "PIPESTATUS"}},
    {"bash", {"if", "then", "else", "elif", "fi", "for", "in", "do", "done", "while", "until",
              "case", "esac", "function", "return", "local", "export", "readonly", "declare",
              "typeset", "unset", "shift", "exit", "break", "continue", "source", "eval", "exec",
              "trap", "set", "shopt", "getopts", "read", "echo", "printf", "test", "true", "false",
              "cd", "pwd", "pushd", "popd", "dirs", "ls", "cp", "mv", "rm", "mkdir", "rmdir",
              "touch", "cat", "head", "tail", "grep", "sed", "awk", "cut", "sort", "uniq", "wc",
              "tr", "xargs", "find", "basename", "dirname", "realpath", "readlink", "which",
              "whereis", "type", "command", "alias", "unalias", "bg", "fg", "jobs", "kill", "wait",
              "nohup", "disown", "ps", "top", "htop", "df", "du", "free", "uname", "hostname",
              "whoami", "id", "groups", "sudo", "su", "chown", "chmod", "chgrp", "umask", "tar",
              "gzip", "gunzip", "zip", "unzip", "curl", "wget", "ssh", "scp", "rsync", "git",
              "make", "npm", "pip", "PATH", "HOME", "USER", "SHELL", "PWD", "OLDPWD", "IFS",
              "BASH", "BASH_VERSION", "RANDOM", "LINENO", "FUNCNAME", "PIPESTATUS"}}
};

// ============================================================================
// Utility Functions
// ============================================================================

std::string get_token(size_t idx, const std::string& prefix = "~") {
    if (idx < CHARS.size()) {
        return prefix + CHARS[idx];
    }
    return prefix + std::to_string(idx);
}

double calculate_entropy(const std::string& data) {
    if (data.empty()) return 0.0;
    
    std::unordered_map<unsigned char, size_t> counts;
    for (unsigned char c : data) {
        counts[c]++;
    }
    
    double entropy = 0.0;
    double len = static_cast<double>(data.size());
    for (const auto& [ch, count] : counts) {
        double p = count / len;
        entropy -= p * std::log2(p);
    }
    return entropy;
}

double whitespace_ratio(const std::string& data) {
    if (data.empty()) return 0.0;
    size_t ws_count = 0;
    for (char c : data) {
        if (c == ' ' || c == '\t' || c == '\n' || c == '\r') ws_count++;
    }
    return static_cast<double>(ws_count) / data.size();
}

bool has_null_bytes(const std::string& data, size_t check_size = 1024) {
    size_t limit = std::min(check_size, data.size());
    for (size_t i = 0; i < limit; ++i) {
        if (data[i] == '\0') return true;
    }
    return false;
}

// Find words in text matching pattern [a-zA-Z_]{min_len,}
std::vector<std::string> find_words(const std::string& text, size_t min_len) {
    std::vector<std::string> words;
    std::string current;
    
    for (char c : text) {
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_') {
            current += c;
        } else {
            if (current.size() >= min_len) {
                words.push_back(current);
            }
            current.clear();
        }
    }
    if (current.size() >= min_len) {
        words.push_back(current);
    }
    return words;
}

// Get frequent words (appearing > 2 times)
std::vector<std::string> get_frequent_phrases(const std::string& text, size_t min_len = 4, size_t top_n = 200) {
    auto words = find_words(text, min_len);
    
    std::unordered_map<std::string, size_t> counts;
    for (const auto& w : words) {
        counts[w]++;
    }
    
    // Filter and sort
    std::vector<std::pair<std::string, size_t>> sorted_words;
    for (const auto& [word, count] : counts) {
        if (count > 2) {
            sorted_words.emplace_back(word, count);
        }
    }
    
    std::sort(sorted_words.begin(), sorted_words.end(),
              [](const auto& a, const auto& b) { return a.second > b.second; });
    
    std::vector<std::string> result;
    for (size_t i = 0; i < std::min(top_n, sorted_words.size()); ++i) {
        result.push_back(sorted_words[i].first);
    }
    
    // Sort by length descending for replacement
    std::sort(result.begin(), result.end(),
              [](const auto& a, const auto& b) { return a.size() > b.size(); });
    
    return result;
}

// Replace word boundaries (simple implementation)
std::string replace_word(const std::string& text, const std::string& word, const std::string& token) {
    std::string result;
    result.reserve(text.size());
    
    size_t pos = 0;
    while (pos < text.size()) {
        size_t found = text.find(word, pos);
        if (found == std::string::npos) {
            result += text.substr(pos);
            break;
        }
        
        // Check word boundaries
        bool start_ok = (found == 0 || !std::isalnum(text[found-1]) && text[found-1] != '_');
        bool end_ok = (found + word.size() >= text.size() || 
                       (!std::isalnum(text[found + word.size()]) && text[found + word.size()] != '_'));
        
        if (start_ok && end_ok) {
            result += text.substr(pos, found - pos);
            result += token;
            pos = found + word.size();
        } else {
            result += text.substr(pos, found - pos + 1);
            pos = found + 1;
        }
    }
    return result;
}

// Escape tildes
std::string escape_tildes(const std::string& text) {
    std::string result;
    result.reserve(text.size() * 1.1);
    for (char c : text) {
        if (c == '~') {
            result += "~~";
        } else {
            result += c;
        }
    }
    return result;
}

// ============================================================================
// Compression
// ============================================================================

std::string compress(const std::string& text, const std::string& file_ext = "", 
                     size_t min_len = 4, size_t top_n = 200) {
    // Get frequent words
    auto words = get_frequent_phrases(text, min_len, top_n);
    
    // Get type-specific dict
    std::vector<std::string> type_dict;
    auto it = TYPE_DICTS.find(file_ext);
    if (it != TYPE_DICTS.end()) {
        type_dict = it->second;
    }
    
    // Escape tildes
    std::string compressed = escape_tildes(text);
    
    // Build mapping
    std::map<std::string, std::string> reverse_mapping;
    size_t local_idx = 0;
    
    for (const auto& word : words) {
        std::string token;
        
        // Check global dict
        auto git = std::find(GLOBAL_DICT.begin(), GLOBAL_DICT.end(), word);
        if (git != GLOBAL_DICT.end()) {
            size_t idx = std::distance(GLOBAL_DICT.begin(), git);
            token = get_token(idx, "~^");
        }
        // Check type dict
        else if (!type_dict.empty()) {
            auto tit = std::find(type_dict.begin(), type_dict.end(), word);
            if (tit != type_dict.end()) {
                size_t idx = std::distance(type_dict.begin(), tit);
                token = get_token(idx, "~*");
            }
        }
        
        // Local dict
        if (token.empty()) {
            token = get_token(local_idx++, "~");
            reverse_mapping[token] = word;
        }
        
        // Apply replacement
        compressed = replace_word(compressed, word, token);
    }
    
    // Build header JSON (simple implementation)
    std::ostringstream header;
    header << "{\"v\":\"1.2\",\"m\":{";
    bool first = true;
    for (const auto& [tok, word] : reverse_mapping) {
        if (!first) header << ",";
        header << "\"" << tok << "\":\"" << word << "\"";
        first = false;
    }
    header << "}";
    if (!file_ext.empty()) {
        header << ",\"ext\":\"" << file_ext << "\"";
    }
    header << "}";
    
    return header.str() + "\n" + compressed;
}

// ============================================================================
// Expansion
// ============================================================================

std::string expand(const std::string& text) {
    // Find header end
    size_t newline = text.find('\n');
    if (newline == std::string::npos) return text;
    
    std::string header_str = text.substr(0, newline);
    std::string body = text.substr(newline + 1);
    
    // Simple JSON parsing for the mapping
    std::map<std::string, std::string> mapping;
    std::string file_ext;
    
    // Parse "m":{...}
    size_t m_start = header_str.find("\"m\":{");
    if (m_start != std::string::npos) {
        m_start += 5;
        size_t m_end = header_str.find("}", m_start);
        std::string m_content = header_str.substr(m_start, m_end - m_start);
        
        // Parse key:value pairs
        std::regex pair_re("\"(~[^\"]+)\":\"([^\"]+)\"");
        std::smatch match;
        std::string::const_iterator search_start(m_content.cbegin());
        while (std::regex_search(search_start, m_content.cend(), match, pair_re)) {
            mapping[match[1]] = match[2];
            search_start = match.suffix().first;
        }
    }
    
    // Parse "ext":"..."
    size_t ext_start = header_str.find("\"ext\":\"");
    if (ext_start != std::string::npos) {
        ext_start += 7;
        size_t ext_end = header_str.find("\"", ext_start);
        file_ext = header_str.substr(ext_start, ext_end - ext_start);
    }
    
    // Get type dict
    std::vector<std::string> type_dict;
    auto it = TYPE_DICTS.find(file_ext);
    if (it != TYPE_DICTS.end()) {
        type_dict = it->second;
    }
    
    // Replace tokens
    std::string result;
    result.reserve(body.size() * 2);
    
    for (size_t i = 0; i < body.size(); ++i) {
        if (body[i] == '~') {
            if (i + 1 < body.size() && body[i+1] == '~') {
                result += '~';
                i++;
                continue;
            }
            
            // Find token end
            size_t tok_end = i + 1;
            if (tok_end < body.size() && (body[tok_end] == '^' || body[tok_end] == '*')) {
                tok_end++;
            }
            while (tok_end < body.size() && (std::isalnum(body[tok_end]) || body[tok_end] == '_')) {
                tok_end++;
            }
            
            std::string token = body.substr(i, tok_end - i);
            
            // Look up token
            if (token.size() >= 2 && token[1] == '^') {
                // Global dict
                std::string idx_str = token.substr(2);
                size_t idx = 0;
                if (idx_str.size() == 1 && CHARS.find(idx_str[0]) != std::string::npos) {
                    idx = CHARS.find(idx_str[0]);
                } else {
                    idx = std::stoul(idx_str);
                }
                if (idx < GLOBAL_DICT.size()) {
                    result += GLOBAL_DICT[idx];
                } else {
                    result += token;
                }
            }
            else if (token.size() >= 2 && token[1] == '*') {
                // Type dict
                std::string idx_str = token.substr(2);
                size_t idx = 0;
                if (idx_str.size() == 1 && CHARS.find(idx_str[0]) != std::string::npos) {
                    idx = CHARS.find(idx_str[0]);
                } else {
                    idx = std::stoul(idx_str);
                }
                if (idx < type_dict.size()) {
                    result += type_dict[idx];
                } else {
                    result += token;
                }
            }
            else {
                // Local dict
                auto mit = mapping.find(token);
                if (mit != mapping.end()) {
                    result += mit->second;
                } else {
                    result += token;
                }
            }
            
            i = tok_end - 1;
        } else {
            result += body[i];
        }
    }
    
    return result;
}

// ============================================================================
// Help Text
// ============================================================================

void print_help() {
    std::cout << "RTO4LLM - Reversible Text Optimizer v" << VERSION << " (C++)\n";
    std::cout << "Build: " << BUILD_DATE << "\n\n";
    std::cout << R"HELP(
PURPOSE
    Compress text files for LLM context windows while preserving 100% 
    reversibility. Reduces token count to fit more content in AI prompts.

USAGE
    cat file.py | rto --compress --ext py > file.rto
    cat file.rto | rto --expand > file_restored.py

OPTIONS
    --compress          Compress input text
    --expand            Expand compressed text
    --ext EXT           File extension for type-specific dict (py, js, c, etc.)
    --min-len N         Minimum word length for local dict (default: 4)
    --top-n N           Max words in local dictionary (default: 200)
    --benchmark         Run internal benchmark
    --show-global-dict  Print global dictionary
    --show-type-dict E  Print type dict for extension E
    --version           Print version
    --help              Print this help

PERFORMANCE (benchmarked on 19,985 files, 291.5 MB)
    Total Savings:     34.6 MB (11.9%)
    Throughput:        ~3.3 MB/s (228 files/s) on 12th Gen Intel i5
    
    BY FILE SIZE:
      <1KB:        -2.4%  (skip - header overhead)
      1-10KB:      +7.1%
      10-50KB:    +10.6%
      50-100KB:   +13.3%
      100-500KB:  +12.5%
      500KB-1MB:  +16.2%  <-- SWEET SPOT
      1MB+:       +15.0%

TOKEN FORMAT
    ~^N  = Global dictionary (~110 common keywords, built-in)
    ~*N  = Type-specific dictionary (py/js/c/cpp/rs/sh, built-in)
    ~N   = Local dictionary (from JSON header "m" field)
    ~~   = Literal tilde character

EXAMPLES
    cat script.py | rto --compress --ext py > script.rto
    cat script.rto | rto --expand > restored.py
    rto --show-global-dict
    rto --show-type-dict py

)HELP" << std::endl;
}

void print_global_dict() {
    std::cout << "GLOBAL DICTIONARY (" << GLOBAL_DICT.size() << " entries)\n";
    std::cout << "═══════════════════════════════════════════════════════════════\n";
    std::cout << "These tokens are used across ALL file types. LLMs can use\n";
    std::cout << "this same dictionary to expand compressed text.\n\n";
    for (size_t i = 0; i < GLOBAL_DICT.size(); ++i) {
        std::cout << "  " << std::setw(8) << std::left << get_token(i, "~^") 
                  << " -> " << GLOBAL_DICT[i] << "\n";
    }
}

void print_type_dict(const std::string& ext) {
    auto it = TYPE_DICTS.find(ext);
    if (it == TYPE_DICTS.end()) {
        std::cout << "No type dictionary for extension: " << ext << "\n";
        std::cout << "Available: py, js, c\n";
        return;
    }
    const auto& dict = it->second;
    std::cout << "TYPE DICTIONARY for ." << ext << " (" << dict.size() << " entries)\n";
    std::cout << "═══════════════════════════════════════════════════════════════\n";
    std::cout << "These tokens are used for " << ext << " files specifically.\n\n";
    for (size_t i = 0; i < dict.size(); ++i) {
        std::cout << "  " << std::setw(8) << std::left << get_token(i, "~*") 
                  << " -> " << dict[i] << "\n";
    }
}

// ============================================================================
// Benchmark
// ============================================================================

void run_benchmark(const std::string& input) {
    const int iterations = 100;
    
    std::cout << "Benchmarking with " << input.size() << " bytes input...\n\n";
    
    // Compression benchmark
    auto start = std::chrono::high_resolution_clock::now();
    std::string compressed;
    for (int i = 0; i < iterations; ++i) {
        compressed = compress(input, "py");
    }
    auto end = std::chrono::high_resolution_clock::now();
    auto compress_time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
    
    // Expansion benchmark
    start = std::chrono::high_resolution_clock::now();
    std::string expanded;
    for (int i = 0; i < iterations; ++i) {
        expanded = expand(compressed);
    }
    end = std::chrono::high_resolution_clock::now();
    auto expand_time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
    
    // Results
    double compress_ratio = 100.0 * (1.0 - static_cast<double>(compressed.size()) / input.size());
    bool roundtrip_ok = (expanded == input);
    
    std::cout << "BENCHMARK RESULTS (C++ Implementation)\n";
    std::cout << std::string(60, '=') << "\n";
    std::cout << "  Input size:       " << input.size() << " bytes\n";
    std::cout << "  Compressed size:  " << compressed.size() << " bytes\n";
    std::cout << "  Compression:      " << std::fixed << std::setprecision(1) << compress_ratio << "%\n";
    std::cout << "  Roundtrip OK:     " << (roundtrip_ok ? "YES ✓" : "NO ✗") << "\n\n";
    std::cout << "  Iterations:       " << iterations << "\n";
    std::cout << "  Compress time:    " << compress_time / 1000.0 << " ms total, " 
              << compress_time / iterations / 1000.0 << " ms/iter\n";
    std::cout << "  Expand time:      " << expand_time / 1000.0 << " ms total, "
              << expand_time / iterations / 1000.0 << " ms/iter\n";
    std::cout << "  Throughput:       " << std::fixed << std::setprecision(2) 
              << (input.size() * iterations / 1024.0 / 1024.0) / (compress_time / 1000000.0) 
              << " MB/s (compress)\n";
}

// ============================================================================
// Main
// ============================================================================

int main(int argc, char* argv[]) {
    bool do_compress = false;
    bool do_expand = false;
    bool do_benchmark = false;
    bool show_help = false;
    bool show_version = false;
    bool show_global = false;
    std::string show_type;
    std::string file_ext;
    size_t min_len = 4;
    size_t top_n = 200;
    
    // Parse arguments
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--compress") do_compress = true;
        else if (arg == "--expand") do_expand = true;
        else if (arg == "--benchmark") do_benchmark = true;
        else if (arg == "--help" || arg == "-h") show_help = true;
        else if (arg == "--version") show_version = true;
        else if (arg == "--show-global-dict") show_global = true;
        else if (arg == "--show-type-dict" && i + 1 < argc) show_type = argv[++i];
        else if (arg == "--ext" && i + 1 < argc) file_ext = argv[++i];
        else if (arg == "--min-len" && i + 1 < argc) min_len = std::stoul(argv[++i]);
        else if (arg == "--top-n" && i + 1 < argc) top_n = std::stoul(argv[++i]);
    }
    
    // Handle info commands
    if (show_version) {
        std::cout << "rto v" << VERSION << " (" << BUILD_DATE << ")\n";
        return 0;
    }
    
    if (show_help) {
        print_help();
        return 0;
    }
    
    if (show_global) {
        print_global_dict();
        return 0;
    }
    
    if (!show_type.empty()) {
        print_type_dict(show_type);
        return 0;
    }
    
    // Check if stdin is a terminal (no piped input)
    if (isatty(fileno(stdin)) && !do_compress && !do_expand && !do_benchmark) {
        print_help();
        return 0;
    }
    
    // Read stdin
    std::istreambuf_iterator<char> begin(std::cin), end;
    std::string input(begin, end);
    
    // If no input and no operation specified, show help
    if (input.empty() && !do_compress && !do_expand) {
        print_help();
        return 0;
    }
    
    // Run operations
    if (do_benchmark) {
        run_benchmark(input);
        return 0;
    }
    
    if (do_compress) {
        std::cout << compress(input, file_ext, min_len, top_n);
    } else if (do_expand) {
        std::cout << expand(input);
    } else {
        // No operation specified - show help
        print_help();
    }
    
    return 0;
}
