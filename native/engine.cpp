// Protocol fixture only. These are synthetic rules, NOT Langrisser combat rules.
#include <algorithm>
#include <array>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <limits>
#include <queue>
#include <stdexcept>
#include <string>
#include <vector>

struct Unit {
    int id, owner, x, y, hp, max_hp, attack, defense, movement, range, acted;
};
struct State {
    int width, height, round_limit, round, active_player, outcome;
    std::vector<int> cells;
    std::vector<Unit> units;
};
struct Action {
    int unit, x, y, target;
    std::vector<int> path;
};

void require(bool ok, const char* message) {
    if (!ok) throw std::runtime_error(message);
}

State read_state() {
    State s{};
    require(static_cast<bool>(std::cin >> s.width >> s.height >> s.round_limit
            >> s.round >> s.active_player >> s.outcome), "invalid state header");
    require(s.width >= 2 && s.width <= 32 && s.height >= 2 && s.height <= 32,
            "map dimensions outside fixture limits");
    require(s.round_limit >= 1 && s.round_limit <= 100 && s.round >= 1
            && s.round <= s.round_limit && s.active_player >= 0
            && s.active_player <= 1 && s.outcome >= -2 && s.outcome <= 1,
            "invalid round or player");
    s.cells.resize(static_cast<std::size_t>(s.width * s.height));
    for (auto& cost : s.cells) {
        require(static_cast<bool>(std::cin >> cost) && cost >= 0 && cost <= 9,
                "invalid terrain cost");
    }
    int count = 0;
    require(static_cast<bool>(std::cin >> count) && count >= 2 && count <= 10,
            "invalid unit count");
    for (int i = 0; i < count; ++i) {
        Unit u{};
        require(static_cast<bool>(std::cin >> u.id >> u.owner >> u.x >> u.y
                >> u.hp >> u.max_hp >> u.attack >> u.defense >> u.movement
                >> u.range >> u.acted), "invalid unit record");
        require(u.id >= 0 && u.id < 100 && u.owner >= 0 && u.owner <= 1
                && u.x >= 0 && u.x < s.width && u.y >= 0 && u.y < s.height
                && u.max_hp > 0 && u.max_hp <= 10000 && u.hp >= 0
                && u.hp <= u.max_hp && u.attack > 0 && u.attack <= 10000
                && u.defense >= 0 && u.defense <= 10000 && u.movement >= 0
                && u.movement <= 10 && u.range >= 1 && u.range <= 10
                && (u.acted == 0 || u.acted == 1), "unit outside fixture limits");
        require(s.cells[static_cast<std::size_t>(u.y * s.width + u.x)] > 0,
                "unit on impassable tile");
        for (const auto& other : s.units) {
            require(other.id != u.id, "duplicate unit id");
            require(!(other.hp > 0 && u.hp > 0 && other.x == u.x && other.y == u.y),
                    "overlapping living units");
        }
        s.units.push_back(u);
    }
    return s;
}

std::vector<Action> legal_actions(const State& s) {
    std::vector<Action> actions;
    if (s.outcome != -2) return actions;
    const int count = s.width * s.height;
    for (const auto& u : s.units) {
        if (u.hp <= 0 || u.acted || u.owner != s.active_player) continue;
        std::vector<bool> occupied(static_cast<std::size_t>(count), false);
        for (const auto& other : s.units) {
            if (other.hp > 0 && other.id != u.id)
                occupied[static_cast<std::size_t>(other.y * s.width + other.x)] = true;
        }
        std::vector<int> dist(static_cast<std::size_t>(count), 1000000);
        std::vector<int> prev(static_cast<std::size_t>(count), -1);
        using Entry = std::pair<int, int>;
        std::priority_queue<Entry, std::vector<Entry>, std::greater<Entry>> queue;
        const int start = u.y * s.width + u.x;
        dist[static_cast<std::size_t>(start)] = 0;
        queue.emplace(0, start);
        while (!queue.empty()) {
            auto [cost, pos] = queue.top();
            queue.pop();
            if (cost != dist[static_cast<std::size_t>(pos)]) continue;
            const int x = pos % s.width, y = pos / s.width;
            for (auto [dx, dy] : std::array<std::pair<int, int>, 4>{
                    {{0, -1}, {-1, 0}, {1, 0}, {0, 1}}}) {
                const int nx = x + dx, ny = y + dy;
                if (nx < 0 || nx >= s.width || ny < 0 || ny >= s.height) continue;
                const auto next = static_cast<std::size_t>(ny * s.width + nx);
                const int new_cost = cost + s.cells[next];
                if (s.cells[next] == 0 || occupied[next] || new_cost > u.movement
                        || new_cost >= dist[next]) continue;
                dist[next] = new_cost;
                prev[next] = pos;
                queue.emplace(new_cost, static_cast<int>(next));
            }
        }
        for (int pos = 0; pos < count; ++pos) {
            if (dist[static_cast<std::size_t>(pos)] > u.movement) continue;
            std::vector<int> path;
            for (int p = pos; p != -1; p = prev[static_cast<std::size_t>(p)])
                path.push_back(p);
            std::reverse(path.begin(), path.end());
            const int x = pos % s.width, y = pos / s.width;
            actions.push_back({u.id, x, y, -1, path});
            for (const auto& enemy : s.units) {
                if (enemy.hp > 0 && enemy.owner != u.owner
                        && std::abs(x - enemy.x) + std::abs(y - enemy.y) <= u.range)
                    actions.push_back({u.id, x, y, enemy.id, path});
            }
        }
    }
    return actions;
}

