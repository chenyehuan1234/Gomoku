#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <random>
#include <unordered_map>
#include <utility>
#include <vector>

using namespace std;

// Board and protocol constants. The public I/O protocol uses 1-based
// coordinates, while all internal arrays use 0-based row/column indices.
static const int N = 38;
static const int EMPTY = 0;
static const int BLACK = 1;
static const int WHITE = 2;
static const int INF = 1000000000;
static const int DIRS[4][2] = {{1, 0}, {0, 1}, {1, 1}, {1, -1}};

// Compile the same source into two independent programs:
//   g++ ... -DBLACK_AI main.cpp -o black.exe
//   g++ ... -DWHITE_AI main.cpp -o white.exe
#ifdef BLACK_AI
static const int MY_COLOR = BLACK;
#else
static const int MY_COLOR = WHITE;
#endif

struct Move {
    int r;
    int c;
};

struct Candidate {
    Move m;
    int score;
};

static int board[N][N];
static int moveCount = 0;
// Zobrist hashing gives every board state a compact key for the
// transposition table used by alpha-beta search.
static uint64_t zobrist[N][N][3];
static uint64_t currentHash = 0;
static mt19937_64 rng(20260509ULL);
static chrono::steady_clock::time_point deadlineTime;
static bool timeoutFlag = false;

struct TTEntry {
    int depth;
    int value;
    // flag: 0 = exact value, 1 = lower bound, 2 = upper bound.
    int flag;
};

static unordered_map<uint64_t, TTEntry> transTable;

static inline bool inside(int r, int c) {
    return r >= 0 && r < N && c >= 0 && c < N;
}

static inline int opponent(int color) {
    return color == BLACK ? WHITE : BLACK;
}

static void initZobrist() {
    for (int r = 0; r < N; ++r)
        for (int c = 0; c < N; ++c)
            for (int k = 0; k < 3; ++k)
                zobrist[r][c][k] = rng();
}

static void putStone(int r, int c, int color) {
    board[r][c] = color;
    currentHash ^= zobrist[r][c][color];
    ++moveCount;
}

static void removeStone(int r, int c, int color) {
    board[r][c] = EMPTY;
    currentHash ^= zobrist[r][c][color];
    --moveCount;
}

static int countLine(int r, int c, int dr, int dc, int color) {
    int cnt = 1;
    for (int step = 1; step < N; ++step) {
        int nr = r + dr * step, nc = c + dc * step;
        if (!inside(nr, nc) || board[nr][nc] != color) break;
        ++cnt;
    }
    for (int step = 1; step < N; ++step) {
        int nr = r - dr * step, nc = c - dc * step;
        if (!inside(nr, nc) || board[nr][nc] != color) break;
        ++cnt;
    }
    return cnt;
}

static bool hasFiveAt(int r, int c, int color) {
    for (auto &d : DIRS) {
        if (countLine(r, c, d[0], d[1], color) >= 5) return true;
    }
    return false;
}

static bool hasExactFiveAt(int r, int c, int color) {
    for (auto &d : DIRS) {
        if (countLine(r, c, d[0], d[1], color) == 5) return true;
    }
    return false;
}

// Under the requested rule set, black wins only with an exact five.
// Longer black lines are forbidden unless another direction also gives an
// exact five. White has no overline restriction.
static bool winsAt(int r, int c, int color) {
    return color == BLACK ? hasExactFiveAt(r, c, color) : hasFiveAt(r, c, color);
}

static bool hasOverlineAt(int r, int c, int color) {
    for (auto &d : DIRS) {
        if (countLine(r, c, d[0], d[1], color) > 5) return true;
    }
    return false;
}

static bool createsFiveIfPlaced(int r, int c, int color) {
    if (!inside(r, c) || board[r][c] != EMPTY) return false;
    board[r][c] = color;
    bool ok = winsAt(r, c, color);
    board[r][c] = EMPTY;
    return ok;
}

