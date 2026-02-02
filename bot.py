# -------------- bot.py (исправленная версия 7.1) --------------
import discord, json, os, asyncio, re, traceback
from datetime import datetime, timedelta, timezone
from discord.ext import tasks
from discord import app_commands
from discord.ui import Button, View, Modal, TextInput, Select

# ==================== НАСТРОЙКИ ====================
TOKEN = os.getenv("TOKEN")
GUILD_ID = 1430087806952411230
ADMIN_ROLES = ["dep.YAK", "Owner", "Leader"]
VIEW_ROLES = ["member", "Test", "Famlily", "Yak"]

# ID каналов
STATS_AVG_CHANNEL_ID = 1467543899643052312
STATS_KILLS_CHANNEL_ID = 1467543933209809076
CAPTS_LIST_CHANNEL_ID = 1467544000088117451
LOG_CHANNEL_ID = 1467598151269150822
ADMIN_MENU_CHANNEL_ID = 1467757228189810799
WEEKLY_REPORT_CHANNEL_ID = 1467757665076776960

# Московское время (UTC+3)
MSK_TZ = timezone(timedelta(hours=3))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

DB_STATS = "stats.json"
DB_CAPTS = "capts.json"
DB_POINTS = "points.json"

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
                        if "T" in capt["date"]:
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