void write_unit(const Unit& u) {
    std::cout << "{\"id\":" << u.id << ",\"owner\":" << u.owner
        << ",\"x\":" << u.x << ",\"y\":" << u.y << ",\"hp\":" << u.hp
        << ",\"max_hp\":" << u.max_hp << ",\"attack\":" << u.attack
        << ",\"defense\":" << u.defense << ",\"movement\":" << u.movement
        << ",\"range\":" << u.range << ",\"acted\":" << u.acted << '}';
}

void write_state(const State& s) {
    std::cout << "{\"round\":" << s.round << ",\"active_player\":"
        << s.active_player << ",\"outcome\":" << s.outcome << ",\"units\":[";
    for (std::size_t i = 0; i < s.units.size(); ++i) {
        if (i) std::cout << ',';
        write_unit(s.units[i]);
    }
    std::cout << "]}";
}

void write_action(const Action& a, int width) {
    std::cout << "{\"kind\":\"" << (a.target < 0 ? "wait" : "attack")
        << "\",\"unit\":" << a.unit << ",\"to\":[" << a.x << ',' << a.y
        << "],\"target\":" << a.target << ",\"path\":[";
    for (std::size_t i = 0; i < a.path.size(); ++i) {
        if (i) std::cout << ',';
        std::cout << '[' << a.path[i] % width << ',' << a.path[i] / width << ']';
    }
    std::cout << "]}";
}

void apply(State& s, const Action& a) {
    auto actor = std::find_if(s.units.begin(), s.units.end(),
                            [&](const Unit& u) { return u.id == a.unit; });
    actor->x = a.x;
    actor->y = a.y;
    std::cout << "{\"events\":[{\"type\":\"move\",\"unit\":" << a.unit
              << ",\"to\":[" << a.x << ',' << a.y << "]}";
    if (a.target >= 0) {
        auto target = std::find_if(s.units.begin(), s.units.end(),
                                  [&](const Unit& u) { return u.id == a.target; });
        const int damage = std::min(target->hp, std::max(1, actor->attack - target->defense));
        target->hp -= damage;
        std::cout << ",{\"type\":\"fixture_damage\",\"source\":" << a.unit
                  << ",\"target\":" << a.target << ",\"amount\":" << damage << '}';
    }
    actor->acted = 1;
    std::array<bool, 2> alive{}, ready{};
    for (const auto& u : s.units) {
        if (u.hp > 0) {
            alive[static_cast<std::size_t>(u.owner)] = true;
            if (!u.acted) ready[static_cast<std::size_t>(u.owner)] = true;
        }
    }
    if (!alive[0] || !alive[1]) {
        s.outcome = alive[0] ? 0 : 1;
    } else if (!ready[0] && !ready[1]) {
        if (s.round == s.round_limit) {
            s.outcome = -1;
        } else {
            ++s.round;
            for (auto& u : s.units) u.acted = 0;
            s.active_player = 0; // Explicit synthetic fixture rule.
            std::cout << ",{\"type\":\"round_start\",\"round\":" << s.round << '}';
        }
    } else if (ready[static_cast<std::size_t>(1 - s.active_player)]) {
        s.active_player = 1 - s.active_player;
    }
    if (s.outcome != -2)
        std::cout << ",{\"type\":\"match_finished\",\"outcome\":" << s.outcome << '}';
    std::cout << "],\"state\":";
    write_state(s);
    std::cout << "}\n";
}

int main(int argc, char** argv) {
    try {
        require(argc == 2, "expected legal or apply command");
        const std::string command = argv[1];
        require(command == "legal" || command == "apply", "unknown command");
        State s = read_state();
        const auto legal = legal_actions(s);
        if (command == "legal") {
            std::cout << '[';
            for (std::size_t i = 0; i < legal.size(); ++i) {
                if (i) std::cout << ',';
                write_action(legal[i], s.width);
            }
            std::cout << "]\n";
        } else {
            Action requested{};
            require(static_cast<bool>(std::cin >> requested.unit >> requested.x
                    >> requested.y >> requested.target), "invalid action record");
            auto found = std::find_if(legal.begin(), legal.end(), [&](const Action& a) {
                return a.unit == requested.unit && a.x == requested.x
                    && a.y == requested.y && a.target == requested.target;
            });
            require(found != legal.end(), "illegal action");
            apply(s, *found);
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 2;
    }
}
