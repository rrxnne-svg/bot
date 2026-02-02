# -------------- bot.py (расширенная версия с админ-меню и улучшенными функциями) --------------
import discord, json, os, asyncio, re, traceback
from datetime import datetime, timedelta, timezone
from discord.ext import tasks
from discord import app_commands
from discord.ui import Button, View, Modal, TextInput, Select
import math

# ==================== НАСТРОЙКИ ====================
TOKEN = os.getenv("TOKEN")
GUILD_ID = 1430087806952411230
ADMIN_ROLES = ["dep.YAK", "Owner", "Leader"]
VIEW_ROLES = ["member", "Test", "Famlily", "Yak"]

# ID каналов
STATS_AVG_CHANNEL_ID = 1467543899643052312
STATS_KILLS_CHANNEL_ID = 1467543933209809076
CAPTS_LIST_CHANNEL_ID = 1467544000088117451
LOG_CHANNEL_ID = 1467564108973998315
ADMIN_PANEL_CHANNEL_ID = 1467757228189810799  # ID канала для админ-панели
WEEKLY_REPORT_CHANNEL_ID = 1467757665076776960  # Канал для недельных отчетов

# Московское время (UTC+3)
MSK_TZ = timezone(timedelta(hours=3))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

DB_STATS = "stats.json"
DB_CAPTS = "capts.json"
DB_SCORES = "scores.json"  # База данных для баллов

# ==================== УТИЛИТЫ ====================
def now_msk():
    """Получить текущее время по Москве (UTC+3)"""
    return datetime.now(timezone.utc).astimezone(MSK_TZ)

