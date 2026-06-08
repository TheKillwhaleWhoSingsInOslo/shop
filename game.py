#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shop（去商店）游戏
一个多人回合制策略游戏，基于石头剪刀布的行动机制。
"""

import random
import os
import sys
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Callable, Tuple

# ============================================================
# 常量与枚举
# ============================================================

class Location(Enum):
    """地图位置"""
    CENTER = "中间"
    SHOP = "商店"
    MACHINE = "机械屋"
    IRON = "铁匠铺"
    MAGIC = "魔法屋"

# 地图邻接关系
ADJACENT_MAP: Dict[Location, List[Location]] = {
    Location.CENTER: [Location.SHOP, Location.MACHINE, Location.IRON, Location.MAGIC],
    Location.SHOP:    [Location.CENTER],
    Location.MACHINE: [Location.CENTER],
    Location.IRON:    [Location.CENTER],
    Location.MAGIC:   [Location.CENTER],
}

class RPS(Enum):
    """石头剪刀布"""
    ROCK = "石头"
    SCISSORS = "剪刀"
    PAPER = "布"

RPS_RULES = {
    (RPS.ROCK, RPS.SCISSORS): True,
    (RPS.SCISSORS, RPS.PAPER): True,
    (RPS.PAPER, RPS.ROCK): True,
}

def rps_win(a: RPS, b: RPS) -> bool:
    """a 是否赢 b"""
    if a == b:
        return False
    return RPS_RULES.get((a, b), False)

def rps_judge(attacker_name: str, defender_name: str) -> bool:
    """
    判定：双方出石头剪刀布，attacker 赢了返回 True。
    显示双方出的是什么。
    """
    print(f"\n  ⚡ 判定！{attacker_name} vs {defender_name}")
    choices = list(RPS)
    a_choice = random.choice(choices)
    d_choice = random.choice(choices)
    print(f"    {attacker_name} 出: {a_choice.value}")
    print(f"    {defender_name} 出: {d_choice.value}")
    result = rps_win(a_choice, d_choice)
    if result:
        print(f"    ✅ {attacker_name} 判定成功！")
    else:
        print(f"    ❌ {attacker_name} 判定失败！")
    return result


# ============================================================
# 物品与效果系统
# ============================================================

class ItemType(Enum):
    """物品类型"""
    GLOVE = "拳套"
    ELECTRIC_GLOVE = "电击拳套"
    SNIPER = "大狙"
    BULLET = "子弹"
    BLOW_DART = "吹箭"
    SUMMONER = "召唤器"
    KNIFE = "刀"
    FAMOUS_KNIFE = "名刀"
    SHIELD = "盾"
    UPGRADED_SHIELD = "升级盾"
    ENCHANTED_SHIELD = "附魔盾"
    FULL_SHIELD = "完全体盾"
    CHANCE_POTION = "机会药水"
    POISON = "毒药"
    LUCKY_POTION = "幸运药水"
    RAILGUN = "电磁炮"
    MECH = "机甲"


@dataclass
class Player:
    """玩家数据类"""
    name: str
    hp: float = 1.0
    location: Location = Location.CENTER
    speed: int = 1
    steps_this_turn: int = 0
    steps_used: int = 0

    # 物品
    inventory: Dict[str, int] = field(default_factory=dict)  # 物品名 -> 数量

    # 状态
    stunned_until_turn: int = -1  # 眩晕到哪个回合（含）
    lucky_turns_left: int = 0     # 幸运药水剩余回合
    poisoned_layers: Dict[int, int] = field(default_factory=dict)  # poison_id -> layers
    poison_owners: Dict[int, str] = field(default_factory=dict)    # poison_id -> owner_name

    # 武器状态
    glove_upgraded: bool = False  # 拳套是否升级为电击拳套
    sniper_aimed_at: Optional[str] = None  # 大狙瞄准目标
    sniper_bullets_loaded: int = 0  # 大狙已装子弹数
    blow_dart_hits: int = 0  # 吹箭连续命中次数

    # 召唤器
    summoner_energy: int = 0
    transformed_as: Optional[str] = None  # "taiyi" / "guanyu"
    transform_hp: float = 0

    # 刀
    knife_forged: bool = False       # 是否已炼刀
    knife_upgraded: bool = False     # 是否升级为名刀
    famous_knife_used: bool = False  # 名刀抵挡是否已用（每局一次）

    # 盾
    shield_forged: bool = False
    shield_upgraded: bool = False    # 可架盾移动
    shield_enchanted: bool = False   # 可格挡眩晕/毒
    shield_active: bool = False      # 是否架起

    # 电磁炮
    railguns_charged: int = 0        # 已充能的电磁炮数量

    # 机甲
    mech_active: bool = False
    mech_hp: float = 0
    mech_attacks_done: int = 0       # 机甲攻击次数（用于减少判定）

    # 机会药水
    banked_steps: int = 0

    # 毒药计数
    _next_poison_id: int = 0

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

    def take_damage(self, amount: float, game_state: 'GameState',
                    attacker_name: str = "", is_magic: bool = False) -> str:
        """
        受到伤害，按优先级处理。
        返回描述文字。
        """
        remaining = amount
        messages = []

        # 优先级1：盾
        if self.shield_active:
            if is_magic and not self.shield_enchanted:
                messages.append(f"🛡️ {self.name} 的盾无法格挡魔法效果！")
            else:
                messages.append(f"🛡️ {self.name} 的盾抵挡了伤害！")
                if not self.shield_upgraded:
                    self.shield_active = False
                return "\n".join(messages)

        # 优先级2：变身（太乙真人/关羽）
        if self.transformed_as:
            if remaining >= self.transform_hp:
                remaining -= self.transform_hp
                messages.append(f"💥 {self.name} 的{self.transformed_as}形态被击破！")
                self.transformed_as = None
                self.transform_hp = 0
                self.speed = 1
                if remaining <= 0:
                    return "\n".join(messages)
            else:
                self.transform_hp -= remaining
                messages.append(f"💢 {self.name} 的{self.transformed_as}形态承受了伤害！")
                return "\n".join(messages)

        # 优先级3：名刀
        if self.knife_upgraded and not self.famous_knife_used:
            messages.append(f"🗡️ {self.name} 的名刀抵挡了伤害！")
            self.famous_knife_used = True
            return "\n".join(messages)

        # 优先级4：机甲
        if self.mech_active:
            if remaining >= self.mech_hp:
                remaining -= self.mech_hp
                messages.append(f"🤖 {self.name} 的机甲被摧毁！")
                self.mech_active = False
                self.mech_hp = 0
                if remaining <= 0:
                    return "\n".join(messages)
            else:
                self.mech_hp -= remaining
                messages.append(f"🤖 {self.name} 的机甲承受了伤害！")
                return "\n".join(messages)

        # 优先级5：玩家本身
        self.hp -= remaining
        messages.append(f"💔 {self.name} 受到 {remaining} 点伤害！剩余生命: {self.hp}")
        if self.hp <= 0:
            messages.append(f"💀 {self.name} 被击败了！")
        return "\n".join(messages)


# ============================================================
# 游戏状态
# ============================================================

@dataclass
class GameState:
    """全局游戏状态"""
    players: List[Player]
    current_turn: int = 0
    current_player_idx: int = 0
    global_poison_id: int = 0
    brag_count: int = 0  # 装逼计数（共享池）
    brag_initiator: Optional[str] = None

    # 所有活跃的毒药
    poisons: Dict[int, dict] = field(default_factory=dict)  # poison_id -> {location, owner, damage_dealt}

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
# 地图显示
# ============================================================

def display_map(game: GameState):
    """显示地图及玩家位置"""
    print("\n" + "=" * 60)
    print("                     🗺️  地  图")
    print("=" * 60)

    locs = {
        Location.SHOP: "商店(shop)",
        Location.MACHINE: "机械屋(machine)",
        Location.CENTER: "中间",
        Location.IRON: "铁匠铺(iron)",
        Location.MAGIC: "魔法屋(magic)",
    }

    # 显示每个位置的玩家
    positions = {
        Location.SHOP: "",
        Location.MACHINE: "",
        Location.CENTER: "",
        Location.IRON: "",
        Location.MAGIC: "",
    }

    for p in game.players:
        status = ""
        if not p.is_alive():
            status = "💀"
        elif p.shield_active:
            status = "🛡️"
        if p.transformed_as == "taiyi":
            status += "🧙"
        elif p.transformed_as == "guanyu":
            status += "⚔️"
        if p.mech_active:
            status += "🤖"
        hp_str = f"{p.hp}HP" if p.transformed_as is None else f"{p.hp}/{p.transform_hp}T"
        positions[p.location] += f"  [{p.name} {hp_str}{status}]"

    print(f"""
                    {locs[Location.SHOP]}
                    {positions[Location.SHOP]}
                      |
                      |
    {locs[Location.MACHINE]} —— {locs[Location.CENTER]} —— {locs[Location.IRON]}
    {positions[Location.MACHINE]}     {positions[Location.CENTER]}     {positions[Location.IRON]}
                      |
                      |
                    {locs[Location.MAGIC]}
                    {positions[Location.MAGIC]}
    """)
    print("=" * 60)


def display_player_status(p: Player):
    """显示玩家详细状态"""
    print(f"\n📋 {p.name} 的状态:")
    print(f"   ❤️  生命: {p.hp}")
    print(f"   📍 位置: {p.location.value}")
    print(f"   🏃 速度: {p.speed}")
    print(f"   👣 剩余步数: {p.steps_this_turn - p.steps_used}")

    if p.stunned_until_turn >= 0:
        print(f"   ⚡ 眩晕中...")

    if p.lucky_turns_left > 0:
        print(f"   🍀 幸运: {p.lucky_turns_left} 回合")

    if p.banked_steps > 0:
        print(f"   💰 储存步数: {p.banked_steps}")

    if p.shield_active:
        shield_desc = "🛡️ 盾(架起)"
        if p.shield_upgraded:
            shield_desc += "[可移动]"
        if p.shield_enchanted:
            shield_desc += "[防魔法]"
        print(f"   {shield_desc}")

    if p.transformed_as:
        print(f"   🔮 变身: {p.transformed_as} (HP:{p.transform_hp})")

    if p.mech_active:
        print(f"   🤖 机甲 (HP:{p.mech_hp})")

    if p.summoner_energy > 0:
        print(f"   ⚡ 召唤器能量: {p.summoner_energy}")

    if p.sniper_aimed_at:
        print(f"   🔫 瞄准: {p.sniper_aimed_at} | 子弹: {p.sniper_bullets_loaded}")

    if p.blow_dart_hits > 0:
        print(f"   🎯 吹箭连击: {p.blow_dart_hits}")

    if p.railguns_charged > 0:
        print(f"   💥 电磁炮(已充能): {p.railguns_charged}")

    if p.inventory:
        print(f"   🎒 物品: {dict(p.inventory)}")

    # 毒状态
    if p.poisoned_layers:
        for pid, layers in p.poisoned_layers.items():
            owner = p.poison_owners.get(pid, "未知")
            print(f"   ☠️  毒({owner}): {layers}层")


# ============================================================
# 核心行动系统
# ============================================================

def do_move(player: Player, game: GameState) -> bool:
    """移动一步"""
    display_map(game)
    print(f"\n🚶 {player.name} 移动 (当前位置: {player.location.value})")
    neighbors = ADJACENT_MAP[player.location]
    print("可到达的位置:")
    for i, loc in enumerate(neighbors):
        players_there = game.get_players_at(loc)
        info = f"{i+1}. {loc.value}"
        if players_there:
            info += f" (有: {', '.join(p.name for p in players_there)})"
        print(f"   {info}")

    choice = input("选择位置编号 (0取消): ").strip()
    if choice == "0":
        return False

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(neighbors):
            new_loc = neighbors[idx]
            # 检查是否可以架盾移动
            if player.shield_active and not player.shield_upgraded:
                print("🛡️ 盾未升级，移动后盾将收起。")
                player.shield_active = False

            # 大狙瞄准丢失
            if player.sniper_aimed_at:
                print("🔫 移动导致瞄准丢失！")
                player.sniper_aimed_at = None

            player.location = new_loc
            print(f"✅ {player.name} 移动到 {new_loc.value}")
            return True
    except ValueError:
        pass
    return False


def do_kick(player: Player, game: GameState):
    """踢人：将同位置的人踢到1格以外"""
    same_loc = [p for p in game.get_players_at(player.location)
                if p.name != player.name]
    if not same_loc:
        print("❌ 当前位置没有其他人可以踢。")
        return

    print("\n👢 选择要踢的人:")
    for i, p in enumerate(same_loc):
        print(f"   {i+1}. {p.name}")

    choice = input("选择 (0取消): ").strip()
    if choice == "0":
        return

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(same_loc):
            target = same_loc[idx]
            neighbors = ADJACENT_MAP[player.location]
            print("踢到哪个位置?")
            for i, loc in enumerate(neighbors):
                print(f"   {i+1}. {loc.value}")
            loc_choice = input("选择: ").strip()
            try:
                loc_idx = int(loc_choice) - 1
                if 0 <= loc_idx < len(neighbors):
                    target.location = neighbors[loc_idx]
                    print(f"👢 {player.name} 把 {target.name} 踢到了 {target.location.value}！")
                    if target.sniper_aimed_at:
                        target.sniper_aimed_at = None
            except ValueError:
                pass
    except ValueError:
        pass


def do_brag(player: Player, game: GameState):
    """装逼"""
    game.brag_count += 1
    print(f"😎 {player.name} 装了一个逼！(总逼数: {game.brag_count})")

    if game.brag_count >= 7:
        game.brag_count = 0
        print("\n⚡⚡⚡ 第七个逼！天雷滚滚！⚡⚡⚡")
        do_thunder(player, game)


def do_thunder(initiator: Player, game: GameState, damage: int = 1, round_num: int = 1):
    """雷劈"""
    enemies = game.get_enemies_of(initiator)
    if not enemies:
        print("没有敌人可劈。")
        return

    print(f"\n⚡ 第{round_num}轮雷劈！伤害: {damage}")
    for enemy in enemies:
        print(f"\n⚡ {initiator.name} 选择雷劈 {enemy.name}！")
        if rps_judge(initiator.name, enemy.name):
            msg = enemy.take_damage(damage, game, initiator.name)
            print(msg)
            if not enemy.is_alive():
                return
            return  # 劈中一个就结束
        else:
            print(f"❌ 没劈中 {enemy.name}！")

    # 所有敌人都没劈中
    print(f"\n😈 所有敌人都没被劈中！敌人反击！")
    if enemies:
        counter = random.choice(enemies)
        print(f"⚡ {counter.name} 反击雷劈 {initiator.name}！")
        if rps_judge(counter.name, initiator.name):
            msg = initiator.take_damage(damage, game, counter.name)
            print(msg)
        else:
            print(f"❌ 反击也没劈中！")

    # 如果一轮下来都没人受伤，重新发起
    all_alive = all(p.is_alive() for p in [initiator] + enemies)
    if all_alive:
        print("\n🔄 无人受伤，重新发起雷劈！")
        do_thunder(initiator, game, damage + 2, round_num + 1)


# ============================================================
# 商店物品
# ============================================================

def shop_buy_glove(player: Player, game: GameState):
    """购买拳套"""
    if player.location != Location.SHOP:
        print("❌ 你必须在商店才能购买拳套。")
        return
    player.add_item("拳套")
    print(f"🥊 {player.name} 购买了拳套！")

def shop_upgrade_glove(player: Player, game: GameState):
    """在铁匠铺升级拳套为电击拳套"""
    if player.location != Location.IRON:
        print("❌ 你必须在铁匠铺才能升级拳套。")
        return
    if not player.has_item("拳套"):
        print("❌ 你没有拳套。")
        return
    player.remove_item("拳套")
    player.glove_upgraded = True
    player.add_item("电击拳套")
    print(f"⚡ {player.name} 的拳套升级为电击拳套！")

def shop_use_glove(player: Player, game: GameState):
    """使用拳套攻击同位置敌人"""
    if not player.has_item("拳套") and not player.glove_upgraded:
        print("❌ 你没有拳套。")
        return

    same_loc = [p for p in game.get_players_at(player.location)
                if p.name != player.name]
    if not same_loc:
        print("❌ 当前位置没有敌人。")
        return

    print("\n👊 选择攻击目标:")
    for i, p in enumerate(same_loc):
        print(f"   {i+1}. {p.name}")
    choice = input("选择 (0取消): ").strip()
    if choice == "0":
        return

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(same_loc):
            target = same_loc[idx]
            print(f"\n🥊 {player.name} 用拳套攻击 {target.name}！")
            if rps_judge(player.name, target.name):
                msg = target.take_damage(1.0, game, player.name)
                print(msg)
            else:
                if player.glove_upgraded:
                    print(f"⚡ 电击拳套！{target.name} 被眩晕一回合！")
                    target.stunned_until_turn = game.current_turn + 1
    except ValueError:
        pass


def shop_buy_sniper(player: Player, game: GameState):
    """购买大狙"""
    if player.location != Location.SHOP:
        print("❌ 你必须在商店才能购买大狙。")
        return
    player.add_item("大狙")
    print(f"🔫 {player.name} 购买了大狙！")

def shop_buy_bullet(player: Player, game: GameState):
    """购买子弹"""
    if player.location != Location.SHOP:
        print("❌ 你必须在商店才能购买子弹。")
        return
    if not player.has_item("大狙"):
        print("❌ 你需要先有大狙。")
        return
    player.add_item("子弹")
    print(f"🔸 {player.name} 购买了一颗子弹！")

def shop_load_bullet(player: Player, game: GameState):
    """装弹"""
    if not player.has_item("大狙"):
        print("❌ 你没有大狙。")
        return
    if not player.has_item("子弹"):
        print("❌ 你没有子弹。")
        return
    player.remove_item("子弹")
    player.sniper_bullets_loaded += 1
    print(f"🔫 {player.name} 装了一颗子弹 (已装: {player.sniper_bullets_loaded})")

def shop_aim_sniper(player: Player, game: GameState):
    """瞄准"""
    if not player.has_item("大狙"):
        print("❌ 你没有大狙。")
        return
    enemies = game.get_enemies_of(player)
    if not enemies:
        print("❌ 没有可瞄准的敌人。")
        return

    print("\n🎯 选择瞄准目标:")
    for i, p in enumerate(enemies):
        print(f"   {i+1}. {p.name} (位置: {p.location.value})")
    choice = input("选择 (0取消): ").strip()
    if choice == "0":
        return

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(enemies):
            player.sniper_aimed_at = enemies[idx].name
            print(f"🎯 {player.name} 瞄准了 {enemies[idx].name}！")
    except ValueError:
        pass

def shop_sniper_shoot(player: Player, game: GameState):
    """开枪"""
    if not player.has_item("大狙"):
        print("❌ 你没有大狙。")
        return
    if player.sniper_bullets_loaded <= 0:
        print("❌ 没有装子弹。")
        return
    if player.sniper_aimed_at is None:
        print("❌ 没有瞄准目标。")
        return

    target = game.get_player_by_name(player.sniper_aimed_at)
    if target is None or not target.is_alive():
        print("❌ 目标已不存在。")
        player.sniper_aimed_at = None
        return

    player.sniper_bullets_loaded -= 1
    print(f"💥 {player.name} 向 {target.name} 开枪！")
    msg = target.take_damage(1.0, game, player.name)
    print(msg)
    player.sniper_aimed_at = None

def shop_sniper_melee(player: Player, game: GameState):
    """枪托攻击（咣）"""
    if not player.has_item("大狙"):
        print("❌ 你没有大狙。")
        return

    same_loc = [p for p in game.get_players_at(player.location)
                if p.name != player.name]
    if not same_loc:
        print("❌ 当前位置没有敌人。")
        return

    print("\n🔫 选择枪托攻击目标:")
    for i, p in enumerate(same_loc):
        print(f"   {i+1}. {p.name}")
    choice = input("选择 (0取消): ").strip()
    if choice == "0":
        return

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(same_loc):
            target = same_loc[idx]
            print(f"💢 {player.name} 用枪托砸 {target.name}！")
            msg = target.take_damage(0.5, game, player.name)
            print(msg)
    except ValueError:
        pass


def shop_buy_blow_dart(player: Player, game: GameState):
    """购买吹箭"""
    if player.location != Location.SHOP:
        print("❌ 你必须在商店才能购买吹箭。")
        return
    player.add_item("吹箭")
    print(f"🎯 {player.name} 购买了吹箭！")

def shop_use_blow_dart(player: Player, game: GameState):
    """使用吹箭"""
    if not player.has_item("吹箭"):
        print("❌ 你没有吹箭。")
        return

    enemies = game.get_enemies_of(player)
    if not enemies:
        print("❌ 没有敌人。")
        return

    print("\n🎯 选择吹箭目标:")
    for i, p in enumerate(enemies):
        print(f"   {i+1}. {p.name} (位置: {p.location.value})")
    choice = input("选择 (0取消): ").strip()
    if choice == "0":
        return

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(enemies):
            target = enemies[idx]
            print(f"\n💨 {player.name} 向 {target.name} 吹箭！")
            if rps_judge(player.name, target.name):
                player.blow_dart_hits += 1
                print(f"🎯 命中！连击数: {player.blow_dart_hits}")
                if player.blow_dart_hits >= 2:
                    msg = target.take_damage(1.0, game, player.name)
                    print(msg)
                    player.blow_dart_hits = 0
            else:
                print(f"❌ 未命中，连击中断！")
                player.blow_dart_hits = 0
    except ValueError:
        pass


def shop_buy_summoner(player: Player, game: GameState):
    """购买召唤器"""
    if player.location != Location.SHOP:
        print("❌ 你必须在商店才能购买召唤器。")
        return
    player.add_item("召唤器")
    print(f"📿 {player.name} 购买了召唤器！")

def shop_charge_summoner(player: Player, game: GameState):
    """为召唤器充能"""
    if not player.has_item("召唤器"):
        print("❌ 你没有召唤器。")
        return
    if player.transformed_as:
        print("❌ 变身状态下无法充能。")
        return
    player.summoner_energy += 1
    print(f"⚡ {player.name} 为召唤器充能 (能量: {player.summoner_energy})")

def shop_transform_taiyi(player: Player, game: GameState):
    """变身太乙真人"""
    if not player.has_item("召唤器"):
        print("❌ 你没有召唤器。")
        return
    if player.summoner_energy < 5:
        print(f"❌ 能量不足 (需要5, 当前{player.summoner_energy})")
        return
    if player.transformed_as:
        print("❌ 你已经处于变身状态。")
        return

    player.summoner_energy -= 5
    player.transformed_as = "太乙真人"
    player.transform_hp = 1.0
    player.speed = 2
    print(f"🧙 {player.name} 变身太乙真人！速度2，可在魔法屋直接获得毒药！")

def shop_transform_guanyu(player: Player, game: GameState):
    """变身关羽"""
    if not player.has_item("召唤器"):
        print("❌ 你没有召唤器。")
        return
    if player.summoner_energy < 10:
        print(f"❌ 能量不足 (需要10, 当前{player.summoner_energy})")
        return
    if player.transformed_as:
        print("❌ 你已经处于变身状态。")
        return

    player.summoner_energy -= 10
    player.transformed_as = "关羽"
    player.transform_hp = 1.0
    player.speed = 2
    print(f"⚔️ {player.name} 变身关羽！速度2！")

def shop_guanyu_attack(player: Player, game: GameState):
    """关羽攻击"""
    if player.transformed_as != "关羽":
        print("❌ 你不是关羽形态。")
        return

    enemies = game.get_enemies_of(player)
    if not enemies:
        print("❌ 没有敌人。")
        return

    print("\n⚔️ 关羽攻击模式:")
    print("   1. 单体攻击 (伤害1点 + 移动到目标位置)")
    print("   2. 范围攻击 (对一个位置所有人判定一次伤害)")
    mode = input("选择 (0取消): ").strip()

    if mode == "1":
        print("\n选择目标:")
        for i, p in enumerate(enemies):
            print(f"   {i+1}. {p.name} (位置: {p.location.value})")
        choice = input("选择: ").strip()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(enemies):
                target = enemies[idx]
                msg = target.take_damage(1.0, game, player.name)
                print(msg)
                player.location = target.location
                print(f"⚔️ 关羽移动到 {target.location.value}！")
        except ValueError:
            pass

    elif mode == "2":
        locations = set(p.location for p in enemies)
        loc_list = list(locations)
        print("\n选择位置:")
        for i, loc in enumerate(loc_list):
            players_there = game.get_players_at(loc)
            print(f"   {i+1}. {loc.value} ({', '.join(p.name for p in players_there)})")
        choice = input("选择: ").strip()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(loc_list):
                target_loc = loc_list[idx]
                targets = game.get_players_at(target_loc)
                for t in targets:
                    if t.name != player.name:
                        if rps_judge(player.name, t.name):
                            msg = t.take_damage(1.0, game, player.name)
                            print(msg)
                        else:
                            print(f"❌ 对 {t.name} 判定失败")
                player.location = target_loc
                print(f"⚔️ 关羽移动到 {target_loc.value}！")
        except ValueError:
            pass

def shop_revert_transform(player: Player, game: GameState):
    """取消变身"""
    if not player.transformed_as:
        print("❌ 你没有变身。")
        return
    if player.transformed_as == "太乙真人":
        player.summoner_energy += 5
    print(f"🔄 {player.name} 恢复人形态，返还能量。")
    player.transformed_as = None
    player.transform_hp = 0
    player.speed = 1


# ============================================================
# 铁匠铺物品
# ============================================================

def iron_forge_knife(player: Player, game: GameState):
    """炼刀"""
    if player.location != Location.IRON:
        print("❌ 你必须在铁匠铺才能炼刀。")
        return
    if player.knife_forged:
        print("❌ 你已经炼过刀了。")
        return
    player.knife_forged = True
    print(f"🔪 {player.name} 开始炼刀...")

def iron_take_knife(player: Player, game: GameState):
    """取刀"""
    if player.location != Location.IRON:
        print("❌ 你必须在铁匠铺才能取刀。")
        return
    if not player.knife_forged:
        print("❌ 你还没有炼刀。")
        return
    if player.has_item("刀"):
        print("❌ 你已经取过刀了。")
        return
    player.add_item("刀")
    print(f"🔪 {player.name} 取到了刀！")

def iron_upgrade_knife(player: Player, game: GameState):
    """升级刀为名刀"""
    if player.location != Location.IRON:
        print("❌ 你必须在铁匠铺才能升级刀。")
        return
    if not player.has_item("刀"):
        print("❌ 你没有刀。")
        return
    if player.knife_upgraded:
        print("❌ 刀已经升级过了。")
        return
    player.remove_item("刀")
    player.knife_upgraded = True
    player.add_item("名刀")
    print(f"🗡️ {player.name} 的刀升级为名刀！5回合后可抵挡一次伤害。")

def iron_use_knife(player: Player, game: GameState):
    """用刀攻击同位置敌人"""
    if not player.has_item("刀") and not player.has_item("名刀"):
        print("❌ 你没有刀。")
        return

    same_loc = [p for p in game.get_players_at(player.location)
                if p.name != player.name]
    if not same_loc:
        print("❌ 当前位置没有敌人。")
        return

    print("\n🔪 选择攻击目标:")
    for i, p in enumerate(same_loc):
        print(f"   {i+1}. {p.name}")
    choice = input("选择 (0取消): ").strip()
    if choice == "0":
        return

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(same_loc):
            target = same_loc[idx]
            print(f"🔪 {player.name} 用刀攻击 {target.name}！")
            msg = target.take_damage(1.0, game, player.name)
            print(msg)
    except ValueError:
        pass


def iron_forge_shield(player: Player, game: GameState):
    """炼盾"""
    if player.location != Location.IRON:
        print("❌ 你必须在铁匠铺才能炼盾。")
        return
    if player.shield_forged:
        print("❌ 你已经炼过盾了。")
        return
    player.shield_forged = True
    print(f"🛡️ {player.name} 开始炼盾...")

def iron_take_shield(player: Player, game: GameState):
    """取盾"""
    if player.location != Location.IRON:
        print("❌ 你必须在铁匠铺才能取盾。")
        return
    if not player.shield_forged:
        print("❌ 你还没有炼盾。")
        return
    if player.has_item("盾"):
        print("❌ 你已经取过盾了。")
        return
    player.add_item("盾")
    print(f"🛡️ {player.name} 取到了盾！")

def iron_raise_shield(player: Player, game: GameState):
    """架盾"""
    if not player.has_item("盾"):
        print("❌ 你没有盾。")
        return
    if player.shield_active:
        print("❌ 盾已经架起了。")
        return
    player.shield_active = True
    print(f"🛡️ {player.name} 架起了盾！")

def iron_upgrade_shield(player: Player, game: GameState):
    """升级盾（可架盾移动）"""
    if player.location != Location.IRON:
        print("❌ 你必须在铁匠铺才能升级盾。")
        return
    if not player.has_item("盾"):
        print("❌ 你没有盾。")
        return
    if player.shield_upgraded:
        print("❌ 盾已经升级过了。")
        return
    player.shield_upgraded = True
    print(f"🛡️⬆ {player.name} 的盾升级了！现在可以架盾移动。")

def iron_enchant_shield(player: Player, game: GameState):
    """附魔盾（格挡眩晕/毒）"""
    if player.location != Location.IRON:
        print("❌ 你必须在铁匠铺才能附魔盾。")
        return
    if not player.has_item("盾"):
        print("❌ 你没有盾。")
        return
    if player.shield_enchanted:
        print("❌ 盾已经附魔过了。")
        return
    player.shield_enchanted = True
    print(f"🛡️✨ {player.name} 的盾附魔了！现在可以格挡魔法效果。")


# ============================================================
# 魔法屋物品
# ============================================================

def magic_buy_chance(player: Player, game: GameState):
    """购买机会药水"""
    if player.location != Location.MAGIC:
        print("❌ 你必须在魔法屋才能购买机会药水。")
        return
    player.add_item("机会药水")
    print(f"🧪 {player.name} 购买了机会药水！")

def magic_use_chance(player: Player, game: GameState):
    """使用机会药水"""
    if not player.has_item("机会药水"):
        print("❌ 你没有机会药水。")
        return
    # 将当前剩余步数储存
    remaining = player.steps_this_turn - player.steps_used
    if remaining <= 0:
        print("❌ 你没有剩余步数可以储存。")
        return
    player.remove_item("机会药水")
    player.banked_steps += remaining
    player.steps_used = player.steps_this_turn  # 消耗完当前步数
    print(f"💰 {player.name} 使用了机会药水！储存了 {remaining} 步 (总储存: {player.banked_steps})")

def magic_withdraw_steps(player: Player, game: GameState):
    """提取储存的步数"""
    if player.banked_steps <= 0:
        print("❌ 你没有储存的步数。")
        return
    print(f"💰 可提取步数: {player.banked_steps}")
    amount = input("提取多少步? ").strip()
    try:
        amt = int(amount)
        if 1 <= amt <= player.banked_steps:
            player.banked_steps -= amt
            player.steps_this_turn += amt
            print(f"💰 {player.name} 提取了 {amt} 步！")
    except ValueError:
        pass


def magic_forge_poison(player: Player, game: GameState):
    """炼毒"""
    if player.location != Location.MAGIC:
        print("❌ 你必须在魔法屋才能炼毒。")
        return
    # 太乙真人可以直接获得
    if player.transformed_as == "太乙真人":
        player.add_item("毒药")
        print(f"🧙 太乙真人直接获得了毒药！")
        return
    player.add_item("毒药")
    print(f"☠️ {player.name} 炼制了毒药！")

def magic_throw_poison(player: Player, game: GameState):
    """扔毒药"""
    if not player.has_item("毒药"):
        print("❌ 你没有毒药。")
        return

    locations = [Location.CENTER, Location.SHOP, Location.MACHINE,
                 Location.IRON, Location.MAGIC]
    print("\n☠️ 选择扔毒药的位置:")
    for i, loc in enumerate(locations):
        players_there = game.get_players_at(loc)
        info = f"{i+1}. {loc.value}"
        if players_there:
            info += f" (有: {', '.join(p.name for p in players_there)})"
        print(f"   {info}")

    choice = input("选择 (0取消): ").strip()
    if choice == "0":
        return

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(locations):
            target_loc = locations[idx]
            player.remove_item("毒药")
            pid = game.next_poison_id()
            game.poisons[pid] = {
                "location": target_loc,
                "owner": player.name,
                "damage_dealt": 0.0,
                "layers": {},  # player_name -> layers
            }
            print(f"☠️ {player.name} 向 {target_loc.value} 扔了毒药！(ID:{pid})")
    except ValueError:
        pass


def magic_buy_lucky(player: Player, game: GameState):
    """购买幸运药水"""
    if player.location != Location.MAGIC:
        print("❌ 你必须在魔法屋才能购买幸运药水。")
        return
    player.add_item("幸运药水")
    print(f"🍀 {player.name} 购买了幸运药水！")

def magic_use_lucky(player: Player, game: GameState):
    """使用幸运药水"""
    if not player.has_item("幸运药水"):
        print("❌ 你没有幸运药水。")
        return
    player.remove_item("幸运药水")
    player.lucky_turns_left += 3
    print(f"🍀 {player.name} 喝下幸运药水！接下来 {player.lucky_turns_left} 回合步数翻倍！")


# ============================================================
# 机械屋物品
# ============================================================

def machine_buy_railgun(player: Player, game: GameState):
    """购买电磁炮"""
    if player.location != Location.MACHINE:
        print("❌ 你必须在机械屋才能购买电磁炮。")
        return
    player.add_item("电磁炮")
    print(f"💥 {player.name} 购买了电磁炮！")

def machine_charge_railgun(player: Player, game: GameState):
    """充能电磁炮"""
    if not player.has_item("电磁炮"):
        print("❌ 你没有电磁炮。")
        return
    # 检查是否有未充能的电磁炮
    uncharged = player.inventory.get("电磁炮", 0) - player.railguns_charged
    if uncharged <= 0:
        print("❌ 所有电磁炮都已充能。")
        return
    player.railguns_charged += 1
    print(f"⚡ {player.name} 为电磁炮充能！(已充能: {player.railguns_charged})")

def machine_fire_railgun(player: Player, game: GameState):
    """发射电磁炮"""
    if player.railguns_charged <= 0:
        print("❌ 没有已充能的电磁炮。")
        return

    # 选择距离1格的位置
    neighbors = ADJACENT_MAP[player.location] + [player.location]
    print("\n💥 选择开炮位置 (距离1格):")
    for i, loc in enumerate(neighbors):
        players_there = game.get_players_at(loc)
        info = f"{i+1}. {loc.value}"
        if players_there:
            info += f" (有: {', '.join(p.name for p in players_there)})"
        print(f"   {info}")

    choice = input("选择 (0取消): ").strip()
    if choice == "0":
        return

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(neighbors):
            target_loc = neighbors[idx]
            player.railguns_charged -= 1
            print(f"💥 {player.name} 向 {target_loc.value} 发射电磁炮！")
            targets = game.get_players_at(target_loc)
            for t in targets:
                msg = t.take_damage(0.5, game, player.name)
                print(msg)
                t.stunned_until_turn = game.current_turn + 1
                print(f"⚡ {t.name} 被眩晕一回合！")
    except ValueError:
        pass


def machine_buy_mech(player: Player, game: GameState):
    """购买机甲"""
    if player.location != Location.MACHINE:
        print("❌ 你必须在机械屋才能购买机甲。")
        return
    if player.mech_active:
        print("❌ 你已经有机甲了。")
        return
    player.add_item("机甲")
    print(f"🤖 {player.name} 购买了机甲！")

def machine_summon_mech(player: Player, game: GameState):
    """召唤机甲"""
    if not player.has_item("机甲"):
        print("❌ 你没有机甲。")
        return
    if player.mech_active:
        print("❌ 机甲已激活。")
        return
    if player.transformed_as:
        print("❌ 变身状态下不能使用机甲。")
        return
    player.remove_item("机甲")
    player.mech_active = True
    player.mech_hp = 1.0
    player.mech_attacks_done = 0
    print(f"🤖 {player.name} 召唤了机甲！")

def machine_mech_attack(player: Player, game: GameState):
    """机甲攻击【飞砍】"""
    if not player.mech_active:
        print("❌ 机甲未激活。")
        return

    enemies = game.get_enemies_of(player)
    if not enemies:
        print("❌ 没有敌人。")
        return

    print("\n🤖 选择飞砍目标:")
    for i, p in enumerate(enemies):
        print(f"   {i+1}. {p.name} (位置: {p.location.value})")
    choice = input("选择 (0取消): ").strip()
    if choice == "0":
        return

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(enemies):
            target = enemies[idx]
            # 判定次数 = max(3 - mech_attacks_done, 0)
            needed = max(3 - player.mech_attacks_done, 0)
            print(f"🤖 机甲飞砍 {target.name}！需要判定 {needed} 次")

            success = True
            for j in range(needed):
                if not rps_judge(f"{player.name}(机甲)", target.name):
                    success = False
                    break

            if success or needed == 0:
                player.location = target.location
                msg = target.take_damage(1.0, game, player.name)
                print(msg)
                print(f"🤖 机甲移动到 {target.location.value}！")
            else:
                print(f"❌ 飞砍失败！")

            player.mech_attacks_done += 1
            print(f"🤖 机甲攻击次数: {player.mech_attacks_done} (下次需判定 {max(3 - player.mech_attacks_done, 0)} 次)")
    except ValueError:
        pass


# ============================================================
# 回合系统
# ============================================================

def rock_paper_scissors_step(players: List[Player]) -> Dict[str, int]:
    """
    石头剪刀布决定步数。
    返回每个玩家获得的步数。
    """
    print("\n" + "=" * 60)
    print("                 ✊✌️✋  石头剪刀布！")
    print("=" * 60)

    choices: Dict[str, RPS] = {}
    for p in players:
        if p.is_stunned(game_state_ref[0].current_turn):
            print(f"  ⚡ {p.name} 被眩晕，无法参与！")
            continue
        print(f"\n  {p.name}，请选择:")
        print("    1. 石头 ✊")
        print("    2. 剪刀 ✌️")
        print("    3. 布 ✋")
        c = input("  你的选择: ").strip()
        if c == "1":
            choices[p.name] = RPS.ROCK
        elif c == "2":
            choices[p.name] = RPS.SCISSORS
        else:
            choices[p.name] = RPS.PAPER

    # 显示所有人的选择
    print("\n  结果:")
    for name, choice in choices.items():
        print(f"    {name}: {choice.value}")

    # 计算赢的次数 = 步数（有多少人输给你就获得几步，平局0步）
    steps: Dict[str, int] = {}
    names = list(choices.keys())
    for name in names:
        wins = 0
        for other in names:
            if name != other:
                if rps_win(choices[name], choices[other]):
                    wins += 1
        steps[name] = wins

    for name, s in steps.items():
        # 幸运药水翻倍
        player = next(p for p in players if p.name == name)
        if player.lucky_turns_left > 0:
            s *= 2
            print(f"    🍀 {name} 幸运翻倍！")
        steps[name] = s
        print(f"    {name} 获得 {s} 步")

    return steps


# 全局引用（用于眩晕检查）
game_state_ref: List[Optional[GameState]] = [None]


def process_poison_effects(game: GameState):
    """处理毒药效果"""
    for pid, poison in list(game.poisons.items()):
        loc = poison["location"]
        owner_name = poison["owner"]
        players_at_loc = game.get_players_at(loc)

        for p in players_at_loc:
            if p.name == owner_name:
                continue
            # 附魔盾无视毒
            if p.shield_active and p.shield_enchanted:
                continue

            # 增加层数
            current = poison["layers"].get(p.name, 0) + 1
            poison["layers"][p.name] = current
            p.poisoned_layers[pid] = current
            p.poison_owners[pid] = owner_name
            print(f"☠️ {p.name} 在 {loc.value} 中毒层数: {current}")

            if current >= 3:
                msg = p.take_damage(0.5, game, owner_name, is_magic=True)
                print(msg)
                poison["damage_dealt"] += 0.5
                poison["layers"][p.name] = 0
                p.poisoned_layers[pid] = 0

                if poison["damage_dealt"] >= 1.0:
                    print(f"☠️ 毒药(ID:{pid})已造成足够伤害，消失了！")
                    del game.poisons[pid]
                    # 清理玩家毒状态
                    for pl in game.players:
                        pl.poisoned_layers.pop(pid, None)
                        pl.poison_owners.pop(pid, None)
                    break


def player_turn(player: Player, game: GameState, steps_this_round: Dict[str, int]):
    """单个玩家的回合"""
    if not player.is_alive():
        return

    # 眩晕检查
    if player.is_stunned(game.current_turn):
        print(f"\n⚡ {player.name} 被眩晕，跳过本回合！")
        player.stunned_until_turn = -1
        return

    # 召唤器自动充能
    if player.has_item("召唤器") and not player.transformed_as:
        player.summoner_energy += 1
        print(f"📿 {player.name} 的召唤器自动获得1点能量 (总: {player.summoner_energy})")

    # 从回合开始时的猜拳结果获取步数
    player.steps_this_turn = steps_this_round.get(player.name, 0)
    player.steps_used = 0

    print(f"\n{'='*60}")
    print(f"  🎮 {player.name} 的回合 (步数: {player.steps_this_turn})")
    print(f"{'='*60}")

    while player.steps_used < player.steps_this_turn and player.is_alive():
        display_map(game)
        display_player_status(player)
        remaining = player.steps_this_turn - player.steps_used
        print(f"\n⏳ 剩余步数: {remaining}")

        actions = get_available_actions(player, game)
        print("\n可选行动:")
        for i, (name, desc) in enumerate(actions):
            print(f"  {i+1:2d}. {name:<20s} {desc}")

        choice = input("\n选择行动 (0结束回合): ").strip()
        if choice == "0":
            break

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(actions):
                action_name = actions[idx][0]
                action_func = action_registry.get(action_name)
                if action_func:
                    if action_func(player, game):
                        player.steps_used += 1
                else:
                    print(f"❌ 未知行动: {action_name}")
        except ValueError:
            print("❌ 无效输入")

    # 回合结束处理
    if player.lucky_turns_left > 0:
        player.lucky_turns_left -= 1

    # 名刀计时（简化：名刀在升级后5回合可用）
    # 这里简化处理，名刀升级后立即可用抵挡


def get_available_actions(player: Player, game: GameState) -> List[Tuple[str, str]]:
    """获取当前可用的行动列表"""
    actions = []

    # 基本行动
    actions.append(("移动", "移动到相邻位置"))
    actions.append(("踢人", "将同位置的人踢走"))
    actions.append(("装逼", "娱乐玩法，积累逼数"))

    # 商店物品
    if player.location == Location.SHOP:
        actions.append(("购买拳套", "在商店购买拳套"))
        actions.append(("购买大狙", "在商店购买大狙"))
        actions.append(("购买吹箭", "在商店购买吹箭"))
        actions.append(("购买召唤器", "在商店购买召唤器"))

    if player.has_item("拳套") or player.glove_upgraded:
        actions.append(("使用拳套", "攻击同位置敌人"))
    if player.location == Location.IRON and player.has_item("拳套") and not player.glove_upgraded:
        actions.append(("升级拳套", "升级为电击拳套"))

    if player.has_item("大狙"):
        actions.append(("枪托攻击", "用枪托砸同位置敌人(0.5伤害)"))
        actions.append(("瞄准", "瞄准一个敌人"))
        actions.append(("开枪", "向瞄准的敌人开枪"))
        if player.location == Location.SHOP:
            actions.append(("购买子弹", "购买一颗子弹"))
        actions.append(("装弹", "装一颗子弹"))

    if player.has_item("吹箭"):
        actions.append(("使用吹箭", "向任意距离敌人吹箭"))

    if player.has_item("召唤器"):
        actions.append(("充能召唤器", "消耗一步为召唤器充能"))
        if player.summoner_energy >= 5 and not player.transformed_as:
            actions.append(("变身太乙真人", "消耗5能量变身"))
        if player.summoner_energy >= 10 and not player.transformed_as:
            actions.append(("变身关羽", "消耗10能量变身"))
    if player.transformed_as == "关羽":
        actions.append(("关羽攻击", "使用关羽技能攻击"))
    if player.transformed_as:
        actions.append(("取消变身", "恢复人形态"))

    # 铁匠铺
    if player.location == Location.IRON:
        if not player.knife_forged:
            actions.append(("炼刀", "在铁匠铺炼刀"))
        if player.knife_forged and not player.has_item("刀") and not player.knife_upgraded:
            actions.append(("取刀", "取出炼好的刀"))
        if player.has_item("刀") and not player.knife_upgraded:
            actions.append(("升级刀", "升级为名刀"))
        if not player.shield_forged:
            actions.append(("炼盾", "在铁匠铺炼盾"))
        if player.shield_forged and not player.has_item("盾"):
            actions.append(("取盾", "取出炼好的盾"))
        if player.has_item("盾") and not player.shield_upgraded:
            actions.append(("升级盾", "升级盾(可架盾移动)"))
        if player.has_item("盾") and not player.shield_enchanted:
            actions.append(("附魔盾", "附魔盾(格挡魔法)"))

    if player.has_item("刀") or player.has_item("名刀"):
        actions.append(("使用刀", "攻击同位置敌人"))
    if player.has_item("盾"):
        if not player.shield_active:
            actions.append(("架盾", "架起盾进入格挡状态"))

    # 魔法屋
    if player.location == Location.MAGIC:
        actions.append(("购买机会药水", "购买机会药水"))
        actions.append(("炼毒", "炼制/获得毒药"))
        actions.append(("购买幸运药水", "购买幸运药水"))

    if player.has_item("机会药水"):
        actions.append(("使用机会药水", "储存当前剩余步数"))
    if player.banked_steps > 0:
        actions.append(("提取步数", "提取储存的步数"))
    if player.has_item("毒药"):
        actions.append(("扔毒药", "向一个位置扔毒药"))
    if player.has_item("幸运药水"):
        actions.append(("使用幸运药水", "接下来3回步数翻倍"))

    # 机械屋
    if player.location == Location.MACHINE:
        actions.append(("购买电磁炮", "购买电磁炮"))
        actions.append(("购买机甲", "购买机甲"))

    if player.has_item("电磁炮"):
        actions.append(("充能电磁炮", "为电磁炮充能"))
    if player.railguns_charged > 0:
        actions.append(("发射电磁炮", "向距离1格位置开炮"))

    if player.has_item("机甲") and not player.mech_active:
        actions.append(("召唤机甲", "召唤机甲"))
    if player.mech_active:
        actions.append(("机甲攻击", "飞砍敌人"))

    return actions


# 行动注册表
action_registry: Dict[str, Callable] = {}


def register_actions():
    """注册所有行动"""
    global action_registry
    action_registry = {
        "移动": lambda p, g: do_move(p, g),
        "踢人": lambda p, g: (do_kick(p, g), True)[1],
        "装逼": lambda p, g: (do_brag(p, g), True)[1],

        "购买拳套": lambda p, g: (shop_buy_glove(p, g), True)[1],
        "升级拳套": lambda p, g: (shop_upgrade_glove(p, g), True)[1],
        "使用拳套": lambda p, g: (shop_use_glove(p, g), True)[1],

        "购买大狙": lambda p, g: (shop_buy_sniper(p, g), True)[1],
        "购买子弹": lambda p, g: (shop_buy_bullet(p, g), True)[1],
        "装弹": lambda p, g: (shop_load_bullet(p, g), True)[1],
        "瞄准": lambda p, g: (shop_aim_sniper(p, g), True)[1],
        "开枪": lambda p, g: (shop_sniper_shoot(p, g), True)[1],
        "枪托攻击": lambda p, g: (shop_sniper_melee(p, g), True)[1],

        "购买吹箭": lambda p, g: (shop_buy_blow_dart(p, g), True)[1],
        "使用吹箭": lambda p, g: (shop_use_blow_dart(p, g), True)[1],

        "购买召唤器": lambda p, g: (shop_buy_summoner(p, g), True)[1],
        "充能召唤器": lambda p, g: (shop_charge_summoner(p, g), True)[1],
        "变身太乙真人": lambda p, g: (shop_transform_taiyi(p, g), True)[1],
        "变身关羽": lambda p, g: (shop_transform_guanyu(p, g), True)[1],
        "关羽攻击": lambda p, g: (shop_guanyu_attack(p, g), True)[1],
        "取消变身": lambda p, g: (shop_revert_transform(p, g), True)[1],

        "炼刀": lambda p, g: (iron_forge_knife(p, g), True)[1],
        "取刀": lambda p, g: (iron_take_knife(p, g), True)[1],
        "升级刀": lambda p, g: (iron_upgrade_knife(p, g), True)[1],
        "使用刀": lambda p, g: (iron_use_knife(p, g), True)[1],

        "炼盾": lambda p, g: (iron_forge_shield(p, g), True)[1],
        "取盾": lambda p, g: (iron_take_shield(p, g), True)[1],
        "架盾": lambda p, g: (iron_raise_shield(p, g), True)[1],
        "升级盾": lambda p, g: (iron_upgrade_shield(p, g), True)[1],
        "附魔盾": lambda p, g: (iron_enchant_shield(p, g), True)[1],

        "购买机会药水": lambda p, g: (magic_buy_chance(p, g), True)[1],
        "使用机会药水": lambda p, g: (magic_use_chance(p, g), True)[1],
        "提取步数": lambda p, g: (magic_withdraw_steps(p, g), True)[1],
        "炼毒": lambda p, g: (magic_forge_poison(p, g), True)[1],
        "扔毒药": lambda p, g: (magic_throw_poison(p, g), True)[1],
        "购买幸运药水": lambda p, g: (magic_buy_lucky(p, g), True)[1],
        "使用幸运药水": lambda p, g: (magic_use_lucky(p, g), True)[1],

        "购买电磁炮": lambda p, g: (machine_buy_railgun(p, g), True)[1],
        "充能电磁炮": lambda p, g: (machine_charge_railgun(p, g), True)[1],
        "发射电磁炮": lambda p, g: (machine_fire_railgun(p, g), True)[1],

        "购买机甲": lambda p, g: (machine_buy_mech(p, g), True)[1],
        "召唤机甲": lambda p, g: (machine_summon_mech(p, g), True)[1],
        "机甲攻击": lambda p, g: (machine_mech_attack(p, g), True)[1],
    }


# ============================================================
# 主游戏循环
# ============================================================

def check_win(game: GameState) -> Optional[Player]:
    """检查是否有玩家获胜"""
    alive = game.get_alive_players()
    if len(alive) == 1:
        return alive[0]
    if len(alive) == 0:
        return None
    return None


def main():
    """主函数"""
    print("=" * 60)
    print("        🏪  SHOP（去商店）")
    print("        一个多人回合制策略游戏")
    print("=" * 60)
    print("\n游戏规则概要:")
    print("  - 地图: 中间、商店、机械屋、铁匠铺、魔法屋")
    print("  - 在不同位置可以购买/炼制不同物品")
    print("  - 石头剪刀布决定步数，输的越多步数越多")
    print("  - 最后存活者获胜！")
    print()

    # 设置玩家
    while True:
        try:
            num = int(input("请输入玩家人数 (2-6): "))
            if 2 <= num <= 6:
                break
            print("❌ 人数必须在2-6之间")
        except ValueError:
            print("❌ 请输入数字")

    players = []
    for i in range(num):
        name = input(f"玩家{i+1}的名字: ").strip()
        if not name:
            name = f"玩家{i+1}"
        players.append(Player(name=name))

    game = GameState(players=players)
    game_state_ref[0] = game
    register_actions()

    print("\n🎮 游戏开始！所有玩家出生在「中间」")
    display_map(game)

    # 主循环
    max_turns = 100
    while game.current_turn < max_turns:
        game.current_turn += 1
        print(f"\n{'#'*60}")
        print(f"  🔄 第 {game.current_turn} 回合")
        print(f"{'#'*60}")

        # 处理毒药
        process_poison_effects(game)

        # 检查胜利条件
        winner = check_win(game)
        if winner:
            print(f"\n{'='*60}")
            print(f"  🎉 {winner.name} 获胜！")
            print(f"{'='*60}")
            break

        # 回合开始时统一猜拳（平局则重猜）
        alive_players = game.get_alive_players()
        while True:
            steps_this_round = rock_paper_scissors_step(alive_players)
            if any(s > 0 for s in steps_this_round.values()):
                break
            print("\n  🤝 全员平局！重新猜拳...")

        # 每个玩家行动
        for player in game.players:
            if not player.is_alive():
                continue
            if check_win(game):
                break
            player_turn(player, game, steps_this_round)

        # 再次检查胜利条件
        winner = check_win(game)
        if winner:
            print(f"\n{'='*60}")
            print(f"  🎉 {winner.name} 获胜！")
            print(f"{'='*60}")
            break

    if game.current_turn >= max_turns:
        print("\n⏰ 达到最大回合数！游戏结束。")

    print("\n感谢游玩 Shop（去商店）！")


if __name__ == "__main__":
    main()