static int countFourDirectionsAfterBlackMove(int r, int c) {
    int fours = 0;
    for (auto &d : DIRS) {
        bool found = false;
        // A four is counted by asking whether this line has at least one
        // follow-up point that would create an exact black five.
        for (int k = -4; k <= 4 && !found; ++k) {
            int er = r + d[0] * k, ec = c + d[1] * k;
            if (!inside(er, ec) || board[er][ec] != EMPTY) continue;
            board[er][ec] = BLACK;
            bool makesFive = countLine(er, ec, d[0], d[1], BLACK) == 5;
            board[er][ec] = EMPTY;
            if (makesFive) found = true;
        }
        if (found) ++fours;
    }
    return fours;
}

static int cellOnLine(int r, int c) {
    if (!inside(r, c)) return WHITE;
    return board[r][c];
}

static bool patternMatch(const vector<int> &line, const vector<int> &pat) {
    if (line.size() < pat.size()) return false;
    for (size_t i = 0; i + pat.size() <= line.size(); ++i) {
        bool ok = true;
        for (size_t j = 0; j < pat.size(); ++j) {
            if (pat[j] != -1 && line[i + j] != pat[j]) {
                ok = false;
                break;
            }
        }
        if (ok) return true;
    }
    return false;
}

static bool isOpenThreeDirection(int r, int c, int dr, int dc) {
    vector<int> line;
    line.reserve(11);
    for (int k = -5; k <= 5; ++k) line.push_back(cellOnLine(r + dr * k, c + dc * k));

    // These local patterns cover straight and broken open-threes around the
    // newly placed black stone. Board edges are treated as white blockers.
    static const vector<vector<int>> patterns = {
        {EMPTY, BLACK, BLACK, BLACK, EMPTY},
        {EMPTY, BLACK, BLACK, EMPTY, BLACK, EMPTY},
        {EMPTY, BLACK, EMPTY, BLACK, BLACK, EMPTY},
        {EMPTY, BLACK, BLACK, EMPTY, EMPTY, BLACK, EMPTY},
        {EMPTY, BLACK, EMPTY, BLACK, EMPTY, BLACK, EMPTY}
    };

    for (const auto &p : patterns) {
        if (patternMatch(line, p)) return true;
    }
    return false;
}

static int countOpenThreeDirectionsAfterBlackMove(int r, int c) {
    int threes = 0;
    for (auto &d : DIRS) {
        if (isOpenThreeDirection(r, c, d[0], d[1])) ++threes;
    }
    return threes;
}

static bool isForbiddenBlackMove(int r, int c) {
    if (!inside(r, c) || board[r][c] != EMPTY) return true;
    board[r][c] = BLACK;
    bool win = hasExactFiveAt(r, c, BLACK);
    bool forbidden = false;
    if (!win) {
        // The forbidden rule is evaluated only for the active black move.
        // Passive forbidden shapes are never checked after white moves.
        forbidden = hasOverlineAt(r, c, BLACK)
                 || countFourDirectionsAfterBlackMove(r, c) >= 2
                 || countOpenThreeDirectionsAfterBlackMove(r, c) >= 2;
    }
    board[r][c] = EMPTY;
    return forbidden;
}

static bool legalMove(int r, int c, int color) {
    if (!inside(r, c) || board[r][c] != EMPTY) return false;
    if (color == BLACK && isForbiddenBlackMove(r, c)) return false;
    return true;
}

static int lineWindowScore(int black, int white, int empty, int color) {
    int mine = color == BLACK ? black : white;
    int theirs = color == BLACK ? white : black;
    if (mine > 0 && theirs > 0) return 0;
    if (mine == 5) return 10000000;
    if (theirs == 5) return -10000000;
    if (mine == 4 && empty == 1) return 120000;
    if (theirs == 4 && empty == 1) return -140000;
    if (mine == 3 && empty == 2) return 7000;
    if (theirs == 3 && empty == 2) return -8500;
    if (mine == 2 && empty == 3) return 500;
    if (theirs == 2 && empty == 3) return -650;
    if (mine == 1 && empty == 4) return 20;
    if (theirs == 1 && empty == 4) return -25;
    return 0;
}

