import os
import queue
import random
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from tkinter import filedialog, messagebox, ttk


BOARD_SIZE = 38
EMPTY = 0
BLACK = 1
WHITE = 2
BLACK_NAME = "黑方"
WHITE_NAME = "白方"
DIRS = ((1, 0), (0, 1), (1, 1), (1, -1))


def color_name(color):
    return BLACK_NAME if color == BLACK else WHITE_NAME


def other_color(color):
    return WHITE if color == BLACK else BLACK


def to_external(r, c):
    return r + 1, c + 1


@dataclass
class MoveRecord:
    color: int
    row: int
    col: int
    source: str
    raw: str = ""
    random_first: bool = False
    timestamp: float = 0.0


class BoardRules:
    def __init__(self):
        self.board = [[EMPTY for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.move_count = 0

    def reset(self):
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                self.board[r][c] = EMPTY
        self.move_count = 0

    def copy_board(self):
        return [row[:] for row in self.board]

    def inside(self, r, c):
        return 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE

    def cell_on_line(self, r, c):
        if not self.inside(r, c):
            return WHITE
        return self.board[r][c]

    def is_empty(self, r, c):
        return self.inside(r, c) and self.board[r][c] == EMPTY

    def put(self, r, c, color):
        self.board[r][c] = color
        self.move_count += 1

    def remove(self, r, c):
        self.board[r][c] = EMPTY
        self.move_count -= 1

    def count_line(self, r, c, dr, dc, color):
        count = 1
        step = 1
        while True:
            nr, nc = r + dr * step, c + dc * step
            if not self.inside(nr, nc) or self.board[nr][nc] != color:
                break
            count += 1
            step += 1
        step = 1
        while True:
            nr, nc = r - dr * step, c - dc * step
            if not self.inside(nr, nc) or self.board[nr][nc] != color:
                break
            count += 1
            step += 1
        return count

    def has_exact_five_at(self, r, c, color):
        return any(self.count_line(r, c, dr, dc, color) == 5 for dr, dc in DIRS)

    def has_five_or_more_at(self, r, c, color):
        return any(self.count_line(r, c, dr, dc, color) >= 5 for dr, dc in DIRS)

    def has_overline_at(self, r, c, color):
        return any(self.count_line(r, c, dr, dc, color) > 5 for dr, dc in DIRS)

    def wins_at(self, r, c, color):
        if color == BLACK:
            return self.has_exact_five_at(r, c, color)
        return self.has_five_or_more_at(r, c, color)

    def creates_exact_five_in_direction(self, r, c, dr, dc):
        self.board[r][c] = BLACK
        ok = self.count_line(r, c, dr, dc, BLACK) == 5
        self.board[r][c] = EMPTY
        return ok

    def count_four_directions_after_black_move(self, r, c):
        fours = 0
        for dr, dc in DIRS:
            found = False
            for k in range(-4, 5):
                er, ec = r + dr * k, c + dc * k
                if not self.inside(er, ec) or self.board[er][ec] != EMPTY:
                    continue
                if self.creates_exact_five_in_direction(er, ec, dr, dc):
                    found = True
                    break
            if found:
                fours += 1
        return fours

    def pattern_match(self, line, pattern):
        if len(line) < len(pattern):
            return False
        for start in range(len(line) - len(pattern) + 1):
            ok = True
            for i, value in enumerate(pattern):
                if value != -1 and line[start + i] != value:
                    ok = False
                    break
            if ok:
                return True
        return False

    def is_open_three_direction(self, r, c, dr, dc):
        line = [self.cell_on_line(r + dr * k, c + dc * k) for k in range(-5, 6)]
        patterns = (
            (EMPTY, BLACK, BLACK, BLACK, EMPTY),
            (EMPTY, BLACK, BLACK, EMPTY, BLACK, EMPTY),
            (EMPTY, BLACK, EMPTY, BLACK, BLACK, EMPTY),
            (EMPTY, BLACK, BLACK, EMPTY, EMPTY, BLACK, EMPTY),
            (EMPTY, BLACK, EMPTY, BLACK, EMPTY, BLACK, EMPTY),
        )
        return any(self.pattern_match(line, pat) for pat in patterns)

    def count_open_three_directions_after_black_move(self, r, c):
        return sum(1 for dr, dc in DIRS if self.is_open_three_direction(r, c, dr, dc))

    def forbidden_reason_for_black_move(self, r, c):
        if not self.inside(r, c):
            return "越界"
        if self.board[r][c] != EMPTY:
            return "已有棋子"
        self.board[r][c] = BLACK
        try:
            if self.has_exact_five_at(r, c, BLACK):
                return None
            if self.has_overline_at(r, c, BLACK):
                return "长连禁手"
            fours = self.count_four_directions_after_black_move(r, c)
            if fours >= 2:
                return "四四禁手"
            threes = self.count_open_three_directions_after_black_move(r, c)
            if threes >= 2:
                return "三三禁手"
            return None
        finally:
            self.board[r][c] = EMPTY

    def validate_move(self, r, c, color):
        if not self.inside(r, c):
            return False, "越界"
        if self.board[r][c] != EMPTY:
            return False, "已有棋子"
        if color == BLACK:
            reason = self.forbidden_reason_for_black_move(r, c)
            if reason:
                return False, reason
        return True, ""


class EngineProcess:
    def __init__(self, path, label, log_callback):
        self.path = path
        self.label = label
        self.log_callback = log_callback
        self.process = None
        self.stdout_queue = queue.Queue()
        self.stderr_queue = queue.Queue()
        self.alive = False

    def start(self):
        if not self.path:
            raise ValueError(f"{self.label} 没有选择 exe")
        if not os.path.exists(self.path):
            raise FileNotFoundError(self.path)
        creationflags = 0
        if sys.platform.startswith("win"):
            creationflags = subprocess.CREATE_NO_WINDOW
        self.process = subprocess.Popen(
            [self.path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            cwd=os.path.dirname(self.path) or None,
            creationflags=creationflags,
        )
        self.alive = True
        threading.Thread(target=self._reader, args=(self.process.stdout, self.stdout_queue), daemon=True).start()
        threading.Thread(target=self._reader, args=(self.process.stderr, self.stderr_queue), daemon=True).start()
        self.log_callback(f"{self.label} 已启动：{self.path}")

    def _reader(self, stream, target_queue):
        try:
            while True:
                chunk = stream.readline()
                if chunk == "":
                    break
                target_queue.put(chunk)
        except Exception as exc:
            target_queue.put(f"[读取错误] {exc}\n")

    def write_move(self, r, c):
        if not self.process or not self.process.stdin or self.process.poll() is not None:
            raise RuntimeError(f"{self.label} 进程已退出")
        er, ec = to_external(r, c)
        self.process.stdin.write(f"{er} {ec}\n")
        self.process.stdin.flush()
        self.log_callback(f"发送给{self.label}：{er} {ec}")

    def drain_stdout(self):
        return self._drain(self.stdout_queue)

    def drain_stderr(self):
        return self._drain(self.stderr_queue)

    def _drain(self, q):
        chunks = []
        while True:
            try:
                chunks.append(q.get_nowait())
            except queue.Empty:
                break
        return "".join(chunks)

    def poll(self):
        if not self.process:
            return None
        return self.process.poll()

    def stop(self):
        self.alive = False
        if not self.process:
            return
        try:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    self.process.kill()
        except Exception:
            pass
        self.process = None


class GameController:
    def __init__(self, app):
        self.app = app
        self.rules = BoardRules()
        self.engines = {BLACK: None, WHITE: None}
        self.players = {BLACK: "human", WHITE: "human"}
        self.current = BLACK
        self.running = False
        self.game_over = False
        self.reviewing = False
        self.waiting_engine = None
        self.wait_started = 0.0
        self.wait_timeout = 10.0
        self.output_buffer = ""
        self.move_history = []
        self.random = random.Random()
        self.stats = {
            "total": 0,
            "black_win": 0,
            "white_win": 0,
            "draw": 0,
            "black_forbidden_loss": 0,
            "black_illegal_timeout_loss": 0,
            "white_illegal_timeout_loss": 0,
        }

    def reset_stats(self):
        for key in self.stats:
            self.stats[key] = 0
        self.app.update_stats()
        self.app.log("累计比分已重置")

    def start_game(self, mode, black_path, white_path):
        self.stop_game(log=False)
        self.rules.reset()
        self.current = BLACK
        self.running = True
        self.game_over = False
        self.reviewing = False
        self.waiting_engine = None
        self.output_buffer = ""
        self.move_history = []
        self.app.set_replay_enabled(False, 0)
        self.app.draw_board()
        self.app.set_status("对局开始，黑方先手")

        if mode == "exe_exe":
            self.players = {BLACK: "engine", WHITE: "engine"}
        elif mode == "human_black":
            self.players = {BLACK: "human", WHITE: "engine"}
        elif mode == "human_white":
            self.players = {BLACK: "engine", WHITE: "human"}
        else:
            self.players = {BLACK: "human", WHITE: "human"}

        try:
            if self.players[BLACK] == "engine":
                self.engines[BLACK] = EngineProcess(black_path, "黑方 exe", self.app.log)
                self.engines[BLACK].start()
            if self.players[WHITE] == "engine":
                self.engines[WHITE] = EngineProcess(white_path, "白方 exe", self.app.log)
                self.engines[WHITE].start()
        except Exception as exc:
            self.app.log(f"启动失败：{exc}")
            messagebox.showerror("启动失败", str(exc))
            self.stop_game(log=False)
            return

        self.advance_turn()

    def stop_game(self, log=True):
        for color in (BLACK, WHITE):
            if self.engines.get(color):
                self.engines[color].stop()
                self.engines[color] = None
        self.running = False
        self.waiting_engine = None
        if log:
            self.app.log("本盘已停止")
            self.app.set_status("已停止")

    def next_game(self, mode, black_path, white_path):
        self.start_game(mode, black_path, white_path)

    def advance_turn(self):
        if not self.running or self.game_over:
            return
        if self.players[self.current] == "human":
            self.waiting_engine = None
            self.app.set_status(f"轮到{color_name(self.current)}，请点击棋盘落子")
            return
        timeout = 5.0 if self.current == BLACK and self.rules.move_count == 0 else 10.0
        self.wait_for_engine(self.current, timeout)

    def wait_for_engine(self, color, timeout):
        self.waiting_engine = color
        self.wait_started = time.monotonic()
        self.wait_timeout = timeout
        self.output_buffer = ""
        self.app.set_status(f"等待{color_name(color)} exe 输出，超时 {timeout:.0f}s")

    def tick(self):
        if not self.running or self.game_over:
            return
        for color in (BLACK, WHITE):
            engine = self.engines.get(color)
            if not engine:
                continue
            err = engine.drain_stderr()
            if err.strip():
                self.app.log(f"{color_name(color)} stderr：{err.strip()}")
            if engine.poll() is not None and self.waiting_engine == color:
                out = engine.drain_stdout()
                if out:
                    self.output_buffer += out
                    parsed = self.parse_move(self.output_buffer)
                    if parsed:
                        self.apply_move(parsed[0], parsed[1], color, "exe", raw=self.output_buffer)
                        return
                self.finish_game(other_color(color), f"{color_name(color)} exe 已退出")
                return

        if self.waiting_engine:
            engine = self.engines.get(self.waiting_engine)
            if not engine:
                return
            out = engine.drain_stdout()
            if out:
                self.output_buffer += out
                self.app.log(f"{color_name(self.waiting_engine)} stdout：{out.strip()}")
                parsed = self.parse_move(self.output_buffer)
                if parsed:
                    self.apply_move(parsed[0], parsed[1], self.waiting_engine, "exe", raw=self.output_buffer)
                    return

            elapsed = time.monotonic() - self.wait_started
            left = max(0.0, self.wait_timeout - elapsed)
            self.app.set_status(f"等待{color_name(self.waiting_engine)} exe 输出，剩余 {left:.1f}s")
            if elapsed >= self.wait_timeout:
                self.handle_timeout(self.waiting_engine)

    def parse_move(self, text):
        nums = [int(x) for x in re.findall(r"-?\d+", text)]
        for i in range(0, len(nums) - 1):
            row, col = nums[i], nums[i + 1]
            r, c = row - 1, col - 1
            if 1 <= row <= BOARD_SIZE and 1 <= col <= BOARD_SIZE and self.rules.is_empty(r, c):
                return r, c
        return None

    def handle_timeout(self, color):
        if color == BLACK and self.rules.move_count == 0:
            choices = []
            for r in range(17, 20):
                for c in range(17, 20):
                    if self.rules.is_empty(r, c):
                        choices.append((r, c))
            if choices:
                r, c = self.random.choice(choices)
                er, ec = to_external(r, c)
                self.app.log(f"黑方首手 5 秒超时，裁判随机中心 9 格落子：{er} {ec}")
                self.apply_move(r, c, BLACK, "裁判随机", random_first=True)
                return
        self.finish_game(other_color(color), f"{color_name(color)} 超时")

    def human_move(self, r, c):
        if not self.running or self.game_over:
            return
        if self.players[self.current] != "human":
            self.app.log("现在不是用户回合")
            return
        self.apply_move(r, c, self.current, "用户")

    def apply_move(self, r, c, color, source, raw="", random_first=False):
        if not self.running or self.game_over:
            return
        if color != self.current:
            self.app.log(f"忽略非当前回合落子：{color_name(color)}")
            return
        er, ec = to_external(r, c)
        ok, reason = self.rules.validate_move(r, c, color)
        if not ok:
            if color == BLACK and reason in ("长连禁手", "三三禁手", "四四禁手"):
                self.finish_game(WHITE, f"黑方落子 {er} {ec} 犯规：{reason}", forbidden_loss=True)
            else:
                self.finish_game(other_color(color), f"{color_name(color)} 非法落子 {er} {ec}：{reason}")
            return

        self.rules.put(r, c, color)
        self.move_history.append(MoveRecord(color, r, c, source, raw, random_first, time.time()))
        self.app.log(f"{color_name(color)}落子：{er} {ec}（{source}）")
        self.app.draw_board()
        self.app.update_replay_range(len(self.move_history))

        if self.rules.wins_at(r, c, color):
            self.finish_game(color, f"{color_name(color)}在 {er} {ec} 获胜")
            return
        if self.rules.move_count >= BOARD_SIZE * BOARD_SIZE:
            self.finish_draw("棋盘已满，平局")
            return

        next_color = other_color(color)
        if self.players[next_color] == "engine":
            engine = self.engines.get(next_color)
            if engine:
                try:
                    engine.write_move(r, c)
                except Exception as exc:
                    self.finish_game(color, f"{color_name(next_color)} 接收输入失败：{exc}")
                    return

        self.current = next_color
        self.waiting_engine = None
        self.advance_turn()

    def finish_draw(self, reason):
        if self.game_over:
            return
        self.game_over = True
        self.running = False
        self.stats["total"] += 1
        self.stats["draw"] += 1
        self.app.log(f"本盘结束：{reason}")
        self.app.set_status(reason)
        self.app.update_stats()
        self.app.set_replay_enabled(True, len(self.move_history))
        self.stop_engines_only()

    def finish_game(self, winner, reason, forbidden_loss=False):
        if self.game_over:
            return
        self.game_over = True
        self.running = False
        self.stats["total"] += 1
        if winner == BLACK:
            self.stats["black_win"] += 1
        else:
            self.stats["white_win"] += 1
        if forbidden_loss:
            self.stats["black_forbidden_loss"] += 1
        elif "超时" in reason or "非法落子" in reason or "已退出" in reason or "接收输入失败" in reason:
            loser = other_color(winner)
            if loser == BLACK:
                self.stats["black_illegal_timeout_loss"] += 1
            else:
                self.stats["white_illegal_timeout_loss"] += 1
        text = f"本盘结束：{reason}，{color_name(winner)}胜"
        self.app.log(text)
        self.app.set_status(text)
        self.app.update_stats()
        self.app.set_replay_enabled(True, len(self.move_history))
        self.stop_engines_only()

    def stop_engines_only(self):
        for color in (BLACK, WHITE):
            if self.engines.get(color):
                self.engines[color].stop()
                self.engines[color] = None
        self.waiting_engine = None

    def board_for_replay(self, count):
        board = [[EMPTY for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        for rec in self.move_history[:count]:
            board[rec.row][rec.col] = rec.color
        return board


class GomokuApp:
    def __init__(self, root):
        self.root = root
        self.root.title("五子棋裁判")
        self.controller = GameController(self)

        self.mode_var = tk.StringVar(value="exe_exe")
        self.black_path_var = tk.StringVar(value=os.path.abspath("black.exe") if os.path.exists("black.exe") else "")
        self.white_path_var = tk.StringVar(value=os.path.abspath("white.exe") if os.path.exists("white.exe") else "")
        self.status_var = tk.StringVar(value="请选择模式并开始")
        self.replay_var = tk.IntVar(value=0)
        self.replay_active = False
        self.display_board = self.controller.rules.board

        self.margin = 24
        self.cell = 17
        self.canvas_size = self.margin * 2 + self.cell * (BOARD_SIZE - 1)

        self.build_ui()
        self.draw_board()
        self.update_stats()
        self.root.after(100, self.periodic_tick)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def build_ui(self):
        outer = ttk.Frame(self.root, padding=8)
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=0)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(1, weight=1)

        top = ttk.Frame(outer)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        top.columnconfigure(4, weight=1)

        ttk.Label(top, text="模式").grid(row=0, column=0, padx=(0, 4))
        mode_box = ttk.Combobox(
            top,
            textvariable=self.mode_var,
            state="readonly",
            width=18,
            values=("exe_exe", "human_black", "human_white", "human_human"),
        )
        mode_box.grid(row=0, column=1, padx=(0, 8))
        mode_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh_mode_labels())

        self.mode_hint = ttk.Label(top, text="")
        self.mode_hint.grid(row=0, column=2, sticky="w")

        ttk.Button(top, text="开始本盘", command=self.start_game).grid(row=0, column=5, padx=4)
        ttk.Button(top, text="停止本盘", command=self.stop_game).grid(row=0, column=6, padx=4)
        ttk.Button(top, text="下一盘", command=self.next_game).grid(row=0, column=7, padx=4)
        ttk.Button(top, text="重置比分", command=self.controller.reset_stats).grid(row=0, column=8, padx=4)

        left = ttk.Frame(outer)
        left.grid(row=1, column=0, sticky="nsw")

        self.canvas = tk.Canvas(
            left,
            width=self.canvas_size,
            height=self.canvas_size,
            bg="#d9a94f",
            highlightthickness=1,
            highlightbackground="#77551d",
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Button-1>", self.on_canvas_click)

        replay = ttk.Frame(left)
        replay.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        replay.columnconfigure(1, weight=1)
        ttk.Label(replay, text="复盘").grid(row=0, column=0, padx=(0, 6))
        self.replay_scale = ttk.Scale(replay, from_=0, to=0, orient="horizontal", command=self.on_replay_change)
        self.replay_scale.grid(row=0, column=1, sticky="ew")
        self.replay_label = ttk.Label(replay, text="0/0", width=8)
        self.replay_label.grid(row=0, column=2, padx=(6, 0))

        right = ttk.Frame(outer)
        right.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        right.columnconfigure(1, weight=1)
        right.rowconfigure(6, weight=1)

        ttk.Label(right, text="黑方 exe").grid(row=0, column=0, sticky="w")
        ttk.Entry(right, textvariable=self.black_path_var).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(right, text="选择", command=lambda: self.choose_exe(self.black_path_var)).grid(row=0, column=2)

        ttk.Label(right, text="白方 exe").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(right, textvariable=self.white_path_var).grid(row=1, column=1, sticky="ew", padx=4, pady=(4, 0))
        ttk.Button(right, text="选择", command=lambda: self.choose_exe(self.white_path_var)).grid(row=1, column=2, pady=(4, 0))

        ttk.Label(right, text="状态").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Label(right, textvariable=self.status_var, wraplength=430).grid(
            row=2, column=1, columnspan=2, sticky="ew", pady=(8, 0)
        )

        stats_frame = ttk.LabelFrame(right, text="累计比分")
        stats_frame.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        stats_frame.columnconfigure(0, weight=1)
        self.stats_var = tk.StringVar()
        ttk.Label(stats_frame, textvariable=self.stats_var, justify="left").grid(row=0, column=0, sticky="w", padx=8, pady=6)

        ttk.Label(right, text="日志").grid(row=5, column=0, sticky="w", pady=(8, 0))
        log_frame = ttk.Frame(right)
        log_frame.grid(row=6, column=0, columnspan=3, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, height=24, width=58, wrap="word", state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)

        self.refresh_mode_labels()

    def refresh_mode_labels(self):
        names = {
            "exe_exe": "黑 exe vs 白 exe",
            "human_black": "用户黑 vs exe 白",
            "human_white": "exe 黑 vs 用户白",
            "human_human": "用户 vs 用户",
        }
        self.mode_hint.configure(text=names.get(self.mode_var.get(), ""))

    def choose_exe(self, var):
        path = filedialog.askopenfilename(
            title="选择 exe 程序",
            filetypes=(("Executable", "*.exe"), ("All files", "*.*")),
        )
        if path:
            var.set(path)

    def start_game(self):
        self.controller.start_game(self.mode_var.get(), self.black_path_var.get(), self.white_path_var.get())

    def next_game(self):
        self.controller.next_game(self.mode_var.get(), self.black_path_var.get(), self.white_path_var.get())

    def stop_game(self):
        self.controller.stop_game()

    def set_status(self, text):
        self.status_var.set(text)

    def log(self, text):
        stamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{stamp}] {text}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def update_stats(self):
        s = self.controller.stats
        self.stats_var.set(
            f"总局数：{s['total']}\n"
            f"黑胜：{s['black_win']}    白胜：{s['white_win']}    平局：{s['draw']}\n"
            f"黑方犯规负：{s['black_forbidden_loss']}\n"
            f"黑方非法/超时负：{s['black_illegal_timeout_loss']}\n"
            f"白方非法/超时负：{s['white_illegal_timeout_loss']}"
        )

    def board_to_canvas(self, r, c):
        return self.margin + c * self.cell, self.margin + r * self.cell

    def canvas_to_board(self, x, y):
        c = round((x - self.margin) / self.cell)
        r = round((y - self.margin) / self.cell)
        if not (0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE):
            return None
        cx, cy = self.board_to_canvas(r, c)
        if abs(x - cx) > self.cell * 0.45 or abs(y - cy) > self.cell * 0.45:
            return None
        return r, c

    def draw_board(self, board=None):
        if board is None:
            board = self.controller.rules.board
        self.display_board = board
        self.canvas.delete("all")
        first = self.margin
        last = self.margin + self.cell * (BOARD_SIZE - 1)
        for i in range(BOARD_SIZE):
            pos = self.margin + i * self.cell
            self.canvas.create_line(first, pos, last, pos, fill="#5e4215")
            self.canvas.create_line(pos, first, pos, last, fill="#5e4215")
        for idx in (3, 9, 15, 18, 22, 28, 34):
            if 0 <= idx < BOARD_SIZE:
                x, y = self.board_to_canvas(idx, idx)
                self.canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill="#5e4215", outline="")
        for i in range(BOARD_SIZE):
            x = self.margin + i * self.cell
            self.canvas.create_text(x, 9, text=str(i + 1), font=("Arial", 7), fill="#3d2b0e")
            y = self.margin + i * self.cell
            self.canvas.create_text(9, y, text=str(i + 1), font=("Arial", 7), fill="#3d2b0e")
        radius = self.cell * 0.42
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                value = board[r][c]
                if value == EMPTY:
                    continue
                x, y = self.board_to_canvas(r, c)
                if value == BLACK:
                    self.canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill="#111111", outline="#000000")
                else:
                    self.canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill="#f5f5f5", outline="#777777")
        if self.controller.move_history and board is self.controller.rules.board:
            rec = self.controller.move_history[-1]
            x, y = self.board_to_canvas(rec.row, rec.col)
            self.canvas.create_rectangle(x - 4, y - 4, x + 4, y + 4, outline="#d22", width=2)

    def on_canvas_click(self, event):
        if self.replay_active and self.controller.game_over:
            self.log("复盘中不能落子，请开始下一盘")
            return
        pos = self.canvas_to_board(event.x, event.y)
        if not pos:
            return
        self.controller.human_move(pos[0], pos[1])

    def set_replay_enabled(self, enabled, max_value):
        self.replay_active = enabled
        self.replay_scale.configure(to=max_value)
        self.replay_scale.set(max_value)
        self.replay_label.configure(text=f"{max_value}/{max_value}")
        if not enabled:
            self.replay_scale.set(0)
            self.replay_label.configure(text="0/0")

    def update_replay_range(self, max_value):
        if not self.controller.game_over:
            self.replay_scale.configure(to=max_value)
            self.replay_scale.set(max_value)
            self.replay_label.configure(text=f"{max_value}/{max_value}")

    def on_replay_change(self, value):
        if not self.controller.game_over:
            return
        try:
            count = int(round(float(value)))
        except ValueError:
            return
        max_value = len(self.controller.move_history)
        count = max(0, min(max_value, count))
        self.replay_label.configure(text=f"{count}/{max_value}")
        self.draw_board(self.controller.board_for_replay(count))

    def periodic_tick(self):
        self.controller.tick()
        self.root.after(100, self.periodic_tick)

    def on_close(self):
        self.controller.stop_game(log=False)
        self.root.destroy()


def main():
    root = tk.Tk()
    app = GomokuApp(root)
    app.log("五子棋裁判已启动")
    root.mainloop()


if __name__ == "__main__":
    main()