def load_stats() -> dict:
    try:
        with open(DB_STATS, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_stats(data: dict):
    with open(DB_STATS, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_capts() -> list:
    try:
        with open(DB_CAPTS, "r", encoding="utf-8") as f:
            capts = json.load(f) or []
            for capt in capts:
                if "date" in capt and isinstance(capt["date"], str):
                    try:
                        dt = datetime.fromisoformat(capt["date"].replace("Z", "+00:00"))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        capt["date"] = dt.astimezone(MSK_TZ).isoformat()
                    except:
                        pass
            return capts
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_capts(data: list):
    with open(DB_CAPTS, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

def load_scores() -> dict:
    try:
        with open(DB_SCORES, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_scores(data: dict):
    with open(DB_SCORES, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def calculate_scores() -> dict:
    """Пересчитать баллы для всех игроков"""
    st = load_stats()
    scores = {}
    
    for uid, data in st.items():
        # Формула: 1 килл = 1 балл, 1 урон = 0.01 балл
        score = data["kills"] + (data["damage"] * 0.01)
        scores[uid] = round(score, 2)
    
    save_scores(scores)
    return scores

def has_role(member: discord.Member, roles: list) -> bool:
    if not member or not member.roles:
        return False
    role_names = [role.name for role in member.roles]
    return any(role_name in roles for role_name in role_names)

def is_admin(member: discord.Member) -> bool:
    return has_role(member, ADMIN_ROLES)

def is_viewer(member: discord.Member) -> bool:
    return has_role(member, VIEW_ROLES)

def get_capts_in_period(days: int = None):
    """Получить капты за период (в московском времени)"""
    capts = load_capts()
    if days is None:
        return capts
    
    cutoff = now_msk() - timedelta(days=days)
    result = []
    
    for capt in capts:
        if "date" in capt and capt["date"]:
            try:
                if isinstance(capt["date"], str):
                    capt_date = datetime.fromisoformat(capt["date"].replace("Z", "+00:00"))
                    if capt_date.tzinfo is None:
                        capt_date = capt_date.replace(tzinfo=timezone.utc).astimezone(MSK_TZ)
                    else:
                        capt_date = capt_date.astimezone(MSK_TZ)
                else:
                    continue
                
                if capt_date >= cutoff:
                    result.append(capt)
            except:
                continue
    
    return result

def calculate_stats(capts_list: list) -> dict:
    """Рассчитать статистику из списка каптов"""
    stats = {}
    for capt in capts_list:
        for player in capt["players"]:
            uid = str(player["user_id"])
            if uid not in stats:
                stats[uid] = {"damage": 0, "kills": 0, "games": 0, "wins": 0}
            stats[uid]["damage"] += player["damage"]
            stats[uid]["kills"] += player["kills"]
            stats[uid]["games"] += 1
            if capt["win"]:
                stats[uid]["wins"] += 1
    return stats

def get_player_stats(uid: str) -> dict:
    """Получить полную статистику игрока"""
    st = load_stats()
    scores = load_scores()
    capts = load_capts()
    
    if uid not in st:
        return None
    
    stats = st[uid].copy()
    stats["score"] = scores.get(uid, 0)
    
    # Получаем последние капты игрока
    player_capts = []
    for capt in reversed(capts):
        for player in capt["players"]:
            if str(player["user_id"]) == uid:
                player_capts.append(capt)
                break
        if len(player_capts) >= 5:
            break
    
    stats["recent_capts"] = player_capts[:5]
    
    # Последняя активность
    if player_capts:
        last_capt = player_capts[0]
        if "date" in last_capt:
            try:
                dt = datetime.fromisoformat(last_capt["date"].replace("Z", "+00:00"))
                stats["last_activity"] = dt.astimezone(MSK_TZ)
            except:
                stats["last_activity"] = None
    else:
        stats["last_activity"] = None
    
    return stats

async def log_action(action: str, user: discord.User = None, details: str = "", color: int = 0x3498db):
    """Логирование действий в лог-канал"""
    if not LOG_CHANNEL_ID:
        return
    
    channel = client.get_channel(LOG_CHANNEL_ID)
    if not channel:
        return
    
    embed = discord.Embed(
        title=f"📝 {action}",
        color=color,
        timestamp=now_msk()
    )
    
    if user:
        embed.add_field(name="👤 Пользователь", value=f"{user.mention} ({user.display_name})", inline=False)
    
    if details:
        embed.add_field(name="📋 Детали", value=details, inline=False)
    
    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"❌ Ошибка отправки лога: {e}")

# ==================== МОДАЛЬНЫЕ ОКНА ДЛЯ РЕДАКТИРОВАНИЯ ====================
class EditCaptModal(Modal, title="✏️ Редактирование капта"):
    def __init__(self, capt_data: dict, capt_index: int):
        super().__init__()
        self.capt_data = capt_data
        self.capt_index = capt_index
        
        self.vs_input = TextInput(
            label="Против кого играли",
            default=capt_data["vs"],
            required=True
        )
        
        self.date_input = TextInput(
            label="Дата (ДД.ММ.ГГГГ ЧЧ:ММ)",
            default=datetime.fromisoformat(capt_data["date"]).strftime("%d.%m.%Y %H:%M"),
            required=True
        )
        
        self.result_input = TextInput(
            label="Результат (win/lose)",
            default="win" if capt_data["win"] else "lose",
            required=True
        )
        
        self.add_item(self.vs_input)
        self.add_item(self.date_input)
        self.add_item(self.result_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        # Проверка результата
        result = self.result_input.value.strip().lower()
        if result not in ["win", "lose"]:
            await interaction.response.send_message("❌ Результат должен быть win или lose", ephemeral=True)
            return
        
        # Проверка даты
        try:
            naive_dt = datetime.strptime(self.date_input.value, "%d.%m.%Y %H:%M")
            new_date = naive_dt.replace(tzinfo=MSK_TZ)
        except:
            await interaction.response.send_message("❌ Неверный формат даты", ephemeral=True)
            return
        
        # Обновление данных
        capts = load_capts()
        capt = capts[-self.capt_index]
        
        old_data = capt.copy()
        capt["vs"] = self.vs_input.value
        capt["date"] = new_date.isoformat()
        capt["win"] = result == "win"
        
        save_capts(capts)
        
        # Логирование
        await log_action(
            "Редактирование капта",
            interaction.user,
            f"**Капт #{self.capt_index} обновлен**\n"
            f"**Старое:** vs {old_data['vs']}, дата {old_data['date'][:10]}, результат: {'win' if old_data['win'] else 'lose'}\n"
            f"**Новое:** vs {capt['vs']}, дата {self.date_input.value}, результат: {result}",
            0xf39c12
        )
        
        # Обновление списков
        asyncio.create_task(update_capts_list())
        asyncio.create_task(update_avg_top())
        asyncio.create_task(update_kills_top())
        
        await interaction.response.send_message(
            f"✅ Капт #{self.capt_index} успешно обновлен!",
            ephemeral=True
        )

class EditPlayerModal(Modal, title="✏️ Редактирование игрока"):
    def __init__(self, player_data: dict, capt_index: int, player_index: int):
        super().__init__()
        self.player_data = player_data
        self.capt_index = capt_index
        self.player_index = player_index
        
        self.damage_input = TextInput(
            label="Урон",
            default=str(player_data["damage"]),
            required=True
        )
        
        self.kills_input = TextInput(
            label="Киллы",
            default=str(player_data["kills"]),
            required=True
        )
        
        self.add_item(self.damage_input)
        self.add_item(self.kills_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            new_damage = int(self.damage_input.value)
            new_kills = int(self.kills_input.value)
        except:
            await interaction.response.send_message("❌ Урон и киллы должны быть числами", ephemeral=True)
            return
        
        # Обновление данных в капте
        capts = load_capts()
        capt = capts[-self.capt_index]
        player = capt["players"][self.player_index]
        
        old_damage = player["damage"]
        old_kills = player["kills"]
        
        # Обновляем в капте
        player["damage"] = new_damage
        player["kills"] = new_kills
        
        # Обновляем общую статистику
        st = load_stats()
        uid = str(player["user_id"])
        
        if uid in st:
            st[uid]["damage"] = st[uid]["damage"] - old_damage + new_damage
            st[uid]["kills"] = st[uid]["kills"] - old_kills + new_kills
            save_stats(st)
            
            # Пересчет баллов
            calculate_scores()
        
        save_capts(capts)
        
        # Логирование
        await log_action(
            "Редактирование игрока",
            interaction.user,
            f"**Игрок {player['user_name']} обновлен в капте #{self.capt_index}**\n"
            f"**Старое:** урон {old_damage:,}, киллы {old_kills}\n"
            f"**Новое:** урон {new_damage:,}, киллы {new_kills}",
            0xf39c12
        )
        
        # Обновление списков
        asyncio.create_task(update_capts_list())
        asyncio.create_task(update_avg_top())
        asyncio.create_task(update_kills_top())
        
        await interaction.response.send_message(
            f"✅ Игрок {player['user_name']} успешно обновлен!",
            ephemeral=True
        )

class EditScoreModal(Modal, title="✏️ Редактирование баллов"):
    def __init__(self, member: discord.Member):
        super().__init__()
        self.member = member
        
        scores = load_scores()
        current_score = scores.get(str(member.id), 0)
        
        self.score_input = TextInput(
            label="Баллы",
            default=str(current_score),
            required=True
        )
        
        self.add_item(self.score_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            new_score = float(self.score_input.value)
        except:
            await interaction.response.send_message("❌ Баллы должны быть числом", ephemeral=True)
            return
        
        scores = load_scores()
        scores[str(self.member.id)] = new_score
        save_scores(scores)
        
        # Логирование
        await log_action(
            "Редактирование баллов",
            interaction.user,
            f"**Баллы игрока {self.member.mention} обновлены**\n"
            f"**Новое значение:** {new_score}",
            0xf39c12
        )
        
        await interaction.response.send_message(
            f"✅ Баллы игрока {self.member.mention} обновлены: {new_score}",
            ephemeral=True
        )

# ==================== VIEW ДЛЯ УПРАВЛЕНИЯ КАПТОМ ====================
class CaptManagementView(View):
    def __init__(self, capt_index: int, capt_data: dict):
        super().__init__(timeout=300)
        self.capt_index = capt_index
        self.capt_data = capt_data
    
    @discord.ui.button(label="✏️ Редактировать капт", style=discord.ButtonStyle.primary, row=0)
    async def edit_capt(self, interaction: discord.Interaction, button: Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ Нет доступа", ephemeral=True)
            return
        
        modal = EditCaptModal(self.capt_data, self.capt_index)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="👥 Управление игроками", style=discord.ButtonStyle.secondary, row=0)
    async def manage_players(self, interaction: discord.Interaction, button: Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ Нет доступа", ephemeral=True)
            return
        
        if not self.capt_data["players"]:
            await interaction.response.send_message("❌ В этом капте нет игроков", ephemeral=True)
            return
        
        view = PlayersListView(self.capt_index, self.capt_data)
        embed = discord.Embed(
            title=f"👥 Игроки в капте #{self.capt_index}",
            description=f"Семья vs {self.capt_data['vs']}",
            color=0x3498db,
            timestamp=now_msk()
        )
        
        text = ""
        for i, player in enumerate(self.capt_data["players"]):
            text += f"{i+1}. {player['user_name']} - 💥 {player['damage']:,} │ ☠️ {player['kills']}\n"
        
        embed.add_field(name="Список игроков", value=text[:1024], inline=False)
        embed.set_footer(text="Выберите игрока для редактирования")
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class PlayersListView(View):
    def __init__(self, capt_index: int, capt_data: dict):
        super().__init__(timeout=300)
        self.capt_index = capt_index
        self.capt_data = capt_data
        
        # Создаем выпадающий список с игроками
        self.player_select = Select(
            placeholder="Выберите игрока...",
            options=[
                discord.SelectOption(
                    label=f"{player['user_name'][:25]}",
                    description=f"Урон: {player['damage']:,} | Киллы: {player['kills']}",
                    value=str(i)
                )
                for i, player in enumerate(capt_data["players"])
            ]
        )
        self.player_select.callback = self.player_selected
        self.add_item(self.player_select)
    
    async def player_selected(self, interaction: discord.Interaction):
        player_index = int(self.player_select.values[0])
        player = self.capt_data["players"][player_index]
        
        view = PlayerActionsView(self.capt_index, player_index, player)
        
        embed = discord.Embed(
            title=f"👤 Управление игроком",
            description=f"**{player['user_name']}**",
            color=0x3498db,
            timestamp=now_msk()
        )
        
        embed.add_field(name="💥 Урон", value=f"{player['damage']:,}", inline=True)
        embed.add_field(name="☠️ Киллы", value=player["kills"], inline=True)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class PlayerActionsView(View):
    def __init__(self, capt_index: int, player_index: int, player_data: dict):
        super().__init__(timeout=300)
        self.capt_index = capt_index
        self.player_index = player_index
        self.player_data = player_data
    
    @discord.ui.button(label="✏️ Изменить статы", style=discord.ButtonStyle.primary, row=0)
    async def edit_stats(self, interaction: discord.Interaction, button: Button):
        modal = EditPlayerModal(self.player_data, self.capt_index, self.player_index)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🗑️ Удалить из капта", style=discord.ButtonStyle.danger, row=0)
    async def remove_player(self, interaction: discord.Interaction, button: Button):
        capts = load_capts()
        capt = capts[-self.capt_index]
        player = capt["players"].pop(self.player_index)
        
        # Обновляем общую статистику
        st = load_stats()
        uid = str(player["user_id"])
        
        if uid in st:
            st[uid]["damage"] -= player["damage"]
            st[uid]["kills"] -= player["kills"]
            st[uid]["games"] -= 1
            
            # Если игроков не осталось, удаляем из статистики
            if st[uid]["games"] <= 0:
                del st[uid]
            
            save_stats(st)
            
            # Пересчет баллов
            calculate_scores()
        
        save_capts(capts)
        
        # Логирование
        await log_action(
            "Удаление игрока из капта",
            interaction.user,
            f"**Игрок {player['user_name']} удален из капта #{self.capt_index}**\n"
            f"Урон: {player['damage']:,} | Киллы: {player['kills']}",
            0xe74c3c
        )
        
        # Обновление списков
        asyncio.create_task(update_capts_list())
        asyncio.create_task(update_avg_top())
        asyncio.create_task(update_kills_top())
        
        await interaction.response.send_message(
            f"✅ Игрок {player['user_name']} удален из капта!",
            ephemeral=True
        )

# ==================== АДМИН ПАНЕЛЬ ====================
class AdminPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)  # Без таймаута
    
    @discord.ui.button(label="📊 Общая статистика", style=discord.ButtonStyle.primary, row=0)
    async def show_stats(self, interaction: discord.Interaction, button: Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ Нет доступа", ephemeral=True)
            return
        
        st = load_stats()
        capts = load_capts()
        
        total_games = len(capts)
        total_players = len(st)
        total_wins = sum(1 for c in capts if c["win"])
        winrate = (total_wins / total_games * 100) if total_games > 0 else 0
        
        embed = discord.Embed(
            title="📊 Общая статистика сервера",
            color=0x9b59b6,
            timestamp=now_msk()
        )
        
        embed.add_field(name="🎮 Всего каптов", value=str(total_games), inline=True)
        embed.add_field(name="✅ Побед", value=str(total_wins), inline=True)
        embed.add_field(name="📈 Винрейт", value=f"{winrate:.1f}%", inline=True)
        embed.add_field(name="👥 Уникальных игроков", value=str(total_players), inline=True)
        embed.add_field(name="📅 Последний капт", value=f"#{len(capts)}" if capts else "Нет", inline=True)
        
        # Топ 3 по урону
        if st:
            top_dmg = sorted(st.items(), key=lambda x: x[1]["damage"], reverse=True)[:3]
            dmg_text = "\n".join([f"{i+1}. <@{uid}> - {data['damage']:,}" for i, (uid, data) in enumerate(top_dmg)])
            embed.add_field(name="🏆 Топ по урону", value=dmg_text, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="👤 Управление игроком", style=discord.ButtonStyle.secondary, row=0)
    async def manage_player(self, interaction: discord.Interaction, button: Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ Нет доступа", ephemeral=True)
            return
        
        # Получаем всех участников сервера
        members = interaction.guild.members
        member_list = [m for m in members if not m.bot]
        
        if len(member_list) == 0:
            await interaction.response.send_message("❌ На сервере нет участников", ephemeral=True)
            return
        
        options = [
            discord.SelectOption(
                label=m.display_name[:25],
                description=f"ID: {m.id}",
                value=str(m.id)
            )
            for m in member_list[:25]  # Ограничение Discord
        ]
        
        view = SelectPlayerView(options)
        await interaction.response.send_message(
            "👤 Выберите игрока для управления:",
            view=view,
            ephemeral=True
        )
    
    @discord.ui.button(label="⭐ Редактировать баллы", style=discord.ButtonStyle.success, row=1)
    async def edit_scores(self, interaction: discord.Interaction, button: Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ Нет доступа", ephemeral=True)
            return
        
        members = interaction.guild.members
        member_list = [m for m in members if not m.bot]
        
        if len(member_list) == 0:
            await interaction.response.send_message("❌ На сервере нет участников", ephemeral=True)
            return
        
        options = [
            discord.SelectOption(
                label=m.display_name[:25],
                description=f"ID: {m.id}",
                value=str(m.id)
            )
            for m in member_list[:25]
        ]
        
        view = SelectPlayerForScoreView(options)
        await interaction.response.send_message(
            "⭐ Выберите игрока для редактирования баллов:",
            view=view,
            ephemeral=True
        )
    
    @discord.ui.button(label="📝 Управление каптами", style=discord.ButtonStyle.primary, row=1)
    async def manage_capts(self, interaction: discord.Interaction, button: Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ Нет доступа", ephemeral=True)
            return
        
        capts = load_capts()
        
        if not capts:
            await interaction.response.send_message("❌ Нет каптов", ephemeral=True)
            return
        
        options = []
        for i, capt in enumerate(reversed(capts[-10:]), 1):  # Последние 10 каптов
            vs = capt["vs"][:20]
            date_str = datetime.fromisoformat(capt["date"]).strftime("%d.%m")
            result = "✅" if capt["win"] else "❌"
            label = f"#{len(capts)-i+1} vs {vs} {result}"
            
            options.append(discord.SelectOption(
                label=label[:100],
                description=f"{date_str} | {len(capt['players'])} игроков",
                value=str(len(capts)-i+1)
            ))
        
        view = SelectCaptView(options)
        await interaction.response.send_message(
            "📝 Выберите капт для управления:",
            view=view,
            ephemeral=True
        )
    
    @discord.ui.button(label="🔄 Обновить все", style=discord.ButtonStyle.success, row=2)
    async def update_all(self, interaction: discord.Interaction, button: Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ Нет доступа", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            await update_avg_top()
            await update_kills_top()
            await update_capts_list()
            
            await log_action(
                "Обновление всех топов",
                interaction.user,
                "Все топы обновлены через админ-панель"
            )
            
            await interaction.followup.send("✅ Все топы успешно обновлены!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

class SelectPlayerView(View):
    def __init__(self, options):
        super().__init__(timeout=300)
        self.options = options
        
        self.select = Select(
            placeholder="Выберите игрока...",
            options=options
        )
        self.select.callback = self.player_selected
        self.add_item(self.select)
    
    async def player_selected(self, interaction: discord.Interaction):
        member_id = int(self.select.values[0])
        member = interaction.guild.get_member(member_id)
        
        if not member:
            await interaction.response.send_message("❌ Игрок не найден", ephemeral=True)
            return
        
        view = PlayerAdminView(member)
        
        stats = get_player_stats(str(member.id))
        if not stats:
            await interaction.response.send_message(
                f"📭 У {member.mention} нет статистики",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title=f"👤 Управление игроком",
            description=f"{member.mention}",
            color=0x3498db,
            timestamp=now_msk()
        )
        
        embed.add_field(name="🎮 Игр", value=stats["games"], inline=True)
        embed.add_field(name="💥 Урон", value=f"{stats['damage']:,}", inline=True)
        embed.add_field(name="☠️ Киллы", value=stats["kills"], inline=True)
        embed.add_field(name="⭐ Баллы", value=stats.get("score", 0), inline=True)
        embed.add_field(name="✅ Побед", value=stats.get("wins", 0), inline=True)
        
        winrate = (stats.get("wins", 0) / stats["games"] * 100) if stats["games"] > 0 else 0
        embed.add_field(name="📈 Винрейт", value=f"{winrate:.1f}%", inline=True)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class PlayerAdminView(View):
    def __init__(self, member: discord.Member):
        super().__init__(timeout=300)
        self.member = member
    
    @discord.ui.button(label="✏️ Изменить статы", style=discord.ButtonStyle.primary, row=0)
    async def edit_stats(self, interaction: discord.Interaction, button: Button):
        # Получаем последний капт игрока
        capts = load_capts()
        for i, capt in enumerate(reversed(capts), 1):
            for player in capt["players"]:
                if str(player["user_id"]) == str(self.member.id):
                    modal = EditPlayerModal(player, i, capt["players"].index(player))
                    await interaction.response.send_modal(modal)
                    return
        
        await interaction.response.send_message("❌ Игрок не найден в последних каптах", ephemeral=True)
    
    @discord.ui.button(label="🗑️ Сбросить статистику", style=discord.ButtonStyle.danger, row=0)
    async def reset_stats(self, interaction: discord.Interaction, button: Button):
        confirm_view = ConfirmView(self.member, "reset_stats")
        await interaction.response.send_message(
            f"⚠️ Вы уверены, что хотите сбросить статистику игрока {self.member.mention}?",
            view=confirm_view,
            ephemeral=True
        )
    
    @discord.ui.button(label="📋 Последние капты", style=discord.ButtonStyle.secondary, row=1)
    async def recent_capts(self, interaction: discord.Interaction, button: Button):
        stats = get_player_stats(str(self.member.id))
        if not stats or "recent_capts" not in stats:
            await interaction.response.send_message("❌ Нет данных о каптах", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"📋 Последние капты {self.member.display_name}",
            color=0x3498db,
            timestamp=now_msk()
        )
        
        text = ""
        for i, capt in enumerate(stats["recent_capts"], 1):
            try:
                date = datetime.fromisoformat(capt["date"].replace("Z", "+00:00"))
                date_str = date.strftime("%d.%m")
            except:
                date_str = "??.??"
            
            result = "✅" if capt["win"] else "❌"
            # Находим игрока в капте
            for player in capt["players"]:
                if str(player["user_id"]) == str(self.member.id):
                    text += f"{i}. vs {capt['vs'][:15]} {result} - {date_str} | 💥 {player['damage']:,} | ☠️ {player['kills']}\n"
                    break
        
        if text:
            embed.description = text
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("❌ Нет данных о каптах", ephemeral=True)

class SelectPlayerForScoreView(View):
    def __init__(self, options):
        super().__init__(timeout=300)
        self.options = options
        
        self.select = Select(
            placeholder="Выберите игрока...",
            options=options
        )
        self.select.callback = self.player_selected
        self.add_item(self.select)
    
    async def player_selected(self, interaction: discord.Interaction):
        member_id = int(self.select.values[0])
        member = interaction.guild.get_member(member_id)
        
        if not member:
            await interaction.response.send_message("❌ Игрок не найден", ephemeral=True)
            return
        
        modal = EditScoreModal(member)
        await interaction.response.send_modal(modal)

class SelectCaptView(View):
    def __init__(self, options):
        super().__init__(timeout=300)
        self.options = options
        
        self.select = Select(
            placeholder="Выберите капт...",
            options=options
        )
        self.select.callback = self.capt_selected
        self.add_item(self.select)
    
    async def capt_selected(self, interaction: discord.Interaction):
        capt_index = int(self.select.values[0])
        capts = load_capts()
        
        if capt_index < 1 or capt_index > len(capts):
            await interaction.response.send_message("❌ Капт не найден", ephemeral=True)
            return
        
        capt = capts[-capt_index]
        view = CaptManagementView(capt_index, capt)
        
        try:
            date = datetime.fromisoformat(capt["date"]).strftime("%d.%m.%Y %H:%M")
        except:
            date = "Дата неизвестна"
        
        embed = discord.Embed(
            title=f"📝 Управление каптом #{capt_index}",
            description=f"vs {capt['vs']}",
            color=0x9b59b6,
            timestamp=now_msk()
        )
        
        embed.add_field(name="📅 Дата", value=date, inline=True)
        embed.add_field(name="📊 Результат", value="✅ Победа" if capt["win"] else "❌ Поражение", inline=True)
        embed.add_field(name="👥 Игроков", value=len(capt["players"]), inline=True)
        
        total_dmg = sum(p["damage"] for p in capt["players"])
        total_kills = sum(p["kills"] for p in capt["players"])
        embed.add_field(name="💥 Общий урон", value=f"{total_dmg:,}", inline=True)
        embed.add_field(name="☠️ Общие киллы", value=total_kills, inline=True)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class ConfirmView(View):
    def __init__(self, member: discord.Member, action: str):
        super().__init__(timeout=300)
        self.member = member
        self.action = action
    
    @discord.ui.button(label="✅ Да", style=discord.ButtonStyle.danger, row=0)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        if self.action == "reset_stats":
            st = load_stats()
            uid = str(self.member.id)
            
            if uid in st:
                old_stats = st[uid]
                del st[uid]
                save_stats(st)
                
                # Удаляем баллы
                scores = load_scores()
                if uid in scores:
                    del scores[uid]
                    save_scores(scores)
                
                # Нужно удалить игрока из всех каптов
                capts = load_capts()
                for capt in capts:
                    capt["players"] = [p for p in capt["players"] if str(p["user_id"]) != uid]
                save_capts(capts)
                
                # Логирование
                await log_action(
                    "Сброс статистики игрока",
                    interaction.user,
                    f"**Статистика игрока {self.member.mention} сброшена**\n"
                    f"Удалено: {old_stats['games']} игр, {old_stats['damage']:,} урона, {old_stats['kills']} киллов",
                    0xe74c3c
                )
                
                # Обновление списков
                asyncio.create_task(update_capts_list())
                asyncio.create_task(update_avg_top())
                asyncio.create_task(update_kills_top())
                
                await interaction.response.edit_message(
                    content=f"✅ Статистика игрока {self.member.mention} сброшена!",
                    view=None
                )
            else:
                await interaction.response.edit_message(
                    content=f"❌ У игрока {self.member.mention} нет статистики",
                    view=None
                )
    
    @discord.ui.button(label="❌ Нет", style=discord.ButtonStyle.secondary, row=0)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(
            content="❌ Действие отменено",
            view=None
        )

async def setup_admin_panel():
    """Создание админ-панели в канале"""
    channel = client.get_channel(ADMIN_PANEL_CHANNEL_ID)
    if not channel:
        print(f"❌ Канал админ-панели не найден: {ADMIN_PANEL_CHANNEL_ID}")
        return
    
    # Удаляем старые сообщения от бота в этом канале
    try:
        async for msg in channel.history(limit=50):
            if msg.author.id == client.user.id and "🛠️ АДМИН-ПАНЕЛЬ" in msg.content:
                await msg.delete()
                await asyncio.sleep(1)
    except:
        pass
    
    # Создаем новое сообщение с админ-панелью
    embed = discord.Embed(
        title="🛠️ АДМИН-ПАНЕЛЬ УПРАВЛЕНИЯ",
        description="*Используйте кнопки ниже для управления статистикой*",
        color=0xe74c3c,
        timestamp=now_msk()
    )
    
    embed.add_field(
        name="📊 Общее управление",
        value="• **Общая статистика** - просмотр общей статистики сервера\n"
              "• **Управление игроком** - редактирование статистики конкретного игрока\n"
              "• **Редактировать баллы** - ручное изменение баллов игрока\n"
              "• **Управление каптами** - редактирование существующих каптов\n"
              "• **Обновить все** - принудительное обновление всех топов",
        inline=False
    )
    
    embed.add_field(
        name="⚡ Быстрые команды",
        value="`/добавить_капт` - Создать новый капт\n"
              "`/добавить_игрока` - Добавить игрока в капт\n"
              "`/удалить_капт` - Удалить капт\n"
              "`/сбросить_статистику` - Полный сброс статистики",
        inline=False
    )
    
    embed.set_footer(text="Доступно только администраторам")
    
    view = AdminPanelView()
    
    try:
        await channel.send(embed=embed, view=view)
        print("✅ Админ-панель создана")
    except Exception as e:
        print(f"❌ Ошибка создания админ-панели: {e}")

# ==================== КОМАНДЫ ====================
@tree.command(name="капт", description="📋 Детали капта с управлением", guild=discord.Object(GUILD_ID))
@app_commands.describe(номер="Номер капта (1 = последний)")
async def capt_details(inter: discord.Interaction, номер: int = 1):
    if not is_viewer(inter.user):
        await inter.response.send_message("❌ Нет доступа", ephemeral=True)
        return
    
    capts = load_capts()
    if not capts or номер < 1 or номер > len(capts):
        await inter.response.send_message("❌ Капт не найден", ephemeral=True)
        return
    
    capt = capts[-номер]
    
    try:
        date = datetime.fromisoformat(capt["date"]).strftime("%d.%m.%Y %H:%M")
    except:
        date = "Дата неизвестна"
    
    embed = discord.Embed(
        title=f"⚔️ YAK vs {capt['vs']}",
        description=f"📅 {date}\n{'✅ Победа' if capt['win'] else '❌ Поражение'}\n**#{номер} из {len(capts)}**",
        color=0x2ecc71 if capt["win"] else 0xe74c3c,
        timestamp=now_msk()
    )
    
    # Сортируем игроков по урону
    players_sorted = sorted(capt["players"], key=lambda x: x["damage"], reverse=True)
    
    if players_sorted:
        text = ""
        for i, p in enumerate(players_sorted[:10], 1):
            try:
                member = await inter.guild.fetch_member(p["user_id"])
                name = f"{member.mention} ({member.display_name})"
            except:
                name = f"Игрок {p['user_id']}"
            text += f"**{i}.** {name} — {p['damage']:,} урона, {p['kills']} киллов\n"
        embed.add_field(name="👥 Участники (первые 10)", value=text, inline=False)
    
    total_dmg = sum(p["damage"] for p in capt["players"])
    total_kills = sum(p["kills"] for p in capt["players"])
    cnt = len(capt["players"])
    avg_dmg = total_dmg // cnt if cnt else 0
    avg_kills = total_kills / cnt if cnt else 0
    
    embed.add_field(
        name="📊 Статистика",
        value=f"👥 {cnt} игроков\n💥 {total_dmg:,} урона\n☠️ {total_kills} киллов\n📈 {avg_dmg:,} ср. урона\n📊 {avg_kills:.1f} ср. киллов",
        inline=False
    )
    
    # Если пользователь админ, добавляем кнопки управления
    if is_admin(inter.user):
        view = CaptManagementView(номер, capt)
    else:
        view = None
    
    await inter.response.send_message(embed=embed, view=view, ephemeral=True)

@tree.command(name="профиль", description="📊 Расширенный профиль игрока", guild=discord.Object(GUILD_ID))
@app_commands.describe(игрок="Игрок")
async def profile(inter: discord.Interaction, игрок: discord.Member = None):
    if not is_viewer(inter.user):
        await inter.response.send_message("❌ Нет доступа", ephemeral=True)
        return
    
    target = игрок or inter.user
    stats = get_player_stats(str(target.id))
    
    if not stats:
        await inter.response.send_message(f"📭 У {target.mention} нет статистики", ephemeral=True)
        return
    
    avg_dmg = stats["damage"] // stats["games"] if stats["games"] > 0 else 0
    avg_kills = stats["kills"] / stats["games"] if stats["games"] > 0 else 0
    winrate = (stats.get("wins", 0) / stats["games"] * 100) if stats["games"] > 0 else 0
    score = stats.get("score", 0)
    
    embed = discord.Embed(
        title=f"📊 Профиль {target.mention}",
        description=f"*Полная статистика игрока*",
        color=0x3498db,
        timestamp=now_msk()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    
    # Основная статистика
    embed.add_field(name="🎮 Игр", value=stats["games"], inline=True)
    embed.add_field(name="💥 Урон", value=f"{stats['damage']:,}", inline=True)
    embed.add_field(name="☠️ Киллы", value=stats["kills"], inline=True)
    embed.add_field(name="📈 Ср.урон", value=f"{avg_dmg:,}", inline=True)
    embed.add_field(name="📊 Ср.киллы", value=f"{avg_kills:.1f}", inline=True)
    embed.add_field(name="✅ Побед", value=stats.get("wins", 0), inline=True)
    embed.add_field(name="📉 Поражений", value=stats["games"] - stats.get("wins", 0), inline=True)
    embed.add_field(name="📈 Винрейт", value=f"{winrate:.1f}%", inline=True)
    embed.add_field(name="⭐ Баллы", value=f"{score:.2f}", inline=True)
    
    # Последняя активность
    if stats.get("last_activity"):
        last_active = stats["last_activity"]
        time_diff = now_msk() - last_active
        if time_diff.days > 0:
            active_text = f"{time_diff.days} д. назад"
        elif time_diff.seconds > 3600:
            active_text = f"{time_diff.seconds // 3600} ч. назад"
        elif time_diff.seconds > 60:
            active_text = f"{time_diff.seconds // 60} мин. назад"
        else:
            active_text = "только что"
        
        embed.add_field(name="🕐 Последняя активность", value=active_text, inline=False)
    
    # Последние 5 каптов
    if stats.get("recent_capts"):
        text = ""
        for i, capt in enumerate(stats["recent_capts"][:5], 1):
            try:
                date = datetime.fromisoformat(capt["date"].replace("Z", "+00:00"))
                date_str = date.strftime("%d.%m")
            except:
                date_str = "??.??"
            
            result = "✅" if capt["win"] else "❌"
            # Находим игрока в капте
            for player in capt["players"]:
                if str(player["user_id"]) == str(target.id):
                    text += f"{i}. vs {capt['vs'][:15]} {result} - {date_str} | 💥 {player['damage']:,} | ☠️ {player['kills']}\n"
                    break
        
        if text:
            embed.add_field(name="📋 Последние 5 каптов", value=text, inline=False)
    
    # Формула баллов
    embed.set_footer(text="Формула баллов: 1 килл = 1 балл, 1 урон = 0.01 балла")
    
    await inter.response.send_message(embed=embed, ephemeral=True)

# Остальные команды (добавить_капт, добавить_игрока, и т.д.) остаются как были, 
# но добавлено ephemeral=True во все ответы и логирование

@tree.command(name="добавить_капт", description="📝 Добавить новый капт", guild=discord.Object(GUILD_ID))
@app_commands.describe(
    против="Против кого играли",
    результат="win или lose",
    дата="Дата (ДД.ММ.ГГГГ ЧЧ:ММ)"
)
async def add_capt(inter: discord.Interaction, против: str, результат: str, дата: str = None):
    if not is_admin(inter.user):
        await inter.response.send_message("❌ Нет доступа", ephemeral=True)
        return
    
    # ... существующий код ...
    # В конце добавляем логирование:
    await log_action(
        "Добавление капта",
        inter.user,
        f"**Добавлен капт против {против}**\n"
        f"Результат: {'win' if win else 'lose'}\n"
        f"Дата: {capt_date.strftime('%d.%m.%Y %H:%M')}"
    )
    
    await inter.response.send_message(
        f"✅ Капт против **{против}** создан!\n"
        f"Результат: {'✅ Победа' if win else '❌ Поражение'}\n"
        f"Дата: {capt_date.strftime('%d.%m.%Y %H:%M')} МСК",
        ephemeral=True
    )

# Аналогично для других команд добавляем логирование и ephemeral=True

# ==================== НЕДЕЛЬНЫЙ ОТЧЕТ ====================
async def generate_weekly_report():
    """Генерация недельного отчета"""
    channel = client.get_channel(WEEKLY_REPORT_CHANNEL_ID)
    if not channel:
        return
    
    # Получаем капты за последние 7 дней
    capts = get_capts_in_period(7)
    
    if not capts:
        return
    
    # Рассчитываем статистику
    stats = calculate_stats(capts)
    
    embed = discord.Embed(
        title="📊 НЕДЕЛЬНЫЙ ОТЧЕТ",
        description=f"*Статистика за последние 7 дней*\n"
                   f"Период: {(now_msk() - timedelta(days=7)).strftime('%d.%m.%Y')} - {now_msk().strftime('%d.%m.%Y')}",
        color=0x9b59b6,
        timestamp=now_msk()
    )
    
    # Общая статистика
    total_games = len(capts)
    total_wins = sum(1 for c in capts if c["win"])
    winrate = (total_wins / total_games * 100) if total_games > 0 else 0
    
    embed.add_field(name="🎮 Сыграно каптов", value=str(total_games), inline=True)
    embed.add_field(name="✅ Побед", value=str(total_wins), inline=True)
    embed.add_field(name="📈 Винрейт", value=f"{winrate:.1f}%", inline=True)
    
    # Топ-5 по урону
    if stats:
        top_dmg = sorted(stats.items(), key=lambda x: x[1]["damage"], reverse=True)[:5]
        dmg_text = ""
        for i, (uid, data) in enumerate(top_dmg, 1):
            try:
                member = await channel.guild.fetch_member(int(uid))
                name = member.display_name
            except:
                name = f"Игрок {uid}"
            
            avg_dmg = data["damage"] // data["games"] if data["games"] > 0 else 0
            dmg_text += f"{i}. **{name}** - {data['damage']:,} урона ({data['games']} игр, ср. {avg_dmg:,})\n"
        
        if dmg_text:
            embed.add_field(name="🏆 Топ по урону", value=dmg_text, inline=False)
    
    # Топ-5 по киллам
    if stats:
        top_kills = sorted(stats.items(), key=lambda x: x[1]["kills"], reverse=True)[:5]
        kills_text = ""
        for i, (uid, data) in enumerate(top_kills, 1):
            try:
                member = await channel.guild.fetch_member(int(uid))
                name = member.display_name
            except:
                name = f"Игрок {uid}"
            
            avg_kills = data["kills"] / data["games"] if data["games"] > 0 else 0
            kills_text += f"{i}. **{name}** - {data['kills']} киллов ({data['games']} игр, ср. {avg_kills:.1f})\n"
        
        if kills_text:
            embed.add_field(name="☠️ Топ по киллам", value=kills_text, inline=False)
    
    # Самый активный игрок
    if stats:
        most_active = sorted(stats.items(), key=lambda x: x[1]["games"], reverse=True)[0]
        uid, data = most_active
        try:
            member = await channel.guild.fetch_member(int(uid))
            name = member.mention
        except:
            name = f"Игрок {uid}"
        
        embed.add_field(
            name="⚡ Самый активный",
            value=f"{name} - {data['games']} игр за неделю",
            inline=False
        )
    
    embed.set_footer(text="Отчет генерируется автоматически каждую неделю")
    
    try:
        await channel.send(embed=embed)
        await log_action("Генерация недельного отчета", details=f"Отправлен отчет за неделю: {total_games} игр")
    except Exception as e:
        print(f"❌ Ошибка отправки недельного отчета: {e}")

@tasks.loop(hours=168)  # 7 дней
async def weekly_report_task():
    """Задача для генерации недельного отчета"""
    await generate_weekly_report()

# ==================== АВТООБНОВЛЕНИЕ ТОПОВ ====================
async def update_avg_top():
    """Обновление топа по среднему урону"""
    channel = client.get_channel(STATS_AVG_CHANNEL_ID)
    if not channel:
        return
    
    try:
        st = load_stats()
        filtered = {uid: d for uid, d in st.items() if d["games"] >= 3}
        
        if not filtered:
            return
        
        users = sorted(filtered.items(), key=lambda x: x[1]["damage"]/x[1]["games"], reverse=True)[:10]
        
        embed = discord.Embed(
            title="🏆 ТОП-10 СРЕДНЕГО УРОНА",
            color=0x9b59b6,
            timestamp=now_msk()
        )
        
        desc = ""
        for i, (uid, data) in enumerate(users, 1):
            try:
                member = await channel.guild.fetch_member(int(uid))
                name = member.display_name
            except:
                name = f"Игрок {uid}"
            
            avg = data["damage"] // data["games"]
            leader_avg = users[0][1]["damage"] // users[0][1]["games"]
            percent = (avg / leader_avg * 100) if leader_avg > 0 else 0
            bar = "█" * int(percent / 10) + "░" * (10 - int(percent / 10))
            
            desc += f"{'🥇' if i == 1 else '🥈' if i == 2 else '🥉' if i == 3 else f'`{i}.`'} **{name}**\n{bar} **{avg:,}** урона ({data['games']} игр)\n\n"
        
        embed.description = desc
        embed.set_footer(text="Обновляется каждый час • Минимум 3 игры")
        
        async for msg in channel.history(limit=50):
            if msg.author.id == client.user.id and msg.embeds:
                if "ТОП-10 СРЕДНЕГО УРОНА" in msg.embeds[0].title:
                    try:
                        await msg.edit(embed=embed)
                        return
                    except:
                        pass
        
        await channel.send(embed=embed)
    except:
        pass

async def update_kills_top():
    """Обновление топа по киллам"""
    channel = client.get_channel(STATS_KILLS_CHANNEL_ID)
    if not channel:
        return
    
    try:
        st = load_stats()
        if not st:
            return
        
        users = sorted(st.items(), key=lambda x: x[1]["kills"], reverse=True)[:10]
        
        embed = discord.Embed(
            title="☠️ ТОП-10 ПО КИЛЛАМ",
            color=0xe74c3c,
            timestamp=now_msk()
        )
        
        desc = ""
        for i, (uid, data) in enumerate(users, 1):
            try:
                member = await channel.guild.fetch_member(int(uid))
                name = member.display_name
            except:
                name = f"Игрок {uid}"
            
            leader_kills = users[0][1]["kills"]
            percent = (data["kills"] / leader_kills * 100) if leader_kills > 0 else 0
            bar = "█" * int(percent / 10) + "░" * (10 - int(percent / 10))
            
            desc += f"{'🥇' if i == 1 else '🥈' if i == 2 else '🥉' if i == 3 else f'`{i}.`'} **{name}**\n{bar} **{data['kills']}** киллов ({data['games']} игр)\n\n"
        
        embed.description = desc
        embed.set_footer(text="Обновляется каждый час")
        
        async for msg in channel.history(limit=50):
            if msg.author.id == client.user.id and msg.embeds:
                if "ТОП-10 ПО КИЛЛАМ" in msg.embeds[0].title:
                    try:
                        await msg.edit(embed=embed)
                        return
                    except:
                        pass
        
        await channel.send(embed=embed)
    except:
        pass

async def update_capts_list():
    """Обновление списка каптов"""
    channel = client.get_channel(CAPTS_LIST_CHANNEL_ID)
    if not channel:
        return
    
    # ... существующий код ...

@tasks.loop(hours=1)
async def auto_update():
    await update_avg_top()
    await update_kills_top()
    await update_capts_list()

# ==================== СОБЫТИЯ ====================
@client.event
async def on_ready():
    print(f"✅ Бот запущен: {client.user}")
    
    # Инициализация баллов
    calculate_scores()
    print("✅ Баллы пересчитаны")
    
    try:
        synced = await tree.sync(guild=discord.Object(GUILD_ID))
        print(f"✅ Команды синхронизированы: {len(synced)} команд")
    except Exception as e:
        print(f"❌ Ошибка синхронизации: {e}")
    
    # Запуск задач
    if not auto_update.is_running():
        auto_update.start()
        print("✅ Автообновление запущено")
    
    if not weekly_report_task.is_running():
        weekly_report_task.start()
        print("✅ Недельные отчеты запущены")
    
    # Создание админ-панели
    await asyncio.sleep(5)
    await setup_admin_panel()
    
    # Первоначальное обновление
    try:
        await update_capts_list()
        await update_avg_top()
        await update_kills_top()
    except:
        pass

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    # Создаем файлы базы данных, если они не существуют
    for db in [DB_STATS, DB_CAPTS, DB_SCORES]:
        if not os.path.exists(db):
            with open(db, "w", encoding="utf-8") as f:
                json.dump({} if db in [DB_STATS, DB_SCORES] else [], f)
            print(f"📁 Создан {db}")

    try:
        client.run(TOKEN)
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