// Static evaluation scans every length-5 window. It is intentionally simple
// and fast because the search calls it many times near the leaf nodes.
static int evaluateBoard(int color) {
    int score = 0;
    for (auto &d : DIRS) {
        for (int r = 0; r < N; ++r) {
            for (int c = 0; c < N; ++c) {
                int er = r + d[0] * 4, ec = c + d[1] * 4;
                if (!inside(er, ec)) continue;
                int b = 0, w = 0, e = 0;
                for (int k = 0; k < 5; ++k) {
                    int v = board[r + d[0] * k][c + d[1] * k];
                    if (v == BLACK) ++b;
                    else if (v == WHITE) ++w;
                    else ++e;
                }
                score += lineWindowScore(b, w, e, color);
            }
        }
    }
    return score;
}

// Local move ordering score. It combines immediate attack, urgent defense,
// and a light center preference so alpha-beta sees strong moves early.
static int pointShapeScore(int r, int c, int color) {
    if (!legalMove(r, c, color)) return -INF / 4;
    int other = opponent(color);
    int score = 0;
    board[r][c] = color;
    if (winsAt(r, c, color)) score += 50000000;
    for (auto &d : DIRS) {
        int len = countLine(r, c, d[0], d[1], color);
        if (len >= 4) score += 300000;
        else if (len == 3) score += 12000;
        else if (len == 2) score += 900;
    }
    board[r][c] = EMPTY;

    board[r][c] = other;
    if (winsAt(r, c, other)) score += 45000000;
    for (auto &d : DIRS) {
        int len = countLine(r, c, d[0], d[1], other);
        if (len >= 4) score += 260000;
        else if (len == 3) score += 10000;
        else if (len == 2) score += 700;
    }
    board[r][c] = EMPTY;

    int center = abs(r - 18) + abs(c - 18);
    score += max(0, 80 - center);
    return score;
}

// Generate moves only near existing stones. On a 38x38 board this is the main
// speed win: the search tree stays focused on tactically relevant points.
static vector<Candidate> generateCandidates(int color, int limit) {
    vector<Candidate> cand;
    if (moveCount == 0) {
        cand.push_back({{18, 18}, 100000});
        return cand;
    }

    bool mark[N][N] = {};
    int radius = moveCount < 8 ? 3 : 2;
    for (int r = 0; r < N; ++r) {
        for (int c = 0; c < N; ++c) {
            if (board[r][c] == EMPTY) continue;
            for (int dr = -radius; dr <= radius; ++dr) {
                for (int dc = -radius; dc <= radius; ++dc) {
                    if (dr == 0 && dc == 0) continue;
                    int nr = r + dr, nc = c + dc;
                    if (!inside(nr, nc) || board[nr][nc] != EMPTY || mark[nr][nc]) continue;
                    mark[nr][nc] = true;
                    int sc = pointShapeScore(nr, nc, color);
                    if (sc > -INF / 8) cand.push_back({{nr, nc}, sc});
                }
            }
        }
    }

    sort(cand.begin(), cand.end(), [](const Candidate &a, const Candidate &b) {
        return a.score > b.score;
    });
    if ((int)cand.size() > limit) cand.resize(limit);
    return cand;
}

static bool timeExpired() {
    if (chrono::steady_clock::now() >= deadlineTime) {
        timeoutFlag = true;
        return true;
    }
    return false;
}

static int terminalScoreForLastMove(const Move &last, int lastColor, int rootColor, int ply) {
    if (last.r < 0) return 0;
    if (winsAt(last.r, last.c, lastColor)) {
        return lastColor == rootColor ? INF / 2 - ply : -INF / 2 + ply;
    }
    return 0;
}

