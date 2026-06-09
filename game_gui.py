#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shop（去商店）游戏 - GUI版本
使用tkinter构建可视化界面
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import random
import os
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# 背景图片路径
BG_IMAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "Camera_1040g3k03215htbl97e005ocprvd40rrpgsa96ro.jpg")


# ============================================================
# 常量与枚举
# ============================================================

class Location(Enum):
    CENTER = "中间"
    SHOP = "商店"
    MACHINE = "机械屋"
    IRON = "铁匠铺"
    MAGIC = "魔法屋"

# 地图邻接关系（环形+中间连接全部）
# 商店↔机械屋↔魔法屋↔铁匠铺↔商店，中间↔全部
# 不直连：商店↔魔法屋、机械屋↔铁匠铺
ADJACENT_MAP: Dict[Location, List[Location]] = {
    Location.CENTER:  [Location.SHOP, Location.MACHINE, Location.IRON, Location.MAGIC],
    Location.SHOP:    [Location.CENTER, Location.MACHINE, Location.IRON],
    Location.MACHINE: [Location.CENTER, Location.SHOP, Location.MAGIC],
    Location.IRON:    [Location.CENTER, Location.SHOP, Location.MAGIC],
    Location.MAGIC:   [Location.CENTER, Location.MACHINE, Location.IRON],
}


class RPS(Enum):
    ROCK = "石头"
    SCISSORS = "剪刀"
    PAPER = "布"


RPS_RULES = {
    (RPS.ROCK, RPS.SCISSORS): True,
    (RPS.SCISSORS, RPS.PAPER): True,
    (RPS.PAPER, RPS.ROCK): True,
}


def rps_win(a: RPS, b: RPS) -> bool:
    if a == b:
        return False
    return RPS_RULES.get((a, b), False)


# ============================================================
# 玩家类
# ============================================================

@dataclass
class Player:
    name: str
    hp: float = 1.0
    location: Location = Location.CENTER
    speed: int = 1
    steps_this_turn: int = 0
    steps_used: int = 0

    inventory: Dict[str, int] = field(default_factory=dict)

    # 状态
    stunned_until_turn: int = -1
    lucky_turns_left: int = 0

    # 拳套
    glove_upgraded: bool = False

    # 大狙
    sniper_aimed_at: Optional[str] = None
    sniper_bullets_loaded: int = 0
    blow_dart_hits: int = 0

    # 召唤器
    summoner_energy: int = 0
    transformed_as: Optional[str] = None
    transform_hp: float = 0

    # 刀
    knife_forged: bool = False
    knife_forged_turn: int = -1
    knife_upgraded: bool = False
    famous_knife_used: bool = False

    # 盾
    shield_forged: bool = False
    shield_upgraded: bool = False
    shield_enchanted: bool = False
    shield_active: bool = False

    # 电磁炮
    railguns_charged: int = 0

    # 机甲
    mech_active: bool = False
    mech_hp: float = 0
    mech_attacks_done: int = 0

    # 机会药水
    banked_steps: int = 0

    def add_item(self, item_name: str, count: int = 1):
        self.inventory[item_name] = self.inventory.get(item_name, 0) + count

    def remove_item(self, item_name: str, count: int = 1) -> bool:
        if self.inventory.get(item_name, 0) >= count:
            self.inventory[item_name] -= count
            if self.inventory[item_name] <= 0:
                del self.inventory[item_name]
            return True
        return False

    def has_item(self, item_name: str, count: int = 1) -> bool:
        return self.inventory.get(item_name, 0) >= count

    def is_stunned(self, turn: int) -> bool:
        return self.stunned_until_turn >= turn

    def is_alive(self) -> bool:
        return self.hp > 0

    def take_damage(self, amount: float, attacker_name: str = "",
                    is_magic: bool = False) -> str:
        remaining = amount
        messages = []

        # 优先级1：盾
        if self.shield_active:
            if is_magic and not self.shield_enchanted:
                messages.append(f"🛡️ {self.name}的盾无法格挡魔法！")
            else:
                messages.append(f"🛡️ {self.name}的盾抵挡了伤害！")
                self.shield_active = False
                return "\n".join(messages)

        # 优先级2：变身
        if self.transformed_as:
            if remaining >= self.transform_hp:
                remaining -= self.transform_hp
                messages.append(f"💥 {self.name}的{self.transformed_as}形态被击破！")
                self.transformed_as = None
                self.transform_hp = 0
                self.speed = 1
                if remaining <= 0:
                    return "\n".join(messages)
            else:
                self.transform_hp -= remaining
                return "\n".join(messages)

        # 优先级3：名刀
        if self.knife_upgraded and not self.famous_knife_used:
            messages.append(f"🗡️ {self.name}的名刀抵挡了伤害！")
            self.famous_knife_used = True
            return "\n".join(messages)

        # 优先级4：机甲
        if self.mech_active:
            if remaining >= self.mech_hp:
                remaining -= self.mech_hp
                messages.append(f"🤖 {self.name}的机甲被摧毁！")
                self.mech_active = False
                self.mech_hp = 0
                if remaining <= 0:
                    return "\n".join(messages)
            else:
                self.mech_hp -= remaining
                return "\n".join(messages)

        # 优先级5：玩家本身
        self.hp -= remaining
        messages.append(f"💔 {self.name}受到{remaining}点伤害！剩余:{self.hp}")
        if self.hp <= 0:
            messages.append(f"💀 {self.name}被击败了！")
        return "\n".join(messages)


# ============================================================
# 游戏状态
# ============================================================

@dataclass
class GameState:
    players: List[Player]
    current_turn: int = 0
    brag_count: int = 0
    global_poison_id: int = 0
    poisons: Dict[int, dict] = field(default_factory=dict)

    def get_players_at(self, location: Location) -> List[Player]:
        return [p for p in self.players if p.location == location and p.is_alive()]

    def get_alive_players(self) -> List[Player]:
        return [p for p in self.players if p.is_alive()]

    def get_player_by_name(self, name: str) -> Optional[Player]:
        for p in self.players:
            if p.name == name:
                return p
        return None

    def get_enemies_of(self, player: Player) -> List[Player]:
        return [p for p in self.players if p.name != player.name and p.is_alive()]

    def next_poison_id(self) -> int:
        self.global_poison_id += 1
        return self.global_poison_id


# ============================================================
# GUI游戏类
# ============================================================

class ShopGameGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("🏪 Shop（去商店）- 多人回合制策略游戏")
        self.root.geometry("1200x800")
        self.root.configure(bg="#2d2d2d")

        self.game: Optional[GameState] = None
        self.current_player_idx: int = 0
        self.steps_this_round: Dict[str, int] = {}
        self.waiting_for_rps: bool = False
        self.rps_choices: Dict[str, RPS] = {}
        self.rps_current_idx: int = 0

        # 动作回调
        self.pending_action_callback = None

        self.setup_start_screen()

    # ============================================================
    # 开始画面
    # ============================================================

    def setup_start_screen(self):
        """设置开始画面"""
        self.clear_window()

        frame = tk.Frame(self.root, bg="#2d2d2d")
        frame.place(relx=0.5, rely=0.5, anchor="center")

        title = tk.Label(frame, text="🏪 Shop（去商店）",
                         font=("微软雅黑", 36, "bold"),
                         fg="#ffd700", bg="#2d2d2d")
        title.pack(pady=20)

        subtitle = tk.Label(frame, text="多人回合制策略游戏",
                            font=("微软雅黑", 16), fg="#aaa", bg="#2d2d2d")
        subtitle.pack(pady=5)

        # 玩家人数
        num_frame = tk.Frame(frame, bg="#2d2d2d")
        num_frame.pack(pady=20)

        tk.Label(num_frame, text="玩家人数:", font=("微软雅黑", 14),
                 fg="white", bg="#2d2d2d").pack(side="left", padx=5)

        self.num_players_var = tk.IntVar(value=2)
        spin = ttk.Spinbox(num_frame, from_=2, to=6,
                           textvariable=self.num_players_var, width=5,
                           font=("微软雅黑", 14))
        spin.pack(side="left", padx=5)

        # 玩家名字
        tk.Label(frame, text="输入玩家名字（逗号分隔）:",
                 font=("微软雅黑", 12), fg="#ccc", bg="#2d2d2d").pack(pady=10)

        self.names_entry = tk.Entry(frame, font=("微软雅黑", 14), width=40)
        self.names_entry.insert(0, "玩家1, 玩家2")
        self.names_entry.pack(pady=5)

        # 开始按钮
        start_btn = tk.Button(frame, text="🎮 开始游戏",
                              font=("微软雅黑", 16, "bold"),
                              bg="#4CAF50", fg="white",
                              command=self.start_game,
                              cursor="hand2")
        start_btn.pack(pady=30)

        # 规则提示
        rules = tk.Label(frame,
                         text="规则：在5个位置间移动，购买武器，击败对手！\n"
                              "地图：商店↔机械屋↔魔法屋↔铁匠铺↔商店，中间↔全部",
                         font=("微软雅黑", 10), fg="#888", bg="#2d2d2d")
        rules.pack(pady=10)

    def start_game(self):
        """初始化游戏"""
        names_str = self.names_entry.get().strip()
        names = [n.strip() for n in names_str.split(",") if n.strip()]

        num = self.num_players_var.get()
        while len(names) < num:
            names.append(f"玩家{len(names)+1}")
        names = names[:num]

        players = [Player(name=n) for n in names]
        self.game = GameState(players=players)
        self.current_player_idx = 0

        self.setup_game_screen()
        self.new_turn()

    # ============================================================
    # 游戏主界面
    # ============================================================

    def setup_game_screen(self):
        """设置游戏主界面"""
        self.clear_window()

        # 顶部信息栏
        self.top_frame = tk.Frame(self.root, bg="#1a1a2e", height=50)
        self.top_frame.pack(fill="x")
        self.top_frame.pack_propagate(False)

        self.turn_label = tk.Label(self.top_frame, text="第 1 回合",
                                   font=("微软雅黑", 14, "bold"),
                                   fg="#ffd700", bg="#1a1a2e")
        self.turn_label.pack(side="left", padx=20, pady=10)

        self.current_player_label = tk.Label(self.top_frame, text="",
                                             font=("微软雅黑", 14),
                                             fg="white", bg="#1a1a2e")
        self.current_player_label.pack(side="left", padx=20, pady=10)

        self.steps_label = tk.Label(self.top_frame, text="",
                                    font=("微软雅黑", 12),
                                    fg="#00ff88", bg="#1a1a2e")
        self.steps_label.pack(side="right", padx=20, pady=10)

        # 主体：左边地图+玩家 | 右边操作
        self.main_frame = tk.Frame(self.root, bg="#2d2d2d")
        self.main_frame.pack(fill="both", expand=True)

        # 左侧：地图画布
        self.left_frame = tk.Frame(self.main_frame, bg="#2d2d2d")
        self.left_frame.pack(side="left", fill="both", expand=True)

        self.canvas = tk.Canvas(self.left_frame, bg="#1e1e2e",
                                highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)

        # 右侧：操作面板
        self.right_frame = tk.Frame(self.main_frame, bg="#252535", width=350)
        self.right_frame.pack(side="right", fill="y")
        self.right_frame.pack_propagate(False)

        # 操作标题
        tk.Label(self.right_frame, text="⚔️ 行动面板",
                 font=("微软雅黑", 14, "bold"),
                 fg="#ffd700", bg="#252535").pack(pady=10)

        # 操作按钮区域（可滚动）
        self.action_canvas = tk.Canvas(self.right_frame, bg="#252535",
                                       highlightthickness=0)
        self.action_scrollbar = ttk.Scrollbar(self.right_frame,
                                              orient="vertical",
                                              command=self.action_canvas.yview)
        self.action_frame = tk.Frame(self.action_canvas, bg="#252535")
        self.action_frame.bind("<Configure>",
                               lambda e: self.action_canvas.configure(
                                   scrollregion=self.action_canvas.bbox("all")))
        self.action_canvas.create_window((0, 0), window=self.action_frame,
                                         anchor="nw", width=330)
        self.action_canvas.configure(yscrollcommand=self.action_scrollbar.set)
        self.action_canvas.pack(side="left", fill="both", expand=True)
        self.action_scrollbar.pack(side="right", fill="y")

        # 底部日志
        self.log_frame = tk.Frame(self.root, bg="#1a1a2e", height=150)
        self.log_frame.pack(fill="x")
        self.log_frame.pack_propagate(False)

        tk.Label(self.log_frame, text="📜 战斗日志",
                 font=("微软雅黑", 10, "bold"),
                 fg="#aaa", bg="#1a1a2e").pack(anchor="w", padx=10, pady=2)

        self.log_text = tk.Text(self.log_frame, font=("Consolas", 10),
                                bg="#0d0d1a", fg="#00ff88",
                                height=7, wrap="word", state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=10, pady=5)

        # 绑定画布大小变化事件
        self.canvas.bind("<Configure>", lambda e: self.draw_map())

    # ============================================================
    # 地图绘制
    # ============================================================

    def draw_map(self):
        """绘制地图"""
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()

        if w < 10 or h < 10:
            return

        # 绘制背景图片
        if HAS_PIL and os.path.exists(BG_IMAGE_PATH):
            try:
                img = Image.open(BG_IMAGE_PATH)
                img = img.resize((w, h), Image.LANCZOS)
                self._bg_photo = ImageTk.PhotoImage(img)
                self.canvas.create_image(0, 0, anchor="nw", image=self._bg_photo)
            except Exception:
                # 无背景时填充深色
                self.canvas.create_rectangle(0, 0, w, h, fill="#1e1e2e", outline="")

        # 位置坐标（对应背景图上的地点位置）
        cx, cy = w // 2, h // 2
        r = min(w, h) * 0.35

        self.loc_positions = {
            Location.CENTER: (cx, cy),
            Location.SHOP:    (cx, cy - r),
            Location.MACHINE: (cx - r, cy),
            Location.IRON:    (cx + r, cy),
            Location.MAGIC:   (cx, cy + r),
        }

        # 绘制玩家（不再绘制地点节点，背景图已有）
        if self.game:
            player_colors = ["#ff6b6b", "#4ecdc4", "#45b7d1",
                             "#96ceb4", "#ffeaa7", "#dda0dd"]
            for i, player in enumerate(self.game.players):
                if not player.is_alive():
                    continue
                x, y = self.loc_positions[player.location]
                # 偏移避免重叠
                offset_x = (i - len(self.game.players) / 2) * 30
                px = x + offset_x
                py = y

                color = player_colors[i % len(player_colors)]

                # 玩家圆形标记
                self.canvas.create_oval(px - 15, py - 14, px + 15, py + 12,
                                        fill=color, outline="white", width=2)
                self.canvas.create_text(px, py - 1,
                                        text=player.name[0],
                                        font=("微软雅黑", 11, "bold"),
                                        fill="white")

                # 名字标签
                self.canvas.create_text(px, py + 20,
                                        text=player.name,
                                        font=("微软雅黑", 9, "bold"),
                                        fill="white")

                # HP条
                hp_w = 36
                hp_h = 5
                hp_fill = max(0, player.hp / 1.0)
                bar_y = py + 32
                self.canvas.create_rectangle(px - hp_w//2, bar_y,
                                             px + hp_w//2, bar_y + hp_h,
                                             fill="#333333", outline="#555")
                if hp_fill > 0:
                    hp_color = "#00ff00" if hp_fill > 0.5 else "#ffaa00" if hp_fill > 0.25 else "#ff0000"
                    self.canvas.create_rectangle(px - hp_w//2, bar_y,
                                                 px - hp_w//2 + int(hp_w * hp_fill),
                                                 bar_y + hp_h,
                                                 fill=hp_color, outline="")

                # 状态图标
                status = ""
                if player.shield_active:
                    status += "🛡️"
                if player.mech_active:
                    status += "🤖"
                if player.transformed_as:
                    status += "🔮"
                if player.is_stunned(self.game.current_turn):
                    status += "⚡"
                if status:
                    self.canvas.create_text(px, py - 28, text=status,
                                            font=("", 10))

        # 毒药标记
        if self.game:
            for pid, poison in self.game.poisons.items():
                loc = poison["location"]
                x, y = self.loc_positions[loc]
                self.canvas.create_text(x, y + 45,
                                        text="☠️", font=("", 14))

    # ============================================================
    # 日志系统
    # ============================================================

    def log(self, message: str):
        """添加日志"""
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ============================================================
    # 回合系统
    # ============================================================

    def new_turn(self):
        """开始新回合"""
        self.game.current_turn += 1
        self.turn_label.config(text=f"第 {self.game.current_turn} 回合")

        # 处理毒药
        self.process_poison()

        # 检查胜利
        if self.check_win():
            return

        self.log(f"\n{'='*30} 第{self.game.current_turn}回合 {'='*30}")

        # 石头剪刀布
        self.start_rps_phase()

    def start_rps_phase(self):
        """开始石头剪刀布/骰子阶段"""
        alive = self.game.get_alive_players()
        # 过滤眩晕玩家
        self.rps_participants = [p for p in alive
                                 if not p.is_stunned(self.game.current_turn)]

        if not self.rps_participants:
            # 所有人都眩晕，跳过
            self.steps_this_round = {}
            self.start_player_turns()
            return

        # 只有一人可参与猜拳 → 直接获得1步
        if len(self.rps_participants) == 1:
            only_player = self.rps_participants[0]
            self.steps_this_round = {only_player.name: 1}
            self.log(f"⚡ 仅 {only_player.name} 可行动，自动获得 1 步")
            self.start_player_turns()
            return

        # 双人模式 → 用骰子决定
        if len(alive) == 2 and len(self.rps_participants) == 2:
            self.start_dice_phase()
            return

        # 多人模式 → 石头剪刀布
        self.rps_choices = {}
        self.rps_current_idx = 0
        self.ask_rps_next()

    def start_dice_phase(self):
        """双人骰子模式：掷骰子决定谁行动"""
        self.clear_actions()

        title = tk.Label(self.action_frame,
                         text="🎲 掷骰子！",
                         font=("微软雅黑", 16, "bold"),
                         fg="#ffd700", bg="#252535")
        title.pack(pady=15)

        info = tk.Label(self.action_frame,
                        text="双人模式：掷骰子决定谁行动\n点大的一方获得行动权(1步)",
                        font=("微软雅黑", 11),
                        fg="#ccc", bg="#252535")
        info.pack(pady=10)

        btn = tk.Button(self.action_frame, text="🎲 掷骰子！",
                        font=("微软雅黑", 14, "bold"),
                        bg="#e8a838", fg="white",
                        width=20, height=2,
                        cursor="hand2",
                        command=self._resolve_dice)
        btn.pack(pady=20)

        self.current_player_label.config(text="🎲 掷骰子阶段")

    def _resolve_dice(self):
        """结算骰子"""
        p1 = self.rps_participants[0]
        p2 = self.rps_participants[1]

        # 掷骰子直到分出胜负
        while True:
            d1 = random.randint(1, 6)
            d2 = random.randint(1, 6)
            if d1 != d2:
                break

        self.log(f"🎲 {p1.name} 掷出 {d1} | {p2.name} 掷出 {d2}")

        if d1 > d2:
            winner = p1
            self.steps_this_round = {p1.name: 1, p2.name: 0}
        else:
            winner = p2
            self.steps_this_round = {p1.name: 0, p2.name: 1}

        self.log(f"🎲 → {winner.name} 获得行动权(1步)！")

        # 显示骰子结果动画
        self.clear_actions()
        result_frame = tk.Frame(self.action_frame, bg="#252535")
        result_frame.pack(pady=20)

        dice_faces = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]

        tk.Label(result_frame, text=f"{p1.name}",
                 font=("微软雅黑", 12), fg="white", bg="#252535").pack()
        tk.Label(result_frame, text=dice_faces[d1-1],
                 font=("", 48), fg="#ffd700", bg="#252535").pack()
        tk.Label(result_frame, text=f"  VS  ",
                 font=("微软雅黑", 14, "bold"), fg="#aaa", bg="#252535").pack(pady=5)
        tk.Label(result_frame, text=f"{p2.name}",
                 font=("微软雅黑", 12), fg="white", bg="#252535").pack()
        tk.Label(result_frame, text=dice_faces[d2-1],
                 font=("", 48), fg="#ffd700", bg="#252535").pack()

        tk.Label(result_frame, text=f"\n🏆 {winner.name} 行动！",
                 font=("微软雅黑", 14, "bold"), fg="#00ff88", bg="#252535").pack(pady=10)

        # 继续按钮
        tk.Button(self.action_frame, text="▶️ 继续",
                  font=("微软雅黑", 12),
                  bg="#4CAF50", fg="white", width=20,
                  cursor="hand2",
                  command=self.start_player_turns).pack(pady=10)

    def ask_rps_next(self):
        """询问下一个玩家的石头剪刀布选择"""
        if self.rps_current_idx >= len(self.rps_participants):
            self.resolve_rps()
            return

        player = self.rps_participants[self.rps_current_idx]
        self.show_rps_dialog(player)

    def show_rps_dialog(self, player: Player):
        """显示石头剪刀布选择对话框"""
        self.clear_actions()

        title = tk.Label(self.action_frame,
                         text=f"✊✌️✋ 石头剪刀布",
                         font=("微软雅黑", 13, "bold"),
                         fg="#ffd700", bg="#252535")
        title.pack(pady=10)

        name_label = tk.Label(self.action_frame,
                              text=f"{player.name}，请选择：",
                              font=("微软雅黑", 12),
                              fg="white", bg="#252535")
        name_label.pack(pady=5)

        choices = [("✊ 石头", RPS.ROCK),
                   ("✌️ 剪刀", RPS.SCISSORS),
                   ("✋ 布", RPS.PAPER)]

        for text, rps_val in choices:
            btn = tk.Button(self.action_frame, text=text,
                            font=("微软雅黑", 14),
                            bg="#3d3d5c", fg="white",
                            width=20, height=2,
                            cursor="hand2",
                            command=lambda v=rps_val, p=player: self.on_rps_choice(p, v))
            btn.pack(pady=5)

        self.current_player_label.config(text=f"🎲 {player.name} 出拳")

    def on_rps_choice(self, player: Player, choice: RPS):
        """处理石头剪刀布选择"""
        self.rps_choices[player.name] = choice
        self.rps_current_idx += 1
        self.ask_rps_next()

    def resolve_rps(self):
        """结算石头剪刀布"""
        # 显示结果
        result_lines = ["⚡ 石头剪刀布结果："]
        for name, choice in self.rps_choices.items():
            result_lines.append(f"  {name}: {choice.value}")

        # 计算步数
        names = list(self.rps_choices.keys())
        self.steps_this_round = {}
        for name in names:
            wins = 0
            for other in names:
                if name != other:
                    if rps_win(self.rps_choices[name], self.rps_choices[other]):
                        wins += 1
            self.steps_this_round[name] = wins

        # 幸运药水
        for name, s in self.steps_this_round.items():
            player = self.game.get_player_by_name(name)
            if player and player.lucky_turns_left > 0:
                self.steps_this_round[name] = s * 2
                result_lines.append(f"  🍀 {name} 幸运翻倍！")

        for name, s in self.steps_this_round.items():
            result_lines.append(f"  → {name} 获得 {s} 步")

        self.log("\n".join(result_lines))

        # 如果所有人都是0步，重新猜拳
        if all(s == 0 for s in self.steps_this_round.values()):
            self.log("🤝 全员平局！重新猜拳...")
            self.rps_choices = {}
            self.rps_current_idx = 0
            self.ask_rps_next()
            return

        self.start_player_turns()

    def start_player_turns(self):
        """开始玩家行动阶段"""
        self.current_player_idx = 0
        self.next_player_turn()

    def next_player_turn(self):
        """下一个玩家行动"""
        while self.current_player_idx < len(self.game.players):
            player = self.game.players[self.current_player_idx]

            if not player.is_alive():
                self.current_player_idx += 1
                continue

            if self.check_win():
                return

            # 眩晕
            if player.is_stunned(self.game.current_turn):
                self.log(f"⚡ {player.name} 被眩晕，跳过回合！")
                player.stunned_until_turn = -1
                self.current_player_idx += 1
                continue

            # 召唤器自动充能
            if player.has_item("召唤器") and not player.transformed_as:
                player.summoner_energy += 1
                self.log(f"📿 {player.name}的召唤器+1能量 (总:{player.summoner_energy})")

            # 设置步数
            player.steps_this_turn = self.steps_this_round.get(player.name, 0)
            player.steps_used = 0

            if player.steps_this_turn <= 0:
                self.log(f"⏩ {player.name} 本回合无步数")
                self.current_player_idx += 1
                continue

            # 开始该玩家行动
            self.begin_player_actions(player)
            return

        # 所有玩家行动完毕，处理回合结束
        self.end_turn()

    def begin_player_actions(self, player: Player):
        """显示玩家的行动选项"""
        self.current_player_label.config(text=f"🎮 {player.name} 的回合")
        remaining = player.steps_this_turn - player.steps_used
        self.steps_label.config(text=f"👣 剩余步数: {remaining}")

        self.log(f"\n🎮 {player.name} 的回合 (步数:{player.steps_this_turn})")
        self.draw_map()
        self.show_actions(player)

    def show_actions(self, player: Player):
        """显示可用行动"""
        self.clear_actions()
        remaining = player.steps_this_turn - player.steps_used
        self.steps_label.config(text=f"👣 剩余步数: {remaining}")

        if remaining <= 0:
            self.finish_player_turn(player)
            return

        # 玩家状态简报
        status_frame = tk.Frame(self.action_frame, bg="#353545")
        status_frame.pack(fill="x", padx=5, pady=5)

        tk.Label(status_frame, text=f"📋 {player.name}",
                 font=("微软雅黑", 11, "bold"),
                 fg="white", bg="#353545").pack(anchor="w", padx=5)
        tk.Label(status_frame,
                 text=f"❤️{player.hp} | 📍{player.location.value} | 👣{remaining}步",
                 font=("微软雅黑", 9), fg="#aaa", bg="#353545").pack(anchor="w", padx=5)

        if player.inventory:
            items_str = " ".join(f"{k}×{v}" for k, v in player.inventory.items())
            tk.Label(status_frame, text=f"🎒 {items_str}",
                     font=("微软雅黑", 9), fg="#88ccff", bg="#353545").pack(anchor="w", padx=5)

        # 分组显示行动
        actions = self.get_available_actions(player)

        # 基本行动
        self.add_action_section("基本")
        for name, desc, cmd in actions.get("基本", []):
            self.add_action_button(name, desc, cmd)

        # 攻击
        if "攻击" in actions:
            self.add_action_section("攻击")
            for name, desc, cmd in actions["攻击"]:
                self.add_action_button(name, desc, cmd, color="#cc4444")

        # 购买
        if "购买" in actions:
            self.add_action_section("购买/制造")
            for name, desc, cmd in actions["购买"]:
                self.add_action_button(name, desc, cmd, color="#44aa44")

        # 其他
        if "其他" in actions:
            self.add_action_section("其他")
            for name, desc, cmd in actions["其他"]:
                self.add_action_button(name, desc, cmd, color="#aa8833")

        # 结束回合按钮
        end_btn = tk.Button(self.action_frame, text="⏹️ 结束回合",
                            font=("微软雅黑", 11),
                            bg="#666", fg="white", width=30,
                            cursor="hand2",
                            command=lambda: self.finish_player_turn(player))
        end_btn.pack(pady=15)

    def add_action_section(self, title: str):
        """添加行动分组标题"""
        tk.Label(self.action_frame, text=f"── {title} ──",
                 font=("微软雅黑", 9), fg="#777",
                 bg="#252535").pack(pady=(10, 2))

    def add_action_button(self, name: str, desc: str, command, color: str = "#3d3d5c"):
        """添加行动按钮"""
        btn = tk.Button(self.action_frame,
                        text=f"{name}  ({desc})",
                        font=("微软雅黑", 10),
                        bg=color, fg="white",
                        width=30, anchor="w",
                        cursor="hand2",
                        command=command)
        btn.pack(pady=2, padx=5)

    def clear_actions(self):
        """清空操作面板"""
        for widget in self.action_frame.winfo_children():
            widget.destroy()

    def finish_player_turn(self, player: Player):
        """结束当前玩家回合"""
        # 幸运药水减少
        if player.lucky_turns_left > 0:
            player.lucky_turns_left -= 1

        self.current_player_idx += 1
        self.next_player_turn()

    def end_turn(self):
        """回合结束"""
        if not self.check_win():
            self.new_turn()

    # ============================================================
    # 行动列表
    # ============================================================

    def get_available_actions(self, player: Player) -> Dict[str, list]:
        """获取分类的可用行动"""
        actions: Dict[str, list] = {"基本": []}

        # 基本行动
        actions["基本"].append(("🚶 移动", "到相邻位置",
                               lambda: self.action_move(player)))
        actions["基本"].append(("👢 踢人", "踢走同位置的人",
                               lambda: self.action_kick(player)))
        actions["基本"].append(("😎 装逼", "积累逼数",
                               lambda: self.action_brag(player)))

        # 攻击行动
        attack = []
        if player.has_item("拳套") or player.glove_upgraded:
            attack.append(("🥊 拳套攻击", "同位置判定1伤害",
                           lambda: self.action_use_glove(player)))
        if player.has_item("大狙"):
            attack.append(("🔫 枪托", "同位置0.5伤害",
                           lambda: self.action_sniper_melee(player)))
            if player.sniper_aimed_at and player.sniper_bullets_loaded > 0:
                attack.append(("💥 开枪", f"射击{player.sniper_aimed_at}",
                               lambda: self.action_sniper_shoot(player)))
        if player.has_item("吹箭"):
            attack.append(("💨 吹箭", "远程连续判定伤害",
                           lambda: self.action_blow_dart(player)))
        if player.has_item("刀") or player.has_item("名刀"):
            attack.append(("🔪 刀攻击", "同位置1伤害",
                           lambda: self.action_use_knife(player)))
        if player.railguns_charged > 0:
            attack.append(("💥 电磁炮", "1格范围0.5伤害+眩晕",
                           lambda: self.action_fire_railgun(player)))
        if player.mech_active:
            attack.append(("🤖 飞砍", "机甲远程攻击",
                           lambda: self.action_mech_attack(player)))
        if player.transformed_as == "关羽":
            attack.append(("⚔️ 关羽", "关羽攻击",
                           lambda: self.action_guanyu_attack(player)))
        if attack:
            actions["攻击"] = attack

        # 购买/制造
        buy = []
        if player.location == Location.SHOP:
            buy.append(("🥊 买拳套", "1步",
                        lambda: self.action_buy(player, "拳套")))
            buy.append(("🔫 买大狙", "1步",
                        lambda: self.action_buy(player, "大狙")))
            buy.append(("💨 买吹箭", "1步",
                        lambda: self.action_buy(player, "吹箭")))
            buy.append(("📿 买召唤器", "1步",
                        lambda: self.action_buy(player, "召唤器")))
            if player.has_item("大狙"):
                buy.append(("🔸 买子弹", "1步",
                            lambda: self.action_buy_bullet(player)))

        if player.location == Location.IRON:
            if not player.knife_forged:
                buy.append(("🔪 炼刀", "1步",
                            lambda: self.action_forge_knife(player)))
            if player.knife_forged and not player.has_item("刀") and not player.knife_upgraded:
                buy.append(("🔪 取刀", "1步",
                            lambda: self.action_take_knife(player)))
            if player.has_item("刀") and not player.knife_upgraded:
                buy.append(("🗡️ 升级名刀", "1步",
                            lambda: self.action_upgrade_knife(player)))
            if player.has_item("拳套") and not player.glove_upgraded:
                buy.append(("⚡ 升级电击拳套", "1步",
                            lambda: self.action_upgrade_glove(player)))
            if not player.shield_forged:
                buy.append(("🛡️ 炼盾", "1步",
                            lambda: self.action_forge_shield(player)))
            if player.shield_forged and not player.has_item("盾"):
                buy.append(("🛡️ 取盾", "1步",
                            lambda: self.action_take_shield(player)))
            if player.has_item("盾") and not player.shield_upgraded:
                buy.append(("🛡️⬆ 升级盾", "可架盾移动",
                            lambda: self.action_upgrade_shield(player)))
            if player.has_item("盾") and not player.shield_enchanted:
                buy.append(("🛡️✨ 附魔盾", "防魔法",
                            lambda: self.action_enchant_shield(player)))

        if player.location == Location.MAGIC:
            buy.append(("🧪 买机会药水", "1步",
                        lambda: self.action_buy(player, "机会药水")))
            buy.append(("☠️ 炼毒", "1步",
                        lambda: self.action_forge_poison(player)))
            buy.append(("🍀 买幸运药水", "1步",
                        lambda: self.action_buy(player, "幸运药水")))

        if player.location == Location.MACHINE:
            buy.append(("💥 买电磁炮", "1步",
                        lambda: self.action_buy(player, "电磁炮")))
            buy.append(("🤖 买机甲", "1步",
                        lambda: self.action_buy_mech(player)))

        if buy:
            actions["购买"] = buy

        # 其他行动
        other = []
        if player.has_item("大狙"):
            other.append(("🎯 瞄准", "瞄准目标",
                          lambda: self.action_aim(player)))
            if player.has_item("子弹"):
                other.append(("🔫 装弹", "装一颗子弹",
                              lambda: self.action_load_bullet(player)))
        if player.has_item("盾") and not player.shield_active:
            other.append(("🛡️ 架盾", "进入格挡",
                          lambda: self.action_raise_shield(player)))
        if player.has_item("电磁炮"):
            uncharged = player.inventory.get("电磁炮", 0) - player.railguns_charged
            if uncharged > 0:
                other.append(("⚡ 充能炮", "1步",
                              lambda: self.action_charge_railgun(player)))
        if player.has_item("机甲") and not player.mech_active:
            other.append(("🤖 召唤机甲", "激活机甲",
                          lambda: self.action_summon_mech(player)))
        if player.has_item("毒药"):
            other.append(("☠️ 扔毒药", "无距离限制",
                          lambda: self.action_throw_poison(player)))
        if player.has_item("机会药水"):
            other.append(("💰 用机会药水", "储存步数",
                          lambda: self.action_use_chance(player)))
        if player.banked_steps > 0:
            other.append(("💰 提取步数", f"有{player.banked_steps}步",
                          lambda: self.action_withdraw_steps(player)))
        if player.has_item("幸运药水"):
            other.append(("🍀 喝幸运药水", "3回合翻倍",
                          lambda: self.action_use_lucky(player)))
        if player.has_item("召唤器"):
            other.append(("⚡ 充能召唤器", "+1能量",
                          lambda: self.action_charge_summoner(player)))
            if player.summoner_energy >= 5 and not player.transformed_as:
                other.append(("🧙 变身太乙", "5能量",
                              lambda: self.action_transform_taiyi(player)))
            if player.summoner_energy >= 10 and not player.transformed_as:
                other.append(("⚔️ 变身关羽", "10能量",
                              lambda: self.action_transform_guanyu(player)))
        if player.transformed_as:
            other.append(("🔄 取消变身", "恢复人形",
                          lambda: self.action_revert_transform(player)))

        if other:
            actions["其他"] = other

        return actions

    # ============================================================
    # 行动实现
    # ============================================================

    def use_step(self, player: Player):
        """消耗一步"""
        player.steps_used += 1
        remaining = player.steps_this_turn - player.steps_used
        self.steps_label.config(text=f"👣 剩余步数: {remaining}")
        self.draw_map()
        if remaining > 0:
            self.show_actions(player)
        else:
            self.finish_player_turn(player)

    def action_move(self, player: Player):
        """移动"""
        neighbors = ADJACENT_MAP[player.location]
        self.clear_actions()
        tk.Label(self.action_frame, text="🚶 选择目的地：",
                 font=("微软雅黑", 12), fg="white", bg="#252535").pack(pady=10)

        for loc in neighbors:
            players_there = self.game.get_players_at(loc)
            info = loc.value
            if players_there:
                info += f" ({', '.join(p.name for p in players_there)})"
            btn = tk.Button(self.action_frame, text=f"📍 {info}",
                            font=("微软雅黑", 11),
                            bg="#3d5c3d", fg="white", width=28,
                            cursor="hand2",
                            command=lambda l=loc: self._do_move(player, l))
            btn.pack(pady=3)

        tk.Button(self.action_frame, text="↩️ 取消",
                  font=("微软雅黑", 10), bg="#555", fg="white",
                  command=lambda: self.show_actions(player)).pack(pady=10)

    def _do_move(self, player: Player, loc: Location):
        """执行移动"""
        if player.shield_active and not player.shield_upgraded:
            player.shield_active = False
            self.log(f"🛡️ {player.name}移动后盾收起")
        if player.sniper_aimed_at:
            player.sniper_aimed_at = None
            self.log(f"🔫 {player.name}移动后瞄准丢失")
        player.location = loc
        self.log(f"🚶 {player.name} → {loc.value}")
        self.use_step(player)

    def action_kick(self, player: Player):
        """踢人"""
        same_loc = [p for p in self.game.get_players_at(player.location)
                    if p.name != player.name]
        if not same_loc:
            messagebox.showinfo("提示", "当前位置没有其他人")
            return

        self.clear_actions()
        tk.Label(self.action_frame, text="👢 选择踢谁：",
                 font=("微软雅黑", 12), fg="white", bg="#252535").pack(pady=10)

        for target in same_loc:
            btn = tk.Button(self.action_frame, text=f"👤 {target.name}",
                            font=("微软雅黑", 11),
                            bg="#5c3d3d", fg="white", width=28,
                            cursor="hand2",
                            command=lambda t=target: self._choose_kick_dest(player, t))
            btn.pack(pady=3)

        tk.Button(self.action_frame, text="↩️ 取消",
                  font=("微软雅黑", 10), bg="#555", fg="white",
                  command=lambda: self.show_actions(player)).pack(pady=10)

    def _choose_kick_dest(self, player: Player, target: Player):
        """选择踢到哪"""
        neighbors = ADJACENT_MAP[player.location]
        self.clear_actions()
        tk.Label(self.action_frame, text=f"👢 踢{target.name}到：",
                 font=("微软雅黑", 12), fg="white", bg="#252535").pack(pady=10)

        for loc in neighbors:
            btn = tk.Button(self.action_frame, text=f"📍 {loc.value}",
                            font=("微软雅黑", 11),
                            bg="#5c5c3d", fg="white", width=28,
                            cursor="hand2",
                            command=lambda l=loc: self._do_kick(player, target, l))
            btn.pack(pady=3)

        tk.Button(self.action_frame, text="↩️ 取消",
                  font=("微软雅黑", 10), bg="#555", fg="white",
                  command=lambda: self.show_actions(player)).pack(pady=10)

    def _do_kick(self, player: Player, target: Player, dest: Location):
        """执行踢人"""
        target.location = dest
        if target.sniper_aimed_at:
            target.sniper_aimed_at = None
        self.log(f"👢 {player.name} 把 {target.name} 踢到 {dest.value}!")
        self.use_step(player)

    def action_brag(self, player: Player):
        """装逼"""
        self.game.brag_count += 1
        self.log(f"😎 {player.name} 装逼！(总:{self.game.brag_count})")
        if self.game.brag_count >= 7:
            self.game.brag_count = 0
            self.log("⚡⚡⚡ 第7逼！天雷滚滚！")
            self._thunder(player, 1)
        self.use_step(player)

    def _thunder(self, initiator: Player, damage: int):
        """雷劈"""
        enemies = self.game.get_enemies_of(initiator)
        for enemy in enemies:
            a = random.choice(list(RPS))
            d = random.choice(list(RPS))
            if rps_win(a, d):
                msg = enemy.take_damage(damage, initiator.name)
                self.log(f"⚡ 雷劈{enemy.name}！{msg}")
                return
        self.log("⚡ 全部没劈中！")

    # 购买类
    def action_buy(self, player: Player, item: str):
        """通用购买"""
        player.add_item(item)
        self.log(f"🛒 {player.name} 获得 {item}")
        self.use_step(player)

    def action_buy_bullet(self, player: Player):
        player.add_item("子弹")
        self.log(f"🔸 {player.name} 买了子弹")
        self.use_step(player)

    def action_buy_mech(self, player: Player):
        if player.mech_active:
            messagebox.showinfo("提示", "已有机甲")
            return
        player.add_item("机甲")
        self.log(f"🤖 {player.name} 买了机甲")
        self.use_step(player)

    # 大狙
    def action_aim(self, player: Player):
        enemies = self.game.get_enemies_of(player)
        if not enemies:
            messagebox.showinfo("提示", "没有目标")
            return
        self.clear_actions()
        tk.Label(self.action_frame, text="🎯 瞄准谁：",
                 font=("微软雅黑", 12), fg="white", bg="#252535").pack(pady=10)
        for e in enemies:
            btn = tk.Button(self.action_frame,
                            text=f"🎯 {e.name} ({e.location.value})",
                            font=("微软雅黑", 11),
                            bg="#3d3d5c", fg="white", width=28,
                            cursor="hand2",
                            command=lambda t=e: self._do_aim(player, t))
            btn.pack(pady=3)
        tk.Button(self.action_frame, text="↩️ 取消",
                  font=("微软雅黑", 10), bg="#555", fg="white",
                  command=lambda: self.show_actions(player)).pack(pady=10)

    def _do_aim(self, player: Player, target: Player):
        player.sniper_aimed_at = target.name
        self.log(f"🎯 {player.name} 瞄准 {target.name}")
        self.use_step(player)

    def action_load_bullet(self, player: Player):
        if player.remove_item("子弹"):
            player.sniper_bullets_loaded += 1
            self.log(f"🔫 装弹 (已装:{player.sniper_bullets_loaded})")
        self.use_step(player)

    def action_sniper_shoot(self, player: Player):
        if not player.sniper_aimed_at or player.sniper_bullets_loaded <= 0:
            return
        target = self.game.get_player_by_name(player.sniper_aimed_at)
        if not target or not target.is_alive():
            player.sniper_aimed_at = None
            messagebox.showinfo("提示", "目标丢失")
            return
        player.sniper_bullets_loaded -= 1
        msg = target.take_damage(1.0, player.name)
        self.log(f"💥 {player.name} 狙击 {target.name}！{msg}")
        player.sniper_aimed_at = None
        self.use_step(player)

    def action_sniper_melee(self, player: Player):
        same = [p for p in self.game.get_players_at(player.location)
                if p.name != player.name]
        if not same:
            messagebox.showinfo("提示", "没有目标")
            return
        self._select_target(same, lambda t: self._do_sniper_melee(player, t), player)

    def _do_sniper_melee(self, player: Player, target: Player):
        msg = target.take_damage(0.5, player.name)
        self.log(f"💢 {player.name} 枪托砸 {target.name}！{msg}")
        self.use_step(player)

    # 拳套
    def action_use_glove(self, player: Player):
        same = [p for p in self.game.get_players_at(player.location)
                if p.name != player.name]
        if not same:
            messagebox.showinfo("提示", "没有目标")
            return
        self._select_target(same, lambda t: self._do_glove(player, t), player)

    def _do_glove(self, player: Player, target: Player):
        a = random.choice(list(RPS))
        d = random.choice(list(RPS))
        self.log(f"🥊 {player.name}({a.value}) vs {target.name}({d.value})")
        if rps_win(a, d):
            msg = target.take_damage(1.0, player.name)
            self.log(f"✅ 命中！{msg}")
        else:
            if player.glove_upgraded:
                target.stunned_until_turn = self.game.current_turn + 1
                self.log(f"⚡ 电击！{target.name}眩晕1回合！")
            else:
                self.log(f"❌ 判定失败")
        self.use_step(player)

    # 吹箭
    def action_blow_dart(self, player: Player):
        enemies = self.game.get_enemies_of(player)
        if not enemies:
            messagebox.showinfo("提示", "没有目标")
            return
        self._select_target(enemies, lambda t: self._do_blow_dart(player, t), player)

    def _do_blow_dart(self, player: Player, target: Player):
        a = random.choice(list(RPS))
        d = random.choice(list(RPS))
        self.log(f"💨 吹箭! {player.name}({a.value}) vs {target.name}({d.value})")
        if rps_win(a, d):
            player.blow_dart_hits += 1
            self.log(f"🎯 命中！连击:{player.blow_dart_hits}")
            if player.blow_dart_hits >= 2:
                msg = target.take_damage(1.0, player.name)
                self.log(f"💥 两连击！{msg}")
                player.blow_dart_hits = 0
        else:
            player.blow_dart_hits = 0
            self.log("❌ 未中，连击中断")
        self.use_step(player)

    # 刀
    def action_forge_knife(self, player: Player):
        player.knife_forged = True
        player.knife_forged_turn = self.game.current_turn
        self.log(f"🔪 {player.name} 炼刀中...")
        self.use_step(player)

    def action_take_knife(self, player: Player):
        player.add_item("刀")
        self.log(f"🔪 {player.name} 取刀！")
        self.use_step(player)

    def action_upgrade_knife(self, player: Player):
        player.remove_item("刀")
        player.knife_upgraded = True
        player.add_item("名刀")
        self.log(f"🗡️ 升级为名刀！")
        self.use_step(player)

    def action_use_knife(self, player: Player):
        same = [p for p in self.game.get_players_at(player.location)
                if p.name != player.name]
        if not same:
            messagebox.showinfo("提示", "没有目标")
            return
        self._select_target(same, lambda t: self._do_knife(player, t), player)

    def _do_knife(self, player: Player, target: Player):
        msg = target.take_damage(1.0, player.name)
        self.log(f"🔪 {player.name} 砍 {target.name}！{msg}")
        self.use_step(player)

    # 盾
    def action_forge_shield(self, player: Player):
        player.shield_forged = True
        self.log(f"🛡️ {player.name} 炼盾...")
        self.use_step(player)

    def action_take_shield(self, player: Player):
        player.add_item("盾")
        self.log(f"🛡️ {player.name} 取盾！")
        self.use_step(player)

    def action_raise_shield(self, player: Player):
        player.shield_active = True
        self.log(f"🛡️ {player.name} 架盾！")
        self.use_step(player)

    def action_upgrade_shield(self, player: Player):
        player.shield_upgraded = True
        self.log(f"🛡️⬆ 盾升级！可架盾移动")
        self.use_step(player)

    def action_enchant_shield(self, player: Player):
        player.shield_enchanted = True
        self.log(f"🛡️✨ 盾附魔！防魔法")
        self.use_step(player)

    def action_upgrade_glove(self, player: Player):
        player.remove_item("拳套")
        player.glove_upgraded = True
        player.add_item("电击拳套")
        self.log(f"⚡ 升级为电击拳套！")
        self.use_step(player)

    # 魔法屋
    def action_forge_poison(self, player: Player):
        player.add_item("毒药")
        self.log(f"☠️ {player.name} 炼毒")
        self.use_step(player)

    def action_throw_poison(self, player: Player):
        locs = list(Location)
        self.clear_actions()
        tk.Label(self.action_frame, text="☠️ 扔到哪个位置：",
                 font=("微软雅黑", 12), fg="white", bg="#252535").pack(pady=10)
        for loc in locs:
            players_there = self.game.get_players_at(loc)
            info = loc.value
            if players_there:
                info += f" ({', '.join(p.name for p in players_there)})"
            btn = tk.Button(self.action_frame, text=f"☠️ {info}",
                            font=("微软雅黑", 11),
                            bg="#5c3d5c", fg="white", width=28,
                            cursor="hand2",
                            command=lambda l=loc: self._do_throw_poison(player, l))
            btn.pack(pady=3)
        tk.Button(self.action_frame, text="↩️ 取消",
                  font=("微软雅黑", 10), bg="#555", fg="white",
                  command=lambda: self.show_actions(player)).pack(pady=10)

    def _do_throw_poison(self, player: Player, loc: Location):
        player.remove_item("毒药")
        pid = self.game.next_poison_id()
        self.game.poisons[pid] = {
            "location": loc, "owner": player.name,
            "damage_dealt": 0.0, "layers": {}
        }
        self.log(f"☠️ {player.name} 向 {loc.value} 扔毒药！")
        self.use_step(player)

    def action_use_chance(self, player: Player):
        remaining = player.steps_this_turn - player.steps_used
        if remaining <= 0:
            messagebox.showinfo("提示", "没有剩余步数")
            return
        player.remove_item("机会药水")
        player.banked_steps += remaining
        player.steps_used = player.steps_this_turn
        self.log(f"💰 储存{remaining}步 (总:{player.banked_steps})")
        self.steps_label.config(text="👣 剩余步数: 0")
        self.finish_player_turn(player)

    def action_withdraw_steps(self, player: Player):
        amt = simpledialog.askinteger("提取步数",
                                      f"可提取: {player.banked_steps}",
                                      minvalue=1,
                                      maxvalue=player.banked_steps,
                                      parent=self.root)
        if amt:
            player.banked_steps -= amt
            player.steps_this_turn += amt
            self.log(f"💰 提取{amt}步")
            self.show_actions(player)

    def action_use_lucky(self, player: Player):
        player.remove_item("幸运药水")
        player.lucky_turns_left += 3
        self.log(f"🍀 {player.name} 幸运3回合！")
        self.use_step(player)

    # 机械屋
    def action_charge_railgun(self, player: Player):
        player.railguns_charged += 1
        self.log(f"⚡ 电磁炮充能！(已充:{player.railguns_charged})")
        self.use_step(player)

    def action_fire_railgun(self, player: Player):
        neighbors = ADJACENT_MAP[player.location] + [player.location]
        self.clear_actions()
        tk.Label(self.action_frame, text="💥 电磁炮目标位置：",
                 font=("微软雅黑", 12), fg="white", bg="#252535").pack(pady=10)
        for loc in neighbors:
            players_there = self.game.get_players_at(loc)
            info = loc.value
            if players_there:
                info += f" ({', '.join(p.name for p in players_there)})"
            btn = tk.Button(self.action_frame, text=f"💥 {info}",
                            font=("微软雅黑", 11),
                            bg="#5c3d3d", fg="white", width=28,
                            cursor="hand2",
                            command=lambda l=loc: self._do_fire_railgun(player, l))
            btn.pack(pady=3)
        tk.Button(self.action_frame, text="↩️ 取消",
                  font=("微软雅黑", 10), bg="#555", fg="white",
                  command=lambda: self.show_actions(player)).pack(pady=10)

    def _do_fire_railgun(self, player: Player, loc: Location):
        player.railguns_charged -= 1
        targets = self.game.get_players_at(loc)
        for t in targets:
            msg = t.take_damage(0.5, player.name)
            t.stunned_until_turn = self.game.current_turn + 1
            self.log(f"💥 电磁炮击中 {t.name}！{msg} ⚡眩晕！")
        self.log(f"💥 电磁炮命中 {loc.value}！")
        self.use_step(player)

    def action_summon_mech(self, player: Player):
        if player.transformed_as:
            messagebox.showinfo("提示", "变身中不可召唤")
            return
        player.remove_item("机甲")
        player.mech_active = True
        player.mech_hp = 1.0
        player.mech_attacks_done = 0
        self.log(f"🤖 {player.name} 召唤机甲！")
        self.use_step(player)

    def action_mech_attack(self, player: Player):
        enemies = self.game.get_enemies_of(player)
        if not enemies:
            return
        self._select_target(enemies, lambda t: self._do_mech_attack(player, t), player)

    def _do_mech_attack(self, player: Player, target: Player):
        needed = max(3 - player.mech_attacks_done, 0)
        self.log(f"🤖 飞砍 {target.name}！需判定{needed}次")
        success = True
        for _ in range(needed):
            a = random.choice(list(RPS))
            d = random.choice(list(RPS))
            if not rps_win(a, d):
                success = False
                break
        if success or needed == 0:
            player.location = target.location
            msg = target.take_damage(1.0, player.name)
            self.log(f"✅ 飞砍成功！{msg}")
        else:
            self.log("❌ 飞砍失败")
        player.mech_attacks_done += 1
        self.use_step(player)

    # 召唤器
    def action_charge_summoner(self, player: Player):
        if player.transformed_as:
            messagebox.showinfo("提示", "变身中不可充能")
            return
        player.summoner_energy += 1
        self.log(f"⚡ 召唤器 +1 (总:{player.summoner_energy})")
        self.use_step(player)

    def action_transform_taiyi(self, player: Player):
        player.summoner_energy -= 5
        player.transformed_as = "太乙真人"
        player.transform_hp = 1.0
        player.speed = 2
        self.log(f"🧙 {player.name} 变身太乙真人！")
        self.use_step(player)

    def action_transform_guanyu(self, player: Player):
        player.summoner_energy -= 10
        player.transformed_as = "关羽"
        player.transform_hp = 1.0
        player.speed = 2
        self.log(f"⚔️ {player.name} 变身关羽！")
        self.use_step(player)

    def action_guanyu_attack(self, player: Player):
        enemies = self.game.get_enemies_of(player)
        if not enemies:
            return
        self._select_target(enemies, lambda t: self._do_guanyu(player, t), player)

    def _do_guanyu(self, player: Player, target: Player):
        msg = target.take_damage(1.0, player.name)
        player.location = target.location
        self.log(f"⚔️ 关羽斩 {target.name}！{msg}")
        self.use_step(player)

    def action_revert_transform(self, player: Player):
        if player.transformed_as == "太乙真人":
            player.summoner_energy += 5
        player.transformed_as = None
        player.transform_hp = 0
        player.speed = 1
        self.log(f"🔄 {player.name} 恢复人形")
        self.use_step(player)

    # ============================================================
    # 辅助工具
    # ============================================================

    def _select_target(self, targets: List[Player], callback, player: Player):
        """选择目标"""
        self.clear_actions()
        tk.Label(self.action_frame, text="🎯 选择目标：",
                 font=("微软雅黑", 12), fg="white", bg="#252535").pack(pady=10)
        for t in targets:
            btn = tk.Button(self.action_frame,
                            text=f"👤 {t.name} ({t.location.value} HP:{t.hp})",
                            font=("微软雅黑", 11),
                            bg="#5c3d3d", fg="white", width=28,
                            cursor="hand2",
                            command=lambda target=t: callback(target))
            btn.pack(pady=3)
        tk.Button(self.action_frame, text="↩️ 取消",
                  font=("微软雅黑", 10), bg="#555", fg="white",
                  command=lambda: self.show_actions(player)).pack(pady=10)

    def process_poison(self):
        """处理毒药效果"""
        for pid, poison in list(self.game.poisons.items()):
            loc = poison["location"]
            owner = poison["owner"]
            for p in self.game.get_players_at(loc):
                if p.name == owner:
                    continue
                if p.shield_active and p.shield_enchanted:
                    continue
                layers = poison["layers"].get(p.name, 0) + 1
                poison["layers"][p.name] = layers
                self.log(f"☠️ {p.name} 中毒层数:{layers}")
                if layers >= 3:
                    msg = p.take_damage(0.5, owner, is_magic=True)
                    self.log(f"☠️ 毒发！{msg}")
                    poison["damage_dealt"] += 0.5
                    poison["layers"][p.name] = 0
                    if poison["damage_dealt"] >= 1.0:
                        self.log(f"☠️ 毒药消散")
                        del self.game.poisons[pid]
                        break

    def check_win(self) -> bool:
        """检查胜利"""
        alive = self.game.get_alive_players()
        if len(alive) == 1:
            winner = alive[0]
            messagebox.showinfo("🎉 游戏结束",
                                f"🏆 {winner.name} 获胜！")
            self.setup_start_screen()
            return True
        if len(alive) == 0:
            messagebox.showinfo("💀 游戏结束", "全员阵亡！")
            self.setup_start_screen()
            return True
        return False

    def clear_window(self):
        """清空窗口"""
        for widget in self.root.winfo_children():
            widget.destroy()


# ============================================================
# 启动
# ============================================================

def main():
    root = tk.Tk()
    app = ShopGameGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