def load_points() -> dict:
    """Загрузить баллы игроков"""
    try:
        with open(DB_POINTS, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_points(data: dict):
    """Сохранить баллы игроков"""
    with open(DB_POINTS, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def calculate_points_from_stats(damage: int, kills: int) -> float:
    """Рассчитать баллы по формуле: 1 килл = 0.5 балла, 1 урон = 0.001 балла"""
    return (kills * 0.5) + (damage * 0.001)

def add_points_to_player(user_id: int, damage: int, kills: int):
    """Добавить баллы игроку за капт"""
    points_db = load_points()
    uid = str(user_id)
    
    # Рассчитываем баллы
    points_to_add = calculate_points_from_stats(damage, kills)
    
    # Добавляем баллы
    current_points = points_db.get(uid, 0)
    new_points = current_points + points_to_add
    
    # Не даем уйти в минус
    if new_points < 0:
        new_points = 0
    
    points_db[uid] = new_points
    save_points(points_db)
    
    return points_to_add, new_points

def remove_points_from_player(user_id: int, damage: int, kills: int):
    """Удалить баллы игрока за капт"""
    points_db = load_points()
    uid = str(user_id)
    
    # Рассчитываем баллы
    points_to_remove = calculate_points_from_stats(damage, kills)
    
    # Отнимаем баллы
    current_points = points_db.get(uid, 0)
    new_points = current_points - points_to_remove
    
    # Не даем уйти в минус
    if new_points < 0:
        new_points = 0
    
    points_db[uid] = new_points
    save_points(points_db)
    
    return points_to_remove, new_points

def adjust_player_points(user_id: int, points_change: float):
    """Изменение баллов игрока (ручное)"""
    points_db = load_points()
    uid = str(user_id)
    
    current_points = points_db.get(uid, 0)
    new_points = current_points + points_change
    
    # Не даем уйти в минус
    if new_points < 0:
        new_points = 0
    
    points_db[uid] = new_points
    save_points(points_db)
    
    return points_change, new_points

def get_player_points(user_id: int) -> float:
    """Получить баллы игрока"""
    points_db = load_points()
    return points_db.get(str(user_id), 0)

def has_role(member: discord.Member, roles: list) -> bool:
    if not member or not member.roles:
        return False
    role_names = [role.name for role in member.roles]
    return any(role_name in roles for role_name in role_names)

def is_admin(member: discord.Member) -> bool:
    """Проверка, является ли пользователь админом"""
    return has_role(member, ADMIN_ROLES)

def is_viewer(member: discord.Member) -> bool:
    """Проверка, может ли пользователь просматривать статистику"""
    return has_role(member, VIEW_ROLES)

def progress_bar(percent: int, length: int = 10):
    filled = int(percent / 100 * length)
    filled = max(0, min(length, filled))
    return "█" * filled + "░" * (length - filled)

def medal(pos: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(pos, "")

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

def get_player_capts(user_id: int) -> list:
    """Получить все капты, в которых участвовал игрок"""
    capts = load_capts()
    player_capts = []
    
    for i, capt in enumerate(capts):
        for player in capt["players"]:
            if player["user_id"] == user_id:
                player_capts.append({
                    "index": len(capts) - i,  # Номер капта (1 = последний)
                    "capt": capt,
                    "player_data": player
                })
                break
    
    return player_capts

def calculate_player_stats(user_id: int, period_days: int = None):
    """Рассчитать статистику игрока за период"""
    capts = get_capts_in_period(period_days)
    total_damage = 0
    total_kills = 0
    total_games = 0
    wins = 0
    
    for capt in capts:
        for player in capt["players"]:
            if player["user_id"] == user_id:
                total_damage += player["damage"]
                total_kills += player["kills"]
                total_games += 1
                if capt["win"]:
                    wins += 1
                break
    
    avg_damage = total_damage // total_games if total_games > 0 else 0
    winrate = (wins / total_games * 100) if total_games > 0 else 0
    
    return {
        "games": total_games,
        "damage": total_damage,
        "kills": total_kills,
        "avg_damage": avg_damage,
        "wins": wins,
        "winrate": winrate,
        "points": calculate_points_from_stats(total_damage, total_kills)
    }

async def log_action(guild: discord.Guild, user: discord.Member, action: str, details: str = "", color: int = 0x3498db):
    """Логирование действий в лог-канал"""
    if not LOG_CHANNEL_ID:
        return
    
    channel = guild.get_channel(LOG_CHANNEL_ID)
    if not channel:
        return
    
    embed = discord.Embed(
        title=f"📝 {action}",
        description=f"**Пользователь:** {user.mention} ({user.display_name})\n" + details,
        color=color,
        timestamp=now_msk()
    )
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    
    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"❌ Ошибка отправки лога: {e}")

async def log_command_start(inter: discord.Interaction, command_name: str, params: dict = None):
    """Логирование начала выполнения команды"""
    try:
        await log_action(
            inter.guild,
            inter.user,
            f"▶️ Запуск команды /{command_name}",
            "**Параметры:**\n" + "\n".join([f"• **{k}:** {v}" for k, v in (params or {}).items()]) if params else "Без параметров",
            0x3498db
        )
    except:
        pass

async def log_command_success(inter: discord.Interaction, command_name: str, result: str):
    """Логирование успешного выполнения команды"""
    try:
        await log_action(
            inter.guild,
            inter.user,
            f"✅ Команда /{command_name} выполнена",
            f"**Результат:** {result}",
            0x2ecc71
        )
    except:
        pass

async def log_command_error(inter: discord.Interaction, command_name: str, error: str):
    """Логирование ошибки выполнения команды"""
    try:
        await log_action(
            inter.guild,
            inter.user,
            f"❌ Ошибка команды /{command_name}",
            f"**Ошибка:** {error}",
            0xe74c3c
        )
    except:
        pass

async def log_system_event(event: str, details: str):
    """Логирование системных событий"""
    if not LOG_CHANNEL_ID:
        return
    
    channel = client.get_channel(LOG_CHANNEL_ID)
    if not channel:
        return
    
    embed = discord.Embed(
        title=f"⚙️ {event}",
        description=details,
        color=0x9b59b6,
        timestamp=now_msk()
    )
    
    try:
        await channel.send(embed=embed)
    except:
        pass

# ==================== МОДАЛЬНЫЕ ОКНА ДЛЯ АДМИН-МЕНЮ ====================
class EditPlayerModal(Modal, title="✏️ Редактировать игрока"):
    def __init__(self):
        super().__init__()
        self.player_id = TextInput(
            label="ID игрока",
            placeholder="123456789012345678",
            required=True
        )
        self.capt_num = TextInput(
            label="Номер капта",
            placeholder="1",
            required=True
        )
        self.kills = TextInput(
            label="Киллы",
            placeholder="10",
            required=True
        )
        self.damage = TextInput(
            label="Урон",
            placeholder="15000",
            required=True
        )
        self.remove_from_capt = TextInput(
            label="Удалить с капта? (1-да, 0-нет)",
            placeholder="0",
            default="0",
            required=False,
            max_length=1
        )
        
        self.add_item(self.player_id)
        self.add_item(self.capt_num)
        self.add_item(self.kills)
        self.add_item(self.damage)
        self.add_item(self.remove_from_capt)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            player_id = int(self.player_id.value)
            capt_num = int(self.capt_num.value)
            new_kills = int(self.kills.value)
            new_damage = int(self.damage.value)
            remove_flag = self.remove_from_capt.value.strip() == "1"
            
            capts = load_capts()
            if not (1 <= capt_num <= len(capts)):
                await interaction.followup.send("❌ Неверный номер капта", ephemeral=True)
                return
            
            capt = capts[-capt_num]
            
            # Ищем игрока в капте
            player_index = -1
            old_player_data = None
            for i, player in enumerate(capt["players"]):
                if player["user_id"] == player_id:
                    player_index = i
                    old_player_data = player.copy()
                    break
            
            if player_index == -1:
                await interaction.followup.send("❌ Игрок не найден в капте", ephemeral=True)
                return
            
            if remove_flag:
                # Удаляем игрока из капта
                removed_player = capt["players"].pop(player_index)
                
                # Обновляем общую статистику
                st = load_stats()
                uid = str(player_id)
                if uid in st:
                    st[uid]["damage"] -= removed_player["damage"]
                    st[uid]["kills"] -= removed_player["kills"]
                    st[uid]["games"] -= 1
                    
                    if st[uid]["games"] <= 0:
                        del st[uid]
                
                # Отнимаем баллы
                points_removed, new_points = remove_points_from_player(
                    player_id, 
                    removed_player["damage"], 
                    removed_player["kills"]
                )
                
                save_stats(st)
                save_capts(capts)
                
                await log_action(
                    interaction.guild,
                    interaction.user,
                    "🗑️ Удален игрок из капта",
                    f"**Капт #{capt_num}**\n"
                    f"**Игрок:** <@{player_id}>\n"
                    f"**Урон:** {removed_player['damage']:,}\n"
                    f"**Киллы:** {removed_player['kills']}\n"
                    f"**Баллов снято:** {points_removed:.2f}",
                    0xe74c3c
                )
                
                await asyncio.sleep(1)
                asyncio.create_task(update_avg_top())
                asyncio.create_task(update_kills_top())
                asyncio.create_task(update_capts_list())
                
                await interaction.followup.send(
                    f"✅ Игрок удален из капта #{capt_num}\n"
                    f"📉 Снято баллов: {points_removed:.2f}\n"
                    f"💰 Новый баланс: {new_points:.2f}",
                    ephemeral=True
                )
                
            else:
                # Изменяем статистику игрока
                old_damage = old_player_data["damage"]
                old_kills = old_player_data["kills"]
                
                # Обновляем данные в капте
                capt["players"][player_index]["damage"] = new_damage
                capt["players"][player_index]["kills"] = new_kills
                
                # Обновляем общую статистику
                st = load_stats()
                uid = str(player_id)
                if uid in st:
                    st[uid]["damage"] = st[uid]["damage"] - old_damage + new_damage
                    st[uid]["kills"] = st[uid]["kills"] - old_kills + new_kills
                
                # Пересчитываем баллы
                # Сначала отнимаем старые баллы
                points_removed, temp_points = remove_points_from_player(player_id, old_damage, old_kills)
                # Потом добавляем новые
                points_added, new_points = add_points_to_player(player_id, new_damage, new_kills)
                
                save_stats(st)
                save_capts(capts)
                
                await log_action(
                    interaction.guild,
                    interaction.user,
                    "✏️ Изменена статистика игрока",
                    f"**Капт #{capt_num}**\n"
                    f"**Игрок:** <@{player_id}>\n"
                    f"**Урон:** {old_damage:,} → {new_damage:,}\n"
                    f"**Киллы:** {old_kills} → {new_kills}\n"
                    f"**Изменение баллов:** {points_added - points_removed:.2f}",
                    0xf1c40f
                )
                
                await asyncio.sleep(1)
                asyncio.create_task(update_avg_top())
                asyncio.create_task(update_kills_top())
                asyncio.create_task(update_capts_list())
                
                await interaction.followup.send(
                    f"✅ Статистика игрока обновлена\n"
                    f"💥 Урон: **{new_damage:,}**\n"
                    f"☠️ Киллы: **{new_kills}**\n"
                    f"💰 Новый баланс: {new_points:.2f}",
                    ephemeral=True
                )
                
        except ValueError as e:
            await interaction.followup.send(f"❌ Ошибка ввода данных: {str(e)}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Ошибка: {str(e)}", ephemeral=True)

class EditPointsModal(Modal, title="⭐ Изменить баллы игрока"):
    def __init__(self):
        super().__init__()
        self.player_id = TextInput(
            label="ID игрока",
            placeholder="123456789012345678",
            required=True
        )
        self.points_change = TextInput(
            label="Изменение баллов (+/-)",
            placeholder="100 или -50",
            required=True
        )
        
        self.add_item(self.player_id)
        self.add_item(self.points_change)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            player_id = int(self.player_id.value)
            points_change = float(self.points_change.value)
            
            # Применяем изменение
            change_applied, new_points = adjust_player_points(player_id, points_change)
            
            await log_action(
                interaction.guild,
                interaction.user,
                "⭐ Изменены баллы игрока",
                f"**Игрок:** <@{player_id}>\n"
                f"**Изменение:** {change_applied:.2f}\n"
                f"**Новые баллы:** {new_points:.2f}",
                0xf1c40f
            )
            
            await interaction.followup.send(
                f"✅ Баллы игрока изменены\n"
                f"📊 Изменение: {change_applied:+.2f}\n"
                f"💰 Новый баланс: {new_points:.2f}",
                ephemeral=True
            )
            
        except ValueError:
            await interaction.followup.send("❌ Введите корректные числа", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Ошибка: {str(e)}", ephemeral=True)

class EditCaptAdminModal(Modal, title="✏️ Редактировать капт"):
    def __init__(self):
        super().__init__()
        self.capt_num = TextInput(
            label="Номер капта",
            placeholder="1",
            required=True
        )
        self.family_name = TextInput(
            label="Название семьи (не обязательно)",
            placeholder="Новое название",
            required=False
        )
        self.result = TextInput(
            label="Результат (win/lose, не обязательно)",
            placeholder="win или lose",
            required=False
        )
        
        self.add_item(self.capt_num)
        self.add_item(self.family_name)
        self.add_item(self.result)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            capt_num = int(self.capt_num.value)
            
            capts = load_capts()
            if not (1 <= capt_num <= len(capts)):
                await interaction.followup.send("❌ Неверный номер капта", ephemeral=True)
                return
            
            capt = capts[-capt_num]
            changes = []
            
            # Изменяем название семьи, если указано
            if self.family_name.value.strip():
                old_family = capt["vs"]
                capt["vs"] = self.family_name.value.strip()
                changes.append(f"**Семья:** {old_family} → {capt['vs']}")
            
            # Изменяем результат, если указано
            if self.result.value.strip():
                result_text = self.result.value.strip().lower()
                if result_text in ["win", "w", "1", "true", "победа", "в"]:
                    capt["win"] = True
                    changes.append(f"**Результат:** Поражение → Победа")
                elif result_text in ["lose", "l", "0", "false", "поражение", "п"]:
                    capt["win"] = False
                    changes.append(f"**Результат:** Победа → Поражение")
                else:
                    await interaction.followup.send("❌ Неверный формат результата", ephemeral=True)
                    return
            
            if changes:
                save_capts(capts)
                
                await log_action(
                    interaction.guild,
                    interaction.user,
                    "✏️ Изменен капт",
                    f"**Капт #{capt_num}**\n" + "\n".join(changes),
                    0xf1c40f
                )
                
                await asyncio.sleep(1)
                asyncio.create_task(update_capts_list())
                
                await interaction.followup.send(
                    f"✅ Капт #{capt_num} изменен\n" + "\n".join(changes),
                    ephemeral=True
                )
            else:
                await interaction.followup.send("ℹ️ Ничего не изменено", ephemeral=True)
                
        except ValueError:
            await interaction.followup.send("❌ Введите корректный номер капта", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Ошибка: {str(e)}", ephemeral=True)

# ==================== VIEW ДЛЯ АДМИН МЕНЮ ====================
class AdminMenuView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="✏️ Редактировать игрока", style=discord.ButtonStyle.primary, custom_id="admin_edit_player")
    async def edit_player(self, interaction: discord.Interaction, button: Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ Нет доступа", ephemeral=True)
            return
        
        modal = EditPlayerModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="⭐ Баллы", style=discord.ButtonStyle.primary, custom_id="admin_points")
    async def points_menu(self, interaction: discord.Interaction, button: Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ Нет доступа", ephemeral=True)
            return
        
        modal = EditPointsModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="✏️ Редактировать капт", style=discord.ButtonStyle.primary, custom_id="admin_edit_capt")
    async def edit_capt(self, interaction: discord.Interaction, button: Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ Нет доступа", ephemeral=True)
            return
        
        modal = EditCaptAdminModal()
        await interaction.response.send_modal(modal)

# ==================== VIEW ДЛЯ СПИСКА КАПТОВ ====================
class CaptsListView(View):
    def __init__(self, guild: discord.Guild, period: str = "all"):
        super().__init__(timeout=None)
        self.guild = guild
        self.period = period
        self.current_page = 0
        self.capts_per_page = 10
        self.update_data()

    def update_data(self):
        if self.period == "week":
            self.capts = get_capts_in_period(7)
        elif self.period == "month":
            self.capts = get_capts_in_period(30)
        else:
            self.capts = load_capts()
        
        self.total_pages = max(1, (len(self.capts) + self.capts_per_page - 1) // self.capts_per_page)
        if self.current_page >= self.total_pages:
            self.current_page = max(0, self.total_pages - 1)

    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.secondary, custom_id="capts_prev")
    async def previous_page(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_message(interaction)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.primary, custom_id="capts_page")
    async def page_info(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)

    @discord.ui.button(label="➡️", style=discord.ButtonStyle.secondary, custom_id="capts_next")
    async def next_page(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            await self.update_message(interaction)

    @discord.ui.button(label="🔄", style=discord.ButtonStyle.success, custom_id="capts_refresh")
    async def refresh(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        self.update_data()
        await self.update_message(interaction)

    async def update_message(self, interaction: discord.Interaction):
        embed = await self.create_embed()
        for child in self.children:
            if isinstance(child, Button):
                if child.custom_id == "capts_page":
                    child.label = f"{self.current_page + 1}/{self.total_pages}"
                elif child.custom_id == "capts_prev":
                    child.disabled = self.current_page == 0
                elif child.custom_id == "capts_next":
                    child.disabled = self.current_page >= self.total_pages - 1

        try:
            await interaction.message.edit(embed=embed, view=self)
        except:
            pass

    async def create_embed(self):
        period_text = {
            "week": "📅 за неделю",
            "month": "📅 за месяц",
            "all": "📜 вся история"
        }.get(self.period, "")
        
        embed = discord.Embed(
            title=f"⚔️ История каптов Семьи {period_text}",
            color=0xe74c3c,
            timestamp=now_msk()
        )

        if not self.capts:
            embed.description = "📭 Нет каптов за этот период"
        else:
            reversed_capts = list(reversed(self.capts))
            start = self.current_page * self.capts_per_page
            end = min(start + self.capts_per_page, len(reversed_capts))

            desc = ""
            for i in range(start, end):
                capt = reversed_capts[i]
                num = len(self.capts) - i
                
                date_str = "Дата неизвестна"
                if "date" in capt and capt["date"]:
                    try:
                        if isinstance(capt["date"], str):
                            dt = datetime.fromisoformat(capt["date"].replace("Z", "+00:00"))
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            dt = dt.astimezone(MSK_TZ)
                            date_str = dt.strftime("%d.%m.%Y %H:%M")
                    except:
                        pass
                
                result = "✅" if capt["win"] else "❌"
                players = len(capt["players"])
                damage = sum(p["damage"] for p in capt["players"])
                kills = sum(p["kills"] for p in capt["players"])

                desc += f"**#{num}. Семья vs {capt['vs']}** {result}\n"
                desc += f"🕐 {date_str} │ 👥 {players} │ 💥 {damage:,} │ ☠️ {kills}\n\n"

            embed.description = desc

            wins = sum(1 for c in self.capts if c["win"])
            total = len(self.capts)
            winrate = (wins/total*100) if total > 0 else 0

            embed.add_field(
                name="📊 Статистика",
                value=f"```Всего:     {total}\nПобед:     {wins}\nПоражений: {total-wins}\nВинрейт:   {winrate:.1f}%```",
                inline=False
            )

        embed.set_footer(text=f"Страница {self.current_page+1}/{self.total_pages} • Время МСК")
        return embed

# ==================== НЕДЕЛЬНЫЙ ОТЧЕТ С БАЛЛАМИ ====================
async def send_weekly_report():
    """Отправка недельного отчета с баллами"""
    channel = client.get_channel(WEEKLY_REPORT_CHANNEL_ID)
    if not channel:
        return
    
    try:
        # Получаем капты за последние 7 дней
        weekly_capts = get_capts_in_period(7)
        
        if not weekly_capts:
            embed = discord.Embed(
                title="📊 Недельный отчет",
                description="За последнюю неделю не было каптов",
                color=0x3498db,
                timestamp=now_msk()
            )
            await channel.send(embed=embed)
            return
        
        # Рассчитываем статистику
        total_capts = len(weekly_capts)
        wins = sum(1 for c in weekly_capts if c["win"])
        winrate = (wins / total_capts * 100) if total_capts > 0 else 0
        
        # Собираем статистику по игрокам за неделю
        player_stats = {}
        for capt in weekly_capts:
            for player in capt["players"]:
                uid = str(player["user_id"])
                if uid not in player_stats:
                    player_stats[uid] = {
                        "damage": 0,
                        "kills": 0,
                        "games": 0,
                        "wins": 0
                    }
                player_stats[uid]["damage"] += player["damage"]
                player_stats[uid]["kills"] += player["kills"]
                player_stats[uid]["games"] += 1
                if capt["win"]:
                    player_stats[uid]["wins"] += 1
        
        # Добавляем баллы за неделю
        for uid, stats in player_stats.items():
            stats["weekly_points"] = calculate_points_from_stats(stats["damage"], stats["kills"])
        
        # Топ по среднему урону (минимум 3 игры)
        top_damage = []
        for uid, stats in player_stats.items():
            if stats["games"] >= 3:
                avg_damage = stats["damage"] // stats["games"]
                top_damage.append((uid, avg_damage, stats))
        
        top_damage.sort(key=lambda x: x[1], reverse=True)
        
        # Топ по киллам
        top_kills = sorted(player_stats.items(), key=lambda x: x[1]["kills"], reverse=True)
        
        # Топ по баллам за неделю
        top_points = sorted(player_stats.items(), key=lambda x: x[1]["weekly_points"], reverse=True)
        
        # Общая статистика
        total_damage = sum(stats["damage"] for stats in player_stats.values())
        total_kills = sum(stats["kills"] for stats in player_stats.values())
        total_points = sum(stats["weekly_points"] for stats in player_stats.values())
        unique_players = len(player_stats)
        
        # Создаем embed
        embed = discord.Embed(
            title="📊 Недельный отчет по статистике",
            description=f"*Период: последние 7 дней*",
            color=0x9b59b6,
            timestamp=now_msk()
        )
        
        # Общая статистика
        embed.add_field(
            name="📈 Общая статистика",
            value=f"```Каптов:          {total_capts}\n"
                  f"Побед:            {wins}\n"
                  f"Винрейт:          {winrate:.1f}%\n"
                  f"Уникальных игроков: {unique_players}\n"
                  f"Всего урона:      {total_damage:,}\n"
                  f"Всего киллов:     {total_kills}\n"
                  f"Всего баллов:     {total_points:.2f}```",
            inline=False
        )
        
        # Топ по среднему урону (первые 5)
        if top_damage:
            damage_text = ""
            for i, (uid, avg_dmg, stats) in enumerate(top_damage[:5], 1):
                try:
                    member = await channel.guild.fetch_member(int(uid))
                    name = member.display_name
                except:
                    name = f"Игрок {uid}"
                
                winrate_player = (stats["wins"] / stats["games"] * 100) if stats["games"] > 0 else 0
                damage_text += f"**{i}. {name}**\n"
                damage_text += f"Ср.урон: {avg_dmg:,} | Игр: {stats['games']} | Винрейт: {winrate_player:.1f}% | Баллы: {stats['weekly_points']:.2f}\n\n"
            
            embed.add_field(
                name="🏆 Топ по среднему урону (3+ игр)",
                value=damage_text,
                inline=False
            )
        
        # Топ по киллам (первые 5)
        if top_kills:
            kills_text = ""
            for i, (uid, stats) in enumerate(top_kills[:5], 1):
                try:
                    member = await channel.guild.fetch_member(int(uid))
                    name = member.display_name
                except:
                    name = f"Игрок {uid}"
                
                avg_kills = stats["kills"] / stats["games"] if stats["games"] > 0 else 0
                kills_text += f"**{i}. {name}**\n"
                kills_text += f"Киллов: {stats['kills']} | Ср.киллов: {avg_kills:.1f} | Игр: {stats['games']} | Баллы: {stats['weekly_points']:.2f}\n\n"
            
            embed.add_field(
                name="☠️ Топ по киллам",
                value=kills_text,
                inline=False
            )
        
        # Топ по баллам (первые 5)
        if top_points:
            points_text = ""
            for i, (uid, stats) in enumerate(top_points[:10], 1):  # Топ-10 для отнятия баллов
                try:
                    member = await channel.guild.fetch_member(int(uid))
                    name = member.display_name
                except:
                    name = f"Игрок {uid}"
                
                if i <= 5:  # Показываем только первые 5 в отчете
                    points_text += f"**{i}. {name}**\n"
                    points_text += f"Баллы: {stats['weekly_points']:.2f} | Урон: {stats['damage']:,} | Киллы: {stats['kills']} | Игр: {stats['games']}\n\n"
            
            if points_text:
                embed.add_field(
                    name="⭐ Топ по баллам (первые 5)",
                    value=points_text,
                    inline=False
                )
        
        embed.set_footer(text="Отчет обновляется каждую неделю • Баллы: 1 килл = 0.5 балла, 1 урон = 0.001 балла")
        
        await channel.send(embed=embed)
        
        # Отнимаем баллы у топ-10 по баллам за неделю
        points_penalty_message = "**Снятие баллов за неделю:**\n"
        players_penalized = 0
        
        for i, (uid, stats) in enumerate(top_points[:10], 1):
            try:
                member = await channel.guild.fetch_member(int(uid))
                name = member.display_name
            except:
                name = f"Игрок {uid}"
            
            # Отнимаем 10% от баллов за неделю
            penalty = stats["weekly_points"] * 0.1  # 10% штраф
            change_applied, new_points = adjust_player_points(int(uid), -penalty)
            
            points_penalty_message += f"{i}. {name}: -{penalty:.2f} баллов (осталось: {new_points:.2f})\n"
            players_penalized += 1
        
        if players_penalized > 0:
            penalty_embed = discord.Embed(
                title="📉 Снятие баллов за неделю",
                description=points_penalty_message,
                color=0xe74c3c,
                timestamp=now_msk()
            )
            penalty_embed.set_footer(text="У топ-10 по баллам снято 10% от недельных баллов")
            await channel.send(embed=penalty_embed)
        
        # Логируем отправку отчета
        await log_system_event("📊 Отправлен недельный отчет", 
                             f"Каптов: {total_capts}, Игроков: {unique_players}, Снято баллов у: {players_penalized}")
        
    except Exception as e:
        await log_system_event("❌ Ошибка недельного отчета", f"Ошибка: {str(e)}")

@tasks.loop(hours=168)  # 7 дней = 168 часов
async def weekly_report_task():
    """Задача для отправки недельного отчета"""
    await send_weekly_report()

# ==================== КОМАНДЫ ====================
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
    
    await log_command_start(inter, "добавить_капт", {
        "против": против,
        "результат": результат,
        "дата": дата or "текущая"
    })
    
    result_text = результат.strip().lower()
    if result результат.strip().lower()
    if result_text not in ["win", "lose", "победа", "поражение", "в_text not in ["win", "lose", "победа", "поражение", "в", "п"]:
        await log_command_error(inter, "", "п"]:
        await log_command_error(inter, "добавить_капт", f"Неверный результатдобавить_капт", f"Неверный результат: {результа: {результат}")
        await interт}")
        await inter.response.send_message("❌ Ре.response.send_message("❌ Результат: win или loseзультат: win или lose", ephemeral=True)
        return
    
    win = result", ephemeral=True)
        return
    
    win = result_text in ["win_text in ["win", "победа", "в", "победа", "в"]
    
    capt_date ="]
    
    capt_date = now_msk()
    if дата:
        try:
 now_msk()
    if дата:
        try:
            naive_dt = datetime            naive_dt = datetime.strptime(дата.strptime(дата, "%d.%, "%d.%m.%Y %H:%M")
            capt_date = naive_dm.%Y %H:%M")
            capt_date = naive_dt.replace(tzinfo=MSK_TZ)
       t.replace(tzinfo=MSK_TZ except:
            try:
                naive_dt = datetime.strptime)
        except:
            try:
                naive_dt = datetime.strptime(дата,(дата, "%d.%m.%Y")
                capt_date = naive "%d.%m.%Y")
                capt_date = naive_dt.replace(tzinfo=MS_dt.replace(tzinfoK_TZ)
            except:
                await log=MSK_TZ)
            except:
                await log_command_error(inter, "доба_command_error(inter, "добавить_капт",вить_капт", f"Неверный формат даты: {да f"Неверный формат даты: {дата}")
                await inter.response.send_message("❌ Нета}")
                await inter.response.send_message("❌ Неверный формат датыверный формат даты", ephemeral=True)
                return
    
", ephemeral=True)
                return
    
    new_capt = {
        "vs":    new_capt = {
        "vs": против.strip(),
        "date": capt против.strip(),
        "date": capt_date.isoformat(),
        "win": win,
        "players_date.isoformat(),
        "win": win,
        "players": []
    }
": []
    }
    
    capts = load_capt    
    capts = load_capts()
    capts.append(new_capt)
    save_capts(capts)
    
s()
    capts.append(new_capt)
    save_capts(capts)
    
    asyncio.create_task(update_capts_list())
    
    await log_command_success(inter, "добавить_капт", f"Капт против {против} создан")
    
    await inter.response.send_message(
        f"✅ Капт против **{против}    asyncio.create_task(update_capts_list())
    
    await log_command_success(inter, "добавить_капт", f"Капт против {против} создан")
    
    await inter.response.send_message(
        f"✅ Капт против **{против}** созда** создан!\n"
        f"Результатн!\n"
        f"Результат: {': {'✅ Победа' if win else '❌✅ Победа' if win else '❌ Поражение'}\n Поражение'}\n"
        f"Дата:"
        f"Дата: {capt_date.strftime('%d.%m.%Y %H:% {capt_date.strftime('%d.%m.%Y %H:%M')} МСК",
        ephemeral=True
   M')} МСК",
        ephemeral=True
    )

@tree.command(name=" )

@tree.command(name="добавить_игрока", description="👤добавить_игрока", description="👤 Добавить Добавить игрока в капт", guild=discord.Object игрока в капт", guild=discord.Object(GUILD_ID(GUILD_ID))
@app_commands.describe(
    игрок="@упоминание))
@app_commands.describe(
    игрок="@упоминание или ID",
    урон="Урон",
    киллы или ID",
    урон="Урон",
    киллы="Киллы",
   ="Киллы",
    номер_капта="Номер капта ( номер_капта="Номер капта (1 = последний)"
)
async def1 = последний)"
)
async def add_player(inter: discord.Interaction, игрок: add_player(inter: discord.Interaction, игрок: discord.Member, урон: int discord.Member, урон: int, киллы: int, киллы: int, номер_капта: int, номер_капта: int = 1):
    if = 1):
    if not is not is_admin(inter.user):
        await inter.response.send_message_admin(inter.user):
        await inter.response.send_message("("❌ Нет доступа", ephemeral=True)
        return
    
❌ Нет доступа", ephemeral=True)
        return
    
    await log_command_start    await log_command(inter, "добавить_игрока", {
_start(inter, "добавить_игрока", {
               "игрок": f"{игрок.mention} "игрок": f"{игрок.mention} ({игрок.display_name})",
        "урон ({игрок.display_name})",
        "урон": урон,
        "киллы": киллы,
": урон,
        "киллы": киллы,
        "номер_капта": номер_капта
        "номер_капта": номер_капта
    })

    capts = load_capts()
    if номер    })

    capts = load_capts()
    if номер_капта < 1 or номер_кап_капта < 1 or номер_капта > len(capts):
       та > len(capts await log_command_error(inter, "добавить_):
        await log_command_error(inter, "добавить_игигрока", f"Капт не найден: номеррока", f"Капт не найден: номер {номер_капта}")
        await inter.response.send {номер_капта}")
        await inter.response.send_message("_message("❌ Кап❌ Капт нет не найден", ephemeral=True)
        return

    capt = capts[-номер_капта]
    
    if any(p["user_id"] == игрок.id for p in capt["players"]):
        await log_command_error(inter, "добавить_игрока", f"Игрок уже в капте: {игрок.display_name}")
        await inter.response.send_message(f" найден", ephemeral=True)
        return

    capt = capts[-номер_капта]
    
    if any(p["user_id"] == игрок.id for p in capt["players"]):
        await log_command_error(inter, "добавить_игрока", f"Игрок уже в капте: {игрок.display_name}")
        await inter.response.send_message(f"❌ {игрок❌ {игрок.mention} уже в ка.mention} уже в капте", ephemeral=Trueпте", ephemeral=True)
       )
        return

    capt["players"].append({
        "user return

    capt["players"].append({
        "user_id": игрок.id,
        "user_name": иг_id": игрок.id,
        "user_name": игрок.display_name,
        "damage": урон,
        "рок.display_name,
        "damage": урон,
        "kills": киллы
   kills": киллы })

    st = load_stats()
    uid = str(
    })

    st = load_stats()
    uid = str(игрок.id)
    if uid not in st:
        stигрок.id)
    if uid not in st:
        st[uid] = {"dam[uid] = {"damage": 0, "kills": 0, "gamesage": 0, "kills": 0,": 0}
    
    st[uid]["damage "games": 0}
    
    st[uid]["damage"] +="] += урон
    st[uid]["kills"] += ки урон
    st[uid]["kills"] +=ллы
    st[uid]["games"] += 1
    
    киллы
    st[uid]["games"] += 1
    
    # Добавляем баллы # Добавляем баллы игроку
    points_added, new_points = игроку
    points_added, new_points = add_points_to_player(игрок add_points_to_player(игрок.id, урон, ки.id, урон, киллы)
    
    save_stats(stллы)
    
    save_stats(st)
    save_capts(capts)
    
    asyn)
    save_capts(capts)
    
    asyncio.create_task(update_avg_topcio.create_task(update_())
    asyncio.create_task(update_kills_topavg_top())
    asyncio.create_task(update_kills_top())
    asyncio.create_task(update_capts_list())
())
    asyncio.create_task(update_capts_list())
    
    await log_command_success(inter, "добавить    
    await log_command_success(inter, "добавить_игрока", 
                            f"Игрок {_игрока", 
                            f"Игрок {игрок.mention} добавлен в капт #{номеригрок.mention} добавлен в капт #{номер_капта}, начислено {points_added:.2_капта}, начислено {points_added:.2f} баллов")
    
    await inter.response.send_messagef} баллов")
    
    await inter.response.send_message(
        f"✅ {игрок.mention} добавлен!\n(
        f"✅ {игрок.mention} добавлен!\n"
        f"💥"
        f"💥 Урон: **{урон:, Урон: **{урон:,}** │ ☠️}** │ ☠️ Кил Киллы: **{лы: **{киллы}**\n"
        f"⭐ Начислено балкиллы}**\n"
        f"⭐ Начислено баллов:лов: **{points_added:.2f}**\n"
        **{points_added:.2f}**\n"
        f"💰 Общий баланс: **{new_points:.2f}**",
        ephemeral=True
    )

@tree.command(name="загрузить_игроков", description="📤 Загрузить игроков из текста", guild=discord.Object(GUILD_ID))
@app_commands.describe(
    данные="ID у f"💰 Общий баланс: **{new_points:.2f}**",
        ephemeral=True
    )

@tree.command(name="загрузить_игроков", description="📤 Загрузить игроков из текста", guild=discord.Object(GUILD_ID))
@app_commands.describe(
    данные="ID урон киллы (каждый с новой строки)",
рон киллы (каждый с новой строки)",
    номер_капта="Н    номер_капта="Номер капта"
)
омер капта"
)
async def upload_players(inter: discord.Interaction, данные:async def upload_players(inter: discord.Interaction, данные: str, номер_капта: int = 1):
    str, номер_капта: int = 1):
    if not is_admin(inter.user):
        await inter.response.send_message if not is_admin(inter.user):
        await inter.response.send_message("❌ Н("❌ Нет доступа", ephemeral=True)
        returnет доступа", ephemeral=True)

    
    await log_command_start(inter, "загру        return
    
    await log_command_start(inter, "загрузить_игроковзить_игроков", {
        "данные": f"{len(данные.splitlines())} строк",
        "номер_капта": номер_капта
    })
    
    await inter.response.defer(ephemeral=True)
    
    try:
        capts = load_capts()
        if номер_капта < 1 or номер_капта >", {
        "данные": f"{len(данные.splitlines())} строк",
        "номер_капта": номер_капта
    })
    
    await inter.response.defer(ephemeral=True)
    
    try:
        capts = load_capts()
        if номер_капта < 1 or номер_капта > len(capts):
            await log_command_error(inter, "загрузить_игроков", f"Ка len(capts):
            await log_command_error(inter, "загрузить_игроков", f"Капт не найден: номер {пт не найден: номер {номер_капта}")
            await inter.followup.send("номер_капта}")
            await inter.followup.send("❌ Капт не❌ Капт не найден", ephemeral=True)
            return
        
        capt = capt найден", ephemeral=True)
            return
        
        capt = capts[-номер_капs[-номер_капта]
        lines = данные.strip().split('\n')
        addedта]
        lines = данные.strip().split('\n')
        added = 0
        errors = []
 = 0
        errors = []
        total        total_points_added = 0
        
       _points_added = 0
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            parts = for line in lines:
            line = line.strip()
            if not line:
                continue
            
            parts = line.split()
            if len(parts line.split()
            if len(parts) < 3:
               ) < 3:
                errors.append errors.append(f"❌ Неверный формат: {line}")
               (f"❌ Неверный формат: {line}")
                continue
            
            try:
                user_id = int(parts[0 continue
            
            try:
                user_id = int(parts[0])
                damage = int(parts[1].replace('k',])
                damage = int(parts[1].replace('k', '000').replace('K', '000'))
                kills = int(parts[2])
            except:
                errors '000').replace('K', '000'))
                kills = int(parts[2])
            except:
                errors.append(f"❌ Ошибка парсин.append(f"❌ Ошибкага: {line}")
                continue
            
            try:
                парсинга: {line}")
                continue
            
            try:
                member = await inter.guild.fetch_m member = await inter.guild.fetch_member(user_id)
            except:
                errors.append(f"❌ Игember(user_id)
            except:
                errors.append(f"❌ Игрок {user_id} не найден")
                continue
            
            ifрок {user_id} не найден")
                continue
            
            if any(p["user_id"] == user any(p["user_id"] == user_id for p in capt["players"]):
                errors.append(f"⚠️_id for p in capt["players"]):
                errors.append(f"⚠️ {member.mention} уже добавлен")
                continue
            
            capt["players {member.mention} уже добавлен")
                continue
            
            capt["players"].append({
                "user_id":"].append({
                "user_id": user_id user_id,
                "user_name": member.display_name,
                "damage,
                "user_name": member.display_name,
                "damage": damage,
                "kills": kills
            })
            
           ": damage,
                "kills": kills
            })
            
            st = load_stats()
            uid = str(user_id)
            if uid not st = load_stats()
            uid = str(user_id)
            if uid not in st:
                st[uid] in st:
                st[uid] = {"damage":  = {"damage": 0,0, "kills": 0, "games": 0}
            st[uid]["damage"] += damage
            st[uid]["kills"] "kills": 0, "games": 0}
            st[uid]["damage"] += damage
            st[uid]["kills"] += kills
            st[uid]["games"] += 1
            
 += kills
            st[uid]["games"] += 1
            
            # Добавляем баллы
            points_added, _            # Добавляем баллы
            points_added, _ = add = add_points_to_player(user_id, damage, kills)
            total_points_add_points_to_player(user_id, damage, kills)
            total_points_added += points_added
            
            save_stats(st)
            
            added += 1
        
ed += points_added
            
            save_stats(st)
            
            added +=         save_capts(capts)
        
        asyncio1
        
        save_capts(capts)
        
        asyncio.create_task(update_avg.create_task(update_avg_top())
        asyncio.create_task_top())
        asyncio.create_task(update_kills_top())
        asyncio(update_kills_top())
        asyncio.create_task(update_capts_list())
        
        await log_command.create_task(update_capts_list())
        
        await log_command_success(inter, "загрузить_игроков", 
_success(inter, "загрузить_игроков", 
                                f"Добавлено {                                f"Добавлено {added} игроков, начисadded} игроков, начислено {total_points_added:.2f} баллов,лено {total_points_added:.2f} баллов, ошибок: {len(errors)}")
        
        msg = f"✅ ошибок: {len(errors)}")
        
        msg = f"✅ Добавлено игроков: **{added}**\n Добавлено игроков: **{added}**\n"
        msg += f"⭐ Все"
        msg += f"⭐ Всего начислено баллов: **го начислено баллов: **{total_points_added:.2f{total_points_added:.2f}**"
        
        if errors:
}**"
        
        if errors:
            msg += f"\n\n⚠️ Ошибки:\n" +            msg += f"\n\n⚠️ Ошибки:\n" + "\n".join(errors[:5])
            if len(errors) > "\n".join(errors[:5])
            if len(errors) > 5:
                msg += f"\ 5:
                msg += f"\n... и ещё {len(errors)-5}"
        
        awaitn... и ещё {len(errors)-5}"
        
        await inter.followup.send(msg, ephemer inter.followup.send(msg, ephemeral=True)
            
    except Exception as e:
        await log_command_error(al=True)
            
    except Exception as e:
        await log_command_error(inter, "загрузить_иinter, "загрузить_игроков", str(e))
        print(f"❌ Огроков", str(e))
        print(f"❌ Ошибка в upload_players: {e}")
        await inter.fшибка в upload_players: {e}")
        await inter.followup.send("❌ Произошлаollowup.send("❌ Произошла ошибка при выполнении команды", ephemeral=True)

@tree ошибка при выполнении команды", ephemeral=True)

@tree.command(name="удалить_ка.command(name="удалить_капт", description="🗑️пт", description="🗑️ Удалить капт", guild=discord.Object(GU Удалить капт", guild=discord.Object(GUILD_ID))
@app_commands.describe(номерILD_ID))
@app_commands.describe="Номер капта")
async def delete_capt(inter: discord(номер="Номер капта")
async def delete_capt(inter:.Interaction, номер: int):
    if not is_admin(inter.user):
 discord.Interaction, номер: int):
    if not is_admin(inter.user):
        await inter.response.send_message("        await inter.response.send_message("❌ Нет доступа",❌ Нет доступа", ephemeral=True)
        return
    
    await log ephemeral=True)
        return
    
   _command_start(inter, "удалить_капт", await log_command_start(inter, "удалить_капт", {"номер": номер})
    
    capt {"номер": номер})
    
    capts = load_capts()
    if номерs = load_capts()
    < 1 or номер > len(capts if номер < 1 or номер > len(capts):
        await log_command_error(inter, "удалить_капт",):
        await log_command_error(inter, "удалить_капт", f"Капт не найден: номер {номер}")
        await inter.response.send_message f"Капт не найден: номер {номер}")
        await inter.response.send_message("("❌ Капт не найден", ephemeral=True)
❌ Капт не найден", ephemeral=True)
        return
    
    removed_capt = capt        return
    
    removed_capt = capts.pops.pop(-номер)
    
    st = load_stats()
    total_points_(-номер)
    
    st = load_stats()
    total_points_removed = 0
    
    for player inremoved = 0
    
    for removed_capt["players"]:
        uid = str(player["user_id"])
 player in removed_capt["players"]:
        uid = str(player["user        if uid in st:
            st[uid]["damage"]_id"])
        if uid in st:
            st[uid]["damage"] -= player["damage"]
            st[uid -= player["damage"]
            st[uid]["kills"] -= player]["kills"] -= player["kills"]
            st[uid]["games["kills"]
            st[uid]["games"] -= 1
            
            # Отнимаем баллы
            points_"] -= 1
            
            # Отнимаем баллы
            points_removed, _ = remove_points_from_player(
                player["userremoved, _ = remove_points_from_player(
                player["user_id"], 
                player["damage"], 
                player["kills"]
            )
_id"], 
                player["damage"], 
                player["kills"]
            )
            total_points_removed += points_removed
            
            if st            total_points_removed += points_removed
            
            if st[uid]["games"] <= 0:
                del[uid]["games"] <= 0:
                del st[uid]
    
    st[uid]
    
    save_stats(st)
    save_capts(c save_stats(st)
    save_capts(capts)
    
    asapts)
    
    asyncio.create_task(update_avg_top())
    asyncio.create_task(updateyncio.create_task(update_avg_top())
    asyncio.create_task(update_kills_top())
    asyncio_kills_top())
    asyncio.create_task(update_capts_list())
    
    await log_command_success.create_task(update_capts_list())
    
    await log_command_success(inter, "удалить_капт", 
                           (inter, "удалить_капт", 
                            f"Удален капт #{номер f"Удален капт #{номер} против {removed_capt['} против {removed_capt['vs']vs']}, снято {total_points_removed:.2f}}, снято {total_points_removed:.2f} баллов баллов")
    
    await inter.response.send_message(
        f"✅ Капт")
    
    await inter.response.send_message(
        f"✅ Капт против **{removed_capt['vs']}** удалён\n"
 против **{removed_capt['vs']}** удалён\n"
        f        f"📉 Снято баллов: **{total_points_"📉 Снято баллов: **{total_points_removedremoved:.2f}**",
        ephemeral=True
    )

@tree.command:.2f}**",
        ephemeral=True
    )

@tree.command(name="профиль", description="📊 Профиль игрока",(name="профиль", description="📊 Профиль игрока", guild=discord.Object(GUILD_ID))
@app_commands.describe( guild=discord.Object(GUILD_ID))
@app_commands.describe(игрок="Игрок")
async defигрок="Игрок")
 profile(inter: discord.Interaction, игрок: discord.Memberasync def profile(inter: discord.Interaction, игрок: discord.Member = None):
    = None):
    if not is_viewer(inter.user):
        await inter if not is_viewer(inter.user):
        await inter.response.send_message("❌ Нет доступа", ephemeral=True)
        return
    
.response.send_message("❌ Нет доступа", ephemeral=True)
        return
    
    await log_command_start(inter, "профиль", {"иг    await log_command_start(inter, "профиль", {"игрок": f"{игрок.рок": f"{игрок.mention if игрок else inter.user.mention}"mention if игрок else inter.user.mention}"})
    
    target = игрок or})
    
    target = игрок or inter.user
    
    # Получаем общую статистику
    st = inter.user
    
    # Получаем общую статистику
    st = load_stats load_stats()
    data = st.get(str(target.id))
    
    if not()
    data = st.get(str(target.id))
    
    if not data or data["games"] == 0:
 data or data["games"] == 0:
        await log_command_error(inter, "профиль", f"У        await log_command_error(inter, "профиль", f"У {target.mention} нет статистики")
        await inter.response.send_message(f" {target.mention} нет статистики")
        await inter.response.send_message(f"📭 У {target.mention} нет статистики", ephemeral=True)
       📭 У {target.mention} нет статистики", ephemeral=True)
        return
    
    # Получаем капты игрока
    player_capts return
    
    # Получаем капты игрока
    player_capts = get_player_capts(target.id)
    
    # Рассчиты = get_player_capts(target.id)
    
    # Рассчитываем винрейт
    wins = 0ваем винрейт
    wins = 0
   
    total_games = len(player_capts)
    for pc in player_c total_games = len(player_capts)
    for pc in player_capts:
        if pc["captapts:
        if pc["capt"]["win"]:
            wins += "]["win"]:
            wins += 1
    
1
    
    winrate = (wins / total_games * 100    winrate = (wins / total_games * 100) if total_games > 0 else ) if total_games > 0 else 0
    
    # Последние 5 каптов
    recent_c0
    
    # Последние 5 каптов
    recent_capts = player_capts[:5]
    
    # Последняя активностьapts = player_capts[:5]
    
    # Последняя активность
    last_activity = "Не
    last_activity = "Неизвестизвестно"
    if player_capts:
        last_capt = player_cно"
    if player_capts:
        last_capt = player_capts[0]
        try:
apts[0]
        try:
            dt = datetime.fromisoformat(last_capt["capt"]["date"])
            last_            dt = datetime.fromisoformat(last_capt["capt"]["date"])
            last_activity =activity = dt.strftime("%d.%m.%Y %H:%M")
 dt.strftime("%d.%m.%Y %H:%M")
        except        except:
            pass
    
    # Баллы
    total_points = get_player:
            pass
    
    # Баллы
    total_points = get_player_points(target.id)
    
    # Сред_points(target.id)
    
    # Средний урон и киллы
    avgний урон и киллы
    avg_dmg = data["damage"] // data["games"]
    avg_kills =_dmg = data["damage"] // data["games"]
    avg_kills = data["kills"] / data[" data["kills"] / data["games"]
    
    # Автоматически рассчитанные баллы по формуле
   games"]
    
    # Автоматически рассчитанные баллы по формуле
    auto_points = calculate_points_from_stats(data["damage"], data["kills auto_points = calculate_points_from_stats(data["damage"], data["kills"])
    
    # Создаем"])
    
    # Создаем embed
    embed = discord.Embed(
        title=f"📊 Профиль embed
    embed = discord.Embed(
        title=f"📊 Профиль {target.mention}",
        description=f"*Статистика игрока*",
 {target.mention}",
        description=f"*Статистика игрока*",
        color=0x3498db        color=0x3498db,
        timestamp=now_msk()
    )
    embed.set_thumbnail(url,
        timestamp=now_msk()
    )
    embed.set_thumbnail(url=target=target.display_avatar.url)
    
    # Основная статистика
    embed.add_field(
.display_avatar.url)
    
    # Основная статистика
    embed.add_field(
        name="📈 Основная статисти        name="📈 Основная статистика",
        value=f"```Игрка",
        value=f"```Игр:          {data['games']}\n"
:          {data['games']}\n"
              f"Винрейт:              f"Винрейт:      {winrate:.1f}%\n"
                   {winrate:.1f}%\n f"Побед:        {wins}\n"
             "
              f"Побед:        {wins}\n"
              f"Всего урона:  {data['damage']:,}\n"
              f" f"Всего урона:  {data['damage']:,}\n"
              f"ВсегоВсего киллов: {data['kills']}\n"
              f"Ср киллов: {data['kills']}\n"
              f"Ср.урон:      {avg_dmg:,.урон:      {avg_d}\n"
              f"Ср.киллы:    mg:,}\n"
              f"Ср.киллы:     {avg_kills:.1f}```",
        inline=False
    )
    
    # Баллы {avg_kills:.1f}```",
        inline=False
    )
    
    # Баллы
    embed.add_field(
        name
    embed.add_field(
        name="⭐="⭐ Баллы",
        value=f"**{total_points:.2f}**\ Баллы",
        value=f"**{total_points:.2f}**\n"
              f"*Формулаn"
              f"*Формула: 1 килл = 0.5 балла\n1: 1 килл = 0.5 балла\n1 урон = 0.001 балла*\n"
              f урон = 0.001 балла*\n"
              f"Авторасчет: {auto_points"Авторасчет: {auto_points:.2f}",
        inline=False
   :.2f}",
        inline=False
    )
    
    # Последние 5 ка )
    
    # Последние 5птов
    if recent_capts:
        capts_text = ""
        for каптов
    if recent_capts:
        capts_text = ""
        for pc in recent_capts:
            result = "✅ pc in recent_capts:
            result =" if pc["capt"]["win"] else "❌"
            try:
 "✅" if pc["capt"]["win"] else "❌"
            try:
                date_str = datetime.fromisoformat(pc["capt"]["date"]).strftime("%d.%m                date_str = datetime.fromisoformat(pc["capt"]["date"]).strftime("%d.%m")
            except:
                date_str =")
            except:
                date_str = "?? "??.??"
            
            capt_points = calculate_points_from_stats(pc["player_data.??"
            
            capt_points = calculate_points_from_stats(pc["player_data"]["damage"], pc["player_data"]["k"]["damage"], pc["player_data"]["kills"])
            capts_text += f"ills"])
            capts_text += f"**#{pc['index']}** vs {**#{pc['index']}** vs {pc['capt']['vs'][:15]} {result} - {date_str}\n"
           pc['capt']['vs'][:15]} {result} - {date_str}\n"
            capts_text += f"💥 {pc capts_text += f"💥 {pc['player_data']['damage']:,['player_data']['damage']} | ☠️ {pc['player_data']['kills']} |:,} | ☠️ {pc['player_data']['kills']} | ⭐ { ⭐ {capt_points:.2f}\n"
        
        embed.add_field(
            name="📅capt_points:.2f}\n"
        
        embed.add_field(
            name="📅 Послед Последние 5 каптов",
            value=capts_text,
            inline=False
ние 5 каптов",
            value=capts_text,
            inline=False
        )
        )
    
    # Последняя активность
    embed.add_field(
        name="    
    # Последняя активность
    embed.add_field(
        name="🕐🕐 Последняя активность",
        value=last_activity,
        inline=True
    )
 Последняя активность",
        value=last_activity,
        inline=True
    )
    
    embed.set_footer(text=f"ID: {target    
    embed.set_footer(text=f"ID: {target.id}")
    
    await inter.response.send_message(embed=embed, ephemeral=True)
.id}")
    
    await inter.response.send_message(embed=embed, ephemeral=True)
    await log_command_success(inter, "профиль", f"Показан профи    await log_command_success(inter, "профиль", f"Показан профиль {target.mention}")

@tree.commandль {target.mention}")

@tree.command(name="топ_баллы", description="⭐ Топ по баллам",(name="топ_баллы", description="⭐ Топ по баллам", guild=discord.Object(GUILD_ID))
@app_commands.describe(period="Пери guild=discord.Object(GUILD_ID))
@app_commands.describe(period="Период")
@app_commands.choices(од")
@app_commands.choices(period=[
period=[
    app_commands.Choice(name="За всё время", value="all"),
    app_commands.Choice    app_commands.Choice(name="За всё время", value="all"),
    app_commands(name="За неделю", value="week"),
    app_commands.Choice(name="За месяц.Choice(name="За неделю", value="week"),
    app_commands.Choice(name="", value="month")
])
async def top_points(inter: discord.Interaction, period:За месяц", value="month")
])
async def top_points(inter: discord.Interaction, period: str str = "all"):
    if not is_viewer(inter.user):
        await inter.response = "all"):
    if not is_viewer(inter.user):
        await inter.response.send_message("❌ Нет доступа", ephemeral.send_message("❌ Нет доступа", ephemeral=True)
        return
    
    await log_command_start=True)
        return
    
    await log_command_start(inter, "топ_баллы", {"period": period})
    
    await inter(inter, "топ_баллы", {"period": period})
    
    await inter.response.defer(ephemeral=True)
    
    try:
        if period == "week":
.response.defer(ephemeral=True)
    
    try:
        if period == "week":
            capt            capts = get_capts_in_period(7)
            period_text = "за неделюs = get_capts_in_period(7)
            period_text = "за неделю"
        elif period == "month":
            capt"
        elif period == "month":
            capts = get_capts_in_period(30)
            period_text = "за месяц"
s = get_capts_in_period(30)
            period_text = "за месяц"
        else:
            # Для "все время        else:
            # Для "все время" используем общие баллы из ба" используем общие баллы иззы
            points_db = load_points()
            
            if not points_db:
                await log базы
            points_db = load_points()
            
            if not points_db:
                await log_command_error_command_error(inter, "топ_баллы", "Нет данных по баллам(inter, "топ_баллы", "Нет данных по баллам")
               ")
                await inter.followup.send("📭 Нет данных по баллам", ephemeral=True)
 await inter.followup.send("📭 Нет данных по баллам", ephemeral=True)
                return
            
            # Сортируем по баллам
            sorted_points = sorted(points                return
            
            # Сортируем по баллам
            sorted_points = sorted(points_db.items(), key=lambda x: x[1], reverse=True)[:10]
            
            embed_db.items(), key=lambda x: x[1], reverse=True)[:10]
            
            = discord.Embed(
                title=f"⭐ ТОП-10 ПО БАЛЛАМ",
 embed = discord.Embed(
                title=f"⭐ ТОП-10 ПО БАЛЛАМ",
                description=f"*За                description=f"*За всё время*\n*1 килл = 0.5 балла, 1 урон всё время*\n*1 килл = 0.5 балла, 1 урон = 0.001 балла*",
                color=0xf = 0.001 балла*",
                color=0xf1c40f,
               1c40f,
                timestamp=now_ms timestamp=now_msk()
            )
            
            desc = ""
            for i, (uid, points) in enumeratek()
            )
            
            desc = ""
            for i, (uid, points) in enumerate(sorted_points, 1):
                try:
                    member = await inter.guild.fetch_member(int(sorted_points, 1):
                try:
                    member = await inter.guild.fetch_member(int(uid(uid))
                    name = f"{member.mention} ({member.display_name})"
                except:
                   ))
                    name = f"{member.mention} ({member.display_name})"
                except:
                    name = f"Игрок {uid}"
                
                if i <= 3:
                    desc name = f"Игрок {uid}"
                
                if i <= 3:
                    desc += f"{medal(i)} **{name}**\n"
                else:
                    desc += f += f"{medal(i)} **{name}**\n"
                else:
                    desc += f"`{i}.` **{name}"`{i}.` **{name}**\n"
                
                desc += f"**\n"
                
                desc += f"```Баллы:      {points:.2f}```\n"
            
            embed.description```Баллы:      {points:.2f}```\n"
            
            embed.description = desc
            await inter.followup.send(embed=embed, ephemeral=True)
            await log = desc
            await inter.followup.send(embed=embed, ephemeral=True)
            await log_command_success(inter, "топ__command_success(inter, "топ_баллы", f"Показан топ баллов за период: {period}")
            return
        
       баллы", f"Показан топ баллов за период: {period}")
            return
        
        # Для недели и месяца считаем баллы из ка # Для недели и месяца считаем баллы из каптов
        player_stats = {}
        for captптов
        player_stats = {}
        in capts:
            for player in capt["players"]:
                uid = str(player["user for capt in capts:
            for player in capt["players"]:
                uid = str(player["user_id"])
                if uid not in player_stats:
_id"])
                if uid not in player_stats:
                                       player_stats[uid] = {
                        "damage": 0,
                        "kills":  player_stats[uid] = {
                        "damage": 0,
                        "kills": 0,
                        "games": 0
                    }
               0,
                        "games": 0
                    }
                player_stats[uid]["damage"] += player player_stats[uid]["damage"] += player["damage"]
                player_stats[uid]["kills"] += player["kills"]
               ["damage"]
                player_stats[uid]["kills"] += player["kills"]
                player_stats[uid]["games"] += 1
        
        player_stats[uid]["games"] += 1
        
        # Рассчитываем баллы для каждого игрока # Рассчитываем баллы для каждого игрока
        player_points = []
        for uid, stats in player_stats.items():
            points = calculate
        player_points = []
        for uid, stats in player_stats.items():
            points = calculate_points_from_stats(stats["damage"], stats["k_points_from_stats(stats["damage"], stats["kills"])
            player_points.append((uid, pointsills"])
            player_points.append((uid, points, stats, stats))
        
        # Сортируем по баллам
        player_points.sort(key=lambda x:))
        
        # Сортируем по баллам
        player_points.sort(key=lambda x: x[1], reverse=True)
        
        if not player_points:
            await log_command_error(inter, x[1], reverse=True)
        
        if not player_points:
            await log_command_error(inter, "топ_баллы", "топ_баллы", f"Нет статистики {period_text}")
            await inter.followup.send(f"📭 Нет статистики {period_text}", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"⭐ ТОП-10 ПО f"Нет статистики {period_text}")
            await inter.followup.send(f"📭 Нет статистики {period_text}", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"⭐ ТОП-10 ПО БА БАЛЛАМ",
            description=f"*Статистика {period_text}*\nЛЛАМ",
            description=f"*Статистика {period_text}*\n*1 килл = 0.5 бал*1 килл = 0.ла, 1 урон = 0.001 балла*",
            color=5 балла, 1 урон = 0.001 балла*",
            color=0xf1c40f,
            timestamp=now_msk()
        )
        
        desc =0xf1c40f,
            timestamp=now_msk()
        )
        
        desc = ""
        for i, (uid, points, ""
        for i, (uid, points, stats) in enumerate(player_points[:10], 1):
            try:
                member = await inter.guild stats) in enumerate(player_points[:10], 1):
            try:
                member = await inter.guild.fetch_member(int(uid))
                name =.fetch_member(int(uid))
                name = f"{member.mention} ({member.display_name})"
            except:
                name = f" f"{member.mention} ({member.display_name})"
            except:
                name = f"Игрок {uid}"
            
            if i <= 3:
                desc += f"{medal(iИгрок {uid}"
            
            if i <= 3:
                desc += f"{medal(i)} **{name}**\n"
            else:
                desc += f"`{i}.`)} **{name}**\n"
            else:
                desc += f"`{i}.` **{name}**\n"
            
            **{name}**\n"
            
            desc += f"```Баллы:      {points desc += f"```Баллы:      {points:.2f}\nУрон:       {stats['damage']:,}\nКиллы::.2f}\nУрон:       {stats['damage']:,}\nКиллы:      {stats['kills']}\nИ      {stats['kills']}\nИгр:        {stats['games']}```\n"
        
        embed.description = desc
        
гр:        {stats['games']}```\n"
        
        embed.description = desc
        
        await inter.followup.send(embed=embed, ephemeral=True)
        await log_command_success        await inter.followup.send(embed=embed, ephemeral=True)
        await log_command_success(inter, "топ_б(inter, "топ_баллы", f"Показан топ баллов за период:аллы", f"Показан топ баллов за период: {period}")
            
    except Exception as e:
        await log_command_error(inter, "топ_ {period}")
            
    except Exception as e:
        await log_command_error(inter, "топ_баллы", str(e))
        print(fбаллы", str(e))
        print(f"❌ Ошибка в top_points: {e"❌ Ошибка в top_points: {e}")
        await inter.followup.send("❌ Произошла ошибка при выполнении команды}")
        await inter.followup.send("❌ Произошла ошибка при выполнении команды", ephemeral=True)

# ==================== АВТООБНОВЛЕНИЕ =================", ephemeral=True)

# ==================== АВТООБНОВЛЕНИЕ ====================
async def update_avg_top():
    """Обновление топа по среднему урону===
async def update_avg_top():
    """Обновление топа по среднему урону"""
    channel = client.get_channel(STAT"""
    channel = client.get_channel(STATS_S_AVG_CHANNEL_ID)
    if not channel:
        await log_sAVG_CHANNEL_ID)
    if not channel:
        await log_system_event("❌ Канал не найден", f"Канал STATS_AVG_CHANNEL_ID ({STATS_ystem_event("❌ Канал не найден", f"Канал STATS_AVG_CHANNEL_ID ({STATS_AVG_CHANNEL_ID}) не найден")
        return

    try:
        st = load_statsAVG_CHANNEL_ID}) не найден")
        return

    try:
        st = load_stats()
        
        filtered = {uid: d for uid, d in st.items() if d["games"]()
        
        filtered = {uid: d for uid, d in st.items() if d["games"] >= 3}
        
        if not filtered:
            embed = discord.Embed(
                title="🏆 >= 3}
        
        if not filtered:
            embed = discord.Embed(
                title="🏆 ТО ТОП-10 СРЕДНЕГО УРОНА",
               П-10 СРЕДНЕГО УРОНА",
                description="📭 Нет игроков с 3+ играми",
                color=0x9b59b6,
                description="📭 Нет игроков с 3+ играми",
                color=0x9b59b6,
                timestamp=now_msk()
            )
            embed.set_footer(text="Минимум 3 игры для участия timestamp=now_msk()
            )
            embed.set_footer(text="Минимум 3 игры для участия")
            
            async for msg in channel.history(limit=50):
                if msg.author.id == client")
            
            async for msg in channel.history(limit=50):
                if msg.author.id == client.user.id and msg.embeds:
                    if.user.id and msg.embeds:
                    if "Т "ТОП-10 СРЕДНЕГО УРОНА" in msg.embedsОП-10 СРЕДНЕГО УРОНА" in msg.embeds[0].title:
                        try:
                            await msg.edit(embed=[0].title:
                        try:
                            await msg.edit(embed=embed)
                            await log_system_event("✅ Топ урона обновленembed)
                            await log_system_event("✅ Топ урона обновлен", "Нет", "Нет игрок игроков с 3+ играми")
                            return
                        except Exception as e:
                           ов с 3+ играми")
                            return
                        except Exception as e:
                            await log await log_system_event("❌ Ошибка редактирования топа урона", f"Ошиб_system_event("❌ Ошибка редактирования топа урона", f"Ошибка:ка: {str(e)}")
            
            try:
                await channel.send(embed=embed)
                await log_system_event {str(e)}")
            
            try:
                await channel.send(embed=embed)
                await log_system_event("✅ Топ урона отправлен", "Н("✅ Топ урона отправлен", "Нет игроков с 3+ играми")
            except Exception as e:
                await log_system_event("ет игроков с 3+ играми")
            except Exception as e:
                await log_system_event("❌ Ошибка отправки топа урона❌ Ошибка отправки топа урона", f"Ошибка: {str(e)}")
            return

        users = sorted(filtered.items", f"Ошибка: {str(e)}")
            return

        users = sorted(filtered.items(), key=lambda x: x[1]["damage"]/x[1]["games"], reverse(), key=lambda x: x[1]["damage"]/x[1]["games"], reverse=True)[:10]

        embed = discord.Embed(
            title="🏆 ТОП-10 СРЕД=True)[:10]

        embed = discord.Embed(
            title="🏆 ТОП-10 СРЕДННЕГО УРОНА",
            color=0x9b59b6,
            timestamp=now_msk()
ЕГО УРОНА",
            color=0x9b59b6,
            timestamp=now_msk()
        )

        desc = ""
        for i, (uid, data) in enumerate(users, 1        )

        desc = ""
        for i, (uid, data) in enumerate(users, 1):
            try:
                member = await channel.guild.fetch_member(int(uid))
                name = member):
            try:
                member = await channel.guild.fetch_member(int(uid))
                name = member.display_name
            except:
                name = f"Игрок {uid}"

            avg = data["dam.display_name
            except:
                name = f"Игрок {uid}"

            avg = dataage"] // data["games"]
            leader_avg = users[0][1]["damage"] //["damage"] // data["games"]
            leader_avg = users[0][1]["damage"] // users[0][1]["games"]
            percent = (avg / leader_avg * 100) if leader_ users[0][1]["games"]
            percent = (avg / leader_avg * 100) ifavg > 0 else 0
            bar = progress_bar(percent)

            desc += f"{med leader_avg > 0 else 0
            bar = progress_bar(percent)

            desc += f"{medal(i)} **{i}. {name}**\n{bar} **{avg:,}**al(i)} **{i}. {name}**\n{bar} **{avg:,}** урона ({data['games']} иг урона ({data['games']} игр)\n\n"

        embed.description = desc
       р)\n\n"

        embed.description = desc
        embed.set_footer(text="Обновляется каждый час • Минимум 3 игры")

        found = False
 embed.set_footer(text="Обновляется каждый час • Минимум 3 игры")

        found = False
        async for msg in channel.history(limit=50):
            if msg.author.id == client.user.id and msg        async for msg in channel.history(limit=50):
            if msg.author.id == client.user.id and msg.embeds:
                if "ТОП.embeds:
                if "ТОП-10 СРЕДНЕГО УРОНА"-10 СРЕДНЕГО УРОНА" in msg.embeds[0].title:
                    try in msg.embeds[0].title:
                    try:
                        await msg.edit(embed=embed)
                        await log_system_event("✅ Топ уро:
                        await msg.edit(embed=embed)
                        await log_system_event("✅ Топ урона обна обновлен", f"Обновлено {len(users)} игроков")
                        found = True
новлен", f"Обновлено {len(users)} игроков")
                        found = True
                        break
                    except Exception as e:
                        await log                        break
                    except Exception as e:
                        await log_system_event("❌ Ошибка редактирования топа урона", f"Ошиб_system_event("❌ Ошибка редактирования топа урона", f"Ошибка: {str(e)}")
                        found = False
        
ка: {str(e)}")
                        found = False
        
        if not found:
            try:
                await channel.send        if not found:
            try:
                await channel.send(embed=embed)
                await log_system_event("✅ Топ урона отправлен", f"От(embed=embed)
                await log_system_event("✅ Топ урона отправлен", f"Отправлено {len(users)} игроковправлено {len(users)} игроков")
            except Exception as e:
                await log_system_event("❌ Ошибка отправки т")
            except Exception as e:
                await log_system_event("❌ Ошибка отправки топа урона", f"Ошибка: {опа урона", f"Ошибка: {str(e)}")
                
    except Exception as e:
        await log_system_event("❌ Криstr(e)}")
                
    except Exception as e:
        await log_system_event("❌ Критическая ошибка в update_avg_top", f"Ошибка: {str(e)}")

async def updateтическая ошибка в update_avg_top", f"Ошибка: {str(e)}")

async def update_kills_kills_top():
    """Обновление топа по киллам"""
    channel = client.get_channel(STAT_top():
    """Обновление топа по киллам"""
    channel = client.get_channel(S_KILLS_CHANNEL_ID)
    if not channel:
        await log_system_event("❌STATS_KILLS_CHANNEL_ID)
    if not channel:
        await log_system_event("❌ Канал не найден", f"Канал STATS Канал не найден", f"Канал STATS_KILLS_CHANNEL_ID ({STATS_KILLS_CHANNEL_ID}) не найден")
_KILLS_CHANNEL_ID ({STATS_KILLS_CHANNEL_ID}) не найден")
        return

    try:
        st = load_stats()
        
               return

    try:
        st = load_stats()
        
        if not st:
            embed = discord.Embed if not st:
            embed = discord.Embed(
               (
                title="☠️ ТОП-10 ПО КИЛЛАМ",
                description="📭 title="☠️ ТОП-10 ПО КИЛЛАМ",
                description="📭 Статистика пуста",
                color=0xe74c3c,
                timestamp=now_msk()
            Статистика пуста",
                color=0xe74c3c,
                timestamp=now_msk()
            )
            embed.set_footer(text="Обновляется каждый час")
            
            async for msg in channel.history( )
            embed.set_footer(text="Обновляется каждый час")
            
            async for msg in channel.history(limit=50):
                if msg.author.id == client.user.id and msg.embeds:
                    if "ТОlimit=50):
                if msg.author.id == client.user.id and msg.embeds:
                    if "ТОП-10 ПО КИЛЛАМ" in msg.embeds[0].title:
                        try:
                           П-10 ПО КИЛЛАМ" in msg.embeds[0].title:
                        try:
                            await msg await msg.edit(embed=embed)
                            await log_system_event("✅ Топ киллов обновлен", "Статисти.edit(embed=embed)
                            await log_system_event("✅ Топ киллов обновлен", "Статистика пуста")
                            return
                        except Exception as e:
                            await log_system_event("❌ Ошибка пуста")
                            return
                        except Exception as e:
                            await log_system_event("❌ Ошибка редактирования топа киллов", f"Ошибка: {str(e)}")
            
            tryка редактирования топа киллов", f"Ошибка: {str(e)}")
            
            try:
                await channel.send(embed=embed)
                await:
                await channel.send(embed=embed)
                await log_system_event("✅ Топ кил log_system_event("✅ Топ киллов отправлов отправлен", "Статистика пуста")
            except Exception as e:
                await log_system_event("❌лен", "Статистика пуста")
            except Exception as e:
                await log_system_event("❌ Ошибка отправки топа киллов", f"Ошибка: {str(e)}")
 Ошибка отправки топа киллов", f"Ошибка: {str(e)}")
            return

        users = sorted(st.items(), key=lambda            return

        users = sorted(st.items(), key=lambda x: x[1]["kills"], reverse=True)[:10]

        embed = discord.Embed(
            title=" x: x[1]["kills"], reverse=True)[:10]

        embed = discord.Embed(
            title="☠️ ТОП-10 ПО КИЛЛА☠️ ТОП-10 ПО КИЛЛАМ",
            color=0xe74c3c,
            timestamp=now_msk()
        )

        desc =М",
            color=0xe74c3c,
            timestamp=now_msk()
        )

        desc = ""
        for i, (uid, data) in enumerate ""
        for i, (uid, data) in enumerate(users, 1):
            try:
                member =(users, 1):
            try:
                member = await channel.guild.fetch_member(int(uid))
                await channel.guild.fetch_member(int(uid))
                name = member.display_name
            except:
                name = f"Игрок {uid}"

            leader_k name = member.display_name
            except:
                name = f"Игрок {uid}"

            leader_kills = users[0][1]["kills"]
            percent = (data["kills"] / leader_killsills = users[0][1]["kills"]
            percent = (data["kills"] / leader_kills * 100) if leader_kills > 0 else 0
            bar = progress_bar(percent * 100) if leader_kills > 0 else 0
            bar = progress_bar(percent)

            desc += f"{medal(i)} **{i}.)

            desc += f"{medal(i)} **{i}. {name}**\n{bar} **{data {name}**\n{bar} **{data['kills']}** киллов ({data['games']} игр)\n\n"

        embed.description['kills']}** киллов ({data['games']} игр)\n\n"

        embed.description = desc
        embed.set_footer(text="Обнов = desc
        embed.set_footer(text="Обновляется каждый час")

        found = False
        async forляется каждый час")

        found = False
        async for msg in channel.history(limit=50):
            if msg.author.id == client.user.id and msg.embeds msg in channel.history(limit=50):
            if msg.author.id == client.user.id and msg.embeds:
                if "ТОП-10 ПО КИЛЛАМ" in msg.embeds[0].:
                if "ТОП-10 ПО КИЛЛАМ" in msg.embeds[0].title:
                    try:
                        await msg.edit(embed=title:
                    try:
                        await msg.edit(embed=embed)
                        await log_system_event("✅ Топ киллов обновлен", fembed)
                        await log_system_event("✅ Топ киллов обновлен", f"Обнов"Обновлено {len(users)} игроков")
                        found = True
                        break
                    except Exception as e:
                       лено {len(users)} игроков")
                        found = True
                        break
                    except Exception as e:
                        await log_system_event("❌ Ошибка редактирования топа киллов", f"Ошиб await log_system_event("❌ Ошибка редактирования топа киллов", f"Ошибка: {str(e)}")
                        found = False
        
ка: {str(e)}")
                        found = False
        
        if not found:
            try:
                await channel.send        if not found:
            try:
                await channel.send(embed=embed)
                await log_system_event("✅ Топ киллов отправлен", f"Отправлено(embed=embed)
                await log_system_event("✅ Топ киллов отправлен", f"От {len(users)} игроков")
            except Exception as e:
                await log_system_event("❌правлено {len(users)} игроков")
            except Exception as e:
                await log_system_event("❌ Ошибка отправки топа киллов", f Ошибка отправки топа киллов", f"Ошибка: {str(e)}")
                
    except Exception as e:
        await log_system_event(""Ошибка: {str(e)}")
                
    except Exception as e:
        await log_system_event("❌ Критическая ошибка в update_kills_top", f"Ошибка: {str(e)}❌ Критическая ошибка в update_kills_top", f"Ошибка: {str(e)}")

async def update_capts_list():
    """Об")

async def update_capts_list():
    """Обновление списка каптов"""
    channel = client.get_channel(CAPTS_LIST_CHANNEL_ID)
новление списка каптов"""
    channel = client.get_channel(CAPTS_LIST_CHANNEL_ID)
    if    if not channel:
        await log_system_event("❌ Канал не найден", f"Канал CAPTS not channel:
        await log_system_event("❌ Канал не найден", f"Канал CAPTS_LIST_CHANNEL_ID ({CAPTS_LIST_CH_LIST_CHANNEL_ID ({CAPTS_LIST_CHANNEL_ID}) не найден")
        return

   ANNEL_ID}) не найден")
        return

    try:
        view = CaptsListView(channel.guild, "all")
 try:
        view = CaptsListView(channel.guild, "all")
        embed = await view.create_embed()

        found = False
        async for msg in channel.history(limit        embed = await view.create_embed()

        found = False
        async for msg in channel.history(limit=50):
            if msg.author.id == client.user.id and msg.embeds:
                if "История ка=50):
            if msg.author.id == client.user.id and msg.embeds:
                if "История каптов" in msg.embeds[0].titleптов" in msg.embeds[0].title:
                    try:
                        await msg.edit(embed=embed, view=view)
                        await log_system_event("✅ С:
                    try:
                        await msg.edit(embed=embed, view=view)
                        await log_system_event("✅ Список каптов обновлен", f"Загружено {len(view.capts)} капписок каптов обновлен", f"Загружено {len(view.capts)} каптов")
                        found = True
                        break
                    except Exception as e:
                        await log_system_event("тов")
                        found = True
                        break
                    except Exception as e:
                        await log_system_event("❌ Ошибка редактирования списка каптов❌ Ошибка редактирования списка каптов", f", f"Ошибка: {str(e)}")
                        found = False
        
        if not found:
            try:
                await channel"Ошибка: {str(e)}")
                        found = False
        
        if not found:
            try:
                await channel.send(embed=embed, view=view)
.send(embed=embed, view=view)
                await                await log_system_event("✅ Список каптов отправлен", f"Загружено {len(view log_system_event("✅ Список каптов отправлен", f"Загружено {len(view.capts)} каптов")
            except Exception as.capts)} каптов")
            except Exception as e:
                await log_system_event("❌ Ошибка отправки списка каптов", f"Ошиб e:
                await log_system_event("❌ Ошибка отправки списка каптов", f"Ошибка: {str(e)}")
                
    except Exception asка: {str(e)}")
                
    except Exception as e:
        await log_system_event("❌ Критическая ошибка в update_capts_list", e:
        await log_system_event("❌ Критическая ошибка в update_capts_list", f"Ошибка: {str(e)}")

async def update f"Ошибка: {str(e)}")

async def update_admin_menu():
    """Обновление админ-мен_admin_menu():
    """Обновление админ-меню"""
    channel = client.get_channel(ADMIN_MENU_CHANNEL_ID)
    if not channelю"""
    channel = client.get_channel(ADMIN_MENU_CHANNEL_ID)
    if not channel:
        return
    
    try:
        embed = discord.Embed(
            title="👑 АДМИН ПАНЕ:
        return
    
    try:
        embed = discord.Embed(
            title="👑 АДМИН ПАНЕЛЬ УПРАВЛЕНИЯ",
            description="*Используйте кнопки ниже для управления статистикой*\ЛЬ УПРАВЛЕНИЯ",
            description="*Используйте кнопки ниже для управления статистикой*\n\n"
                       "**Формат вn\n"
                       "**Формат ввода:**\n"
                       "• **Редактивода:**\n"
                       "• **Редактировать игрока:** ID, номер капта, кировать игрока:** ID, номер капта, киллыллы, урон, удалить (1/0)\n"
                       "• **Баллы:** ID,, урон, удалить (1/0)\n"
                       "• **Баллы:** ID, изменение (+/-)\n"
                       "• **Редактировать капт:** номер, название (не изменение (+/-)\n"
                       "• **Редактировать капт:** номер, название (не обязательно), win/lose (не обязательно)",
            color=0xe74c3c,
            timestamp=now обязательно), win/lose (не обязательно)",
            color=0xe74c3c,
            timestamp=now_msk()
        )
        
        # Статистика
        stats = load_stats()
        capts = load_capts_msk()
        )
        
        # Статистика
        stats = load_stats()
        capts = load_capts()
        points_db = load_points()
        
        total_points = sum(points_db.values())
        
        embed.add_field(
           ()
        points_db = load_points()
        
        total_points = sum(points_db.values())
        
        embed.add_field(
            name="📊 Статистика",
            value=f" name="📊 Статистика",
            value=f"Всего каптов: **{len(captsВсего каптов: **{len(capts)}**\n"
                  f"Игроков в базе: **{len(stats)}**\)}**\n"
                  f"Игроков в базе: **{len(stats)}**\n"
                  f"Всего баллов: **{n"
                  f"Всего баллов: **{total_points:.2f}**\n"
                  f"Последнее обновление: {now_msk().strtotal_points:.2f}**\n"
                  f"Последнее обновление: {now_msk().strftime('%d.%m.%Y %H:%M')}",
            inline=False
        )
        
        # Информаftime('%d.%m.%Y %H:%M')}",
            inline=False
        )
        
        # Информация о баллах
        embed.add_field(
            name="⭐ция о баллах
        embed.add_field(
            name="⭐ Система баллов",
            value="**Ф Система баллов",
            value="**Формула:**\n"
                  "1 киллормула:**\n"
                  "1 килл = 0.5 балла\n"
                  "1 урон = 0.001 балла\n\n"
                  " = 0.5 балла\n"
                  "1 урон = 0.001 балла\n\n"
                  "**В недельном отчете:**\n"
                  "• Показываются баллы за неделю\n"
                  "**В недельном отчете:**\n"
                  "• Показываются баллы за неделю\n"
                  "• У топ-10 снимается 10% баллов",
• У топ-10 снимается 10% баллов",
            inline=False
        )
        
        view = AdminMenu            inline=False
        )
        
        view = AdminMenuView()
        
        # Ищем существующее сообщение
        async for msg in channel.history(limit=50):
View()
        
        # Ищем существующее сообщение
        async for msg in channel.history(limit=50):
            if msg.author.id == client.user.id and msg.embeds:
                if "АДМИН ПАН            if msg.author.id == client.user.id and msg.embeds:
                if "АДМИН ПАНЕЛЬ УПРАВЛЕНИЯ" in msg.embЕЛЬ УПРАВЛЕНИЯ" in msg.embeds[0].title:
                    try:
                        await msgeds[0].title:
                    try:
                        await msg.edit(.edit(embed=embed, view=view)
                        return
                    except:
                        pass
        
        # Если не наembed=embed, view=view)
                        return
                    except:
                        pass
        
        # Если не нашли, отправляем новое
        await channel.send(embed=embed, view=view)
        
    except Exception as e:
       шли, отправляем новое
        await channel.send(embed=embed, view=view)
        
    except Exception as e:
        await log_system_event("❌ Ошибка обновления await log_system_event("❌ Ошибка обновления админ-меню", f"Ошибка: админ-меню", f"Ошибка: {str(e)}")

@tasks.loop(hours=1)
 {str(e)}")

@tasks.loop(hours=1)
async def auto_update():
    """Автоматическое обasync def auto_update():
    """Автоматическое обновление топов каждый час"""
    await log_system_event("новление топов каждый час"""
    await log_system_event("⏰ Начало автообновления", "Запущено автоматическое обновление топов")
    await⏰ Начало автообновления", "Запущено автоматическое обновление топов")
    await update_avg_top()
    await update_kills_top()
    await update_avg_top()
    await update_kills_top()
    await update_capts_list()
    await log_system_event update_capts_list()
    await log_system_event("✅ Автообновление завершено", "Все топы успешно обновлены")

# ==================== СО("✅ Автообновление завершено", "Все топы успешно обновлены")

# ==================== СОБЫТИЯ ====================
@client.event
async def on_ready():
    print(f"✅ Бот запущенБЫТИЯ ====================
@client.event
async def on_ready():
    print(f"✅: {client.user}")
    
    try:
        synced = await tree.sync(guild=discord.Object(GUILD Бот запущен: {client.user}")
    
    try:
        synced = await tree.sync(guild=discord.Object(G_ID))
        print(f"✅ Команды синхронизированы: {len(synced)} команд") 
UILD_ID))
        print(f"✅ Команды синхронизированы: {len(synced)} команд        
        await log_system_event("✅ Бот запущен", f"Бот успешно запущен. Синх") 
        
        await log_system_event("✅ Бот запущен", f"Бот успешно запущен. Синхронизировано {len(synced)} команд")
        
        for cmd in synced:
            print(f"  • /ронизировано {len(synced)} команд")
        
        for cmd in synced:
            print(f"  • /{cmd.name}")
    except Exception as e:
        print(f"{cmd.name}")
    except Exception as e:
        print❌ Ошибка синхронизации: {e}")
        await log_system_event("❌(f"❌ Ошибка синхронизации: {e}")
        await log_system_event("❌ Ошибка синхронизации", f"Ошибка: {str(e)}")
    
    if not auto_update.is_running():
        Ошибка синхронизации", f"Ошибка: {str(e)}")
    
    if not auto_update.is_running():
        auto_update.start()
        print("✅ Автообнов auto_update.start()
        print("✅ Автообновление запущено")
        await log_system_event("✅ Автообновление запущено", "Топыление запущено")
        await log_system_event("✅ Автообновление запущено", "Топы будут обновляться каждый час")
    
    if not weekly_report будут обновляться каждый час")
    
    if not weekly_report_task.is_running():
        weekly_report_task.start()
        print("_task.is_running():
        weekly_report_task.start()
        print("✅ Недельный отчет активирован")
        await log_system_event("✅ Недельный отчет активирован", "✅ Недельный отчет активирован")
        await log_system_event("✅ Недельный отчет активирован", "Отчеты будут отправляться каждую неделю")
Отчеты будут отправляться каждую неделю")
    
       
    # Обновляем все списки при запуске
    try:
        await log_system_event("🔄 Об # Обновляем все списки при запуске
    try:
        await log_system_event("🔄 Обновление при запуске", "Начато принудительное обновновление при запуске", "Начато принудительное обновление топов при запуске")
        await update_captление топов при запуске")
        await update_capts_list()
        await update_avg_top()
        await update_kills_top()
        
        # Создаем админs_list()
        await update_avg_top()
        await update_kills_top()
        
        # Создаем админ-меню
        await update_admin_menu()
        
        await log-меню
        await update_admin_menu()
        
        await log_system_event("✅ Обновление завершено", "Все топы обновлены при запуске")
        print("_system_event("✅ Обновление завершено", "Все топы обновлены при запуске")
        print("✅ Все✅ Все списки обновлены при запуске")
    except Exception as e:
        print(f"⚠️ Ошибка при об списки обновлены при запуске")
    except Exception as e:
        print(f"⚠️ Ошибка при обновлении списков: {e}")
        awaitновлении списков: {e}")
        await log_system_event("❌ Ошибка обновления", f" log_system_event("❌ Ошибка обновления", f"Ошибка при обновлении списков: {str(eОшибка при обновлении списков: {str(e)})}")

@client.event
async def on_member_remove(member: discord.Member):
    st = load_stats()
    uid =")

@client.event
async def on_member_remove(member: discord.Member):
    st = load_stats()
    uid = str(member.id)
    
    if uid in st:
 str(member.id)
    
    if uid in st:
        del st[uid]
        save_stats(st)
        
        # Также удаляем баллы
        points_db = load_points()
               del st[uid]
        save_stats(st)
        
        # Также удаляем баллы
        points_db = load_points()
        if uid in points_db:
            del points_db[uid]
            save_points(points_db)
        
        await log if uid in points_db:
            del points_db[uid]
            save_points(points_db)
        
        await log_system_system_event("👤 Игрок покинул сервер", 
                             f"Игрок {member.mention}_event("👤 Игрок покинул сервер", 
                             f"Игрок {member.mention} ({member.display_name}) покинул сервер. Статистика и ({member.display_name}) покинул сервер. Статистика и баллы удалены.")
        
        asyncio.create_task(update баллы удалены.")
        
        asyncio.create_task(update_avg_top())
        asyncio.create_task(update_kills_top())

# ==================== ЗАПУСК =_avg_top())
        asyncio.create_task(update_kills_top())

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    # Созда===================
if __name__ == "__main__":
    # Сем файлы базы данных, если они не существуют
    for db in [DB_STATS, DB_CAPTSоздаем файлы базы данных, если они не существуют
    for db in [DB_STATS, DB_CAPTS, DB_POINTS]:
        if not os.path.exists(db):
, DB_POINTS]:
        if not os.path.exists(db):
            with open(db, "w", encoding="utf-8") as f:
                if db == DB_STATS            with open(db, "w", encoding="utf-8") as f:
                if db == DB_STATS:
                   :
                    json.dump({}, f)
                elif db == DB_CAPTS:
                    json.dump([], f)
                elif json.dump({}, f)
                elif db == DB_CAPTS:
                    json.dump([], f)
                elif db == DB_POINTS:
                    json.dump({}, f)
            print(f"📁 Создан {db}")

 db == DB_POINTS:
                    json.dump({}, f)
            print(f"📁 Создан {db}")

    try:
        client.run(TOKEN)
    except Exception as e:
    try:
        client.run(TOKEN)
    except Exception as        print(f"❌ Критическая ошибка: {e}")