static int alphaBeta(int depth, int alpha, int beta, int side, int rootColor, Move last, int lastColor, int ply) {
    if ((ply & 15) == 0 && timeExpired()) return evaluateBoard(rootColor);

    int terminal = terminalScoreForLastMove(last, lastColor, rootColor, ply);
    if (terminal != 0) return terminal;
    if (depth == 0) return evaluateBoard(rootColor);

    // Include side-to-move in the key; the same stones can have different
    // values depending on whose turn it is.
    auto it = transTable.find(currentHash ^ (uint64_t)side);
    if (it != transTable.end() && it->second.depth >= depth) {
        const TTEntry &e = it->second;
        if (e.flag == 0) return e.value;
        if (e.flag == 1) alpha = max(alpha, e.value);
        else beta = min(beta, e.value);
        if (alpha >= beta) return e.value;
    }

    int alphaOrig = alpha;
    // Balanced-speed preset: limit deeper nodes more aggressively than the
    // root while preserving enough candidates for tactical defense.
    vector<Candidate> moves = generateCandidates(side, depth >= 3 ? 14 : 20);
    if (moves.empty()) return evaluateBoard(rootColor);

    int best;
    if (side == rootColor) {
        best = -INF;
        for (const Candidate &cm : moves) {
            if (timeExpired()) break;
            int r = cm.m.r, c = cm.m.c;
            putStone(r, c, side);
            int val = alphaBeta(depth - 1, alpha, beta, opponent(side), rootColor, {r, c}, side, ply + 1);
            removeStone(r, c, side);
            if (val > best) best = val;
            if (val > alpha) alpha = val;
            if (alpha >= beta) break;
        }
    } else {
        best = INF;
        for (const Candidate &cm : moves) {
            if (timeExpired()) break;
            int r = cm.m.r, c = cm.m.c;
            putStone(r, c, side);
            int val = alphaBeta(depth - 1, alpha, beta, opponent(side), rootColor, {r, c}, side, ply + 1);
            removeStone(r, c, side);
            if (val < best) best = val;
            if (val < beta) beta = val;
            if (alpha >= beta) break;
        }
    }

    if (!timeoutFlag) {
        int flag = 0;
        if (best <= alphaOrig) flag = 2;
        else if (best >= beta) flag = 1;
        transTable[currentHash ^ (uint64_t)side] = {depth, best, flag};
    }
    return best;
}

static Move chooseMove(int color) {
    if (moveCount == 0) return {18, 18};

    // Balanced-speed preset: about 1.5 seconds per move, depth up to 4.
    deadlineTime = chrono::steady_clock::now() + chrono::milliseconds(1500);
    timeoutFlag = false;
    transTable.clear();

    vector<Candidate> rootMoves = generateCandidates(color, 30);
    if (rootMoves.empty()) {
        for (int r = 0; r < N; ++r)
            for (int c = 0; c < N; ++c)
                if (legalMove(r, c, color)) return {r, c};
        return {0, 0};
    }

    // Tactical shortcuts are checked before the full search: win immediately
    // if possible, otherwise block the opponent's immediate win.
    for (const Candidate &cm : rootMoves) {
        int r = cm.m.r, c = cm.m.c;
        putStone(r, c, color);
        bool win = winsAt(r, c, color);
        removeStone(r, c, color);
        if (win) return {r, c};
    }

    int other = opponent(color);
    for (const Candidate &cm : rootMoves) {
        int r = cm.m.r, c = cm.m.c;
        if (!legalMove(r, c, color)) continue;
        board[r][c] = other;
        bool oppWin = winsAt(r, c, other);
        board[r][c] = EMPTY;
        if (oppWin) return {r, c};
    }

    Move bestMove = rootMoves[0].m;
    int bestScore = -INF;
    for (int depth = 1; depth <= 4; ++depth) {
        if (timeExpired()) break;
        int depthBest = -INF;
        Move depthMove = bestMove;
        vector<Candidate> moves = rootMoves;
        sort(moves.begin(), moves.end(), [&](const Candidate &a, const Candidate &b) {
            if (a.m.r == bestMove.r && a.m.c == bestMove.c) return true;
            if (b.m.r == bestMove.r && b.m.c == bestMove.c) return false;
            return a.score > b.score;
        });
        for (const Candidate &cm : moves) {
            if (timeExpired()) break;
            int r = cm.m.r, c = cm.m.c;
            putStone(r, c, color);
            int val = alphaBeta(depth - 1, -INF / 2, INF / 2, opponent(color), color, {r, c}, color, 1);
            removeStone(r, c, color);
            if (timeoutFlag) break;
            if (val > depthBest) {
                depthBest = val;
                depthMove = {r, c};
            }
        }
        if (!timeoutFlag) {
            bestScore = depthBest;
            bestMove = depthMove;
        }
    }
    (void)bestScore;
    return bestMove;
}

static bool readMove(Move &m) {
    int r, c;
    if (!(cin >> r >> c)) return false;
    --r;
    --c;
    if (inside(r, c) && board[r][c] == EMPTY) {
        m = {r, c};
        return true;
    }
    m = {-1, -1};
    return true;
}

static void outputMove(const Move &m) {
    cout << (m.r + 1) << ' ' << (m.c + 1) << '\n' << flush;
}

static void clearBoard() {
    for (int r = 0; r < N; ++r) {
        for (int c = 0; c < N; ++c) board[r][c] = EMPTY;
    }
    moveCount = 0;
    currentHash = 0;
}

#ifndef SELF_TEST
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    initZobrist();

    const int opp = opponent(MY_COLOR);

#ifdef BLACK_AI
    // Black must speak first. White waits for the opponent's first coordinate.
    Move first = chooseMove(BLACK);
    putStone(first.r, first.c, BLACK);
    outputMove(first);
#endif

    Move in;
    while (readMove(in)) {
        if (in.r >= 0) putStone(in.r, in.c, opp);
        Move out = chooseMove(MY_COLOR);
        if (board[out.r][out.c] != EMPTY || !legalMove(out.r, out.c, MY_COLOR)) {
            bool found = false;
            for (int r = 0; r < N && !found; ++r) {
                for (int c = 0; c < N && !found; ++c) {
                    if (legalMove(r, c, MY_COLOR)) {
                        out = {r, c};
                        found = true;
                    }
                }
            }
        }
        putStone(out.r, out.c, MY_COLOR);
        outputMove(out);
    }
    return 0;
}
#else
// Compile with -DSELF_TEST to run small rule-focused checks without changing
// the production executables or stdout protocol.
static void requireTest(bool cond) {
    if (!cond) exit(1);
}

int main() {
    initZobrist();

    clearBoard();
    for (int c = 10; c <= 13; ++c) board[10][c] = BLACK;
    requireTest(!isForbiddenBlackMove(10, 14));

    clearBoard();
    for (int c = 10; c <= 14; ++c) board[10][c] = BLACK;
    requireTest(isForbiddenBlackMove(10, 15));

    clearBoard();
    board[10][9] = BLACK;
    board[10][11] = BLACK;
    board[9][10] = BLACK;
    board[11][10] = BLACK;
    requireTest(isForbiddenBlackMove(10, 10));

    clearBoard();
    board[10][8] = BLACK;
    board[10][9] = BLACK;
    board[10][11] = BLACK;
    board[8][10] = BLACK;
    board[9][10] = BLACK;
    board[11][10] = BLACK;
    requireTest(isForbiddenBlackMove(10, 10));

    clearBoard();
    for (int c = 10; c <= 13; ++c) board[10][c] = BLACK;
    board[8][14] = BLACK;
    board[9][14] = BLACK;
    board[11][14] = BLACK;
    requireTest(!isForbiddenBlackMove(10, 14));

    return 0;
}
#endif
