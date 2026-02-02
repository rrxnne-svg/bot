# -------------- bot.py (исправленная версия 7.2) --------------
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
ADMIN_MENU_CHANNEL_ID = 1467757228189810799  # Обновленный ID для админ меню
WEEKLY_REPORT_CHANNEL_ID = 1467757665076776960  # Обновленный ID для недельных отчетов

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
    if result_text not in ["win", "lose", "победа", "поражение", "в", "п"]:
        await log_command_error(inter, "добавить_капт", f"Неверный результат: {результат}")
        await inter.response.send_message("❌ Результат: win или lose", ephemeral=True)
        return
    
    win = result_text in ["win", "победа", "в"]
    
    capt_date = now_msk()
    if дата:
        try:
            naive_dt = datetime.strptime(дата, "%d.%m.%Y %H:%M")
            capt_date = naive_dt.replace(tzinfo=MSK_TZ)
        except:
            try:
                naive_dt = datetime.strptime(дата, "%d.%m.%Y")
                capt_date = naive_dt.replace(tzinfo=MSK_TZ)
            except:
                await log_command_error(inter, "добавить_капт", f"Неверный формат даты: {дата}")
                await inter.response.send_message("❌ Неверный формат даты", ephemeral=True)
                return
    
    new_capt = {
        "vs": против.strip(),
        "date": capt_date.isoformat(),
        "win": win,
        "players": []
    }
    
    capts = load_capts()
    capts.append(new_capt)
    save_capts(capts)
    
    asyncio.create_task(update_capts_list())
    
    await log_command_success(inter, "добавить_капт", f"Капт против {против} создан")
    
    await inter.response.send_message(
        f"✅ Капт против **{против}** создан!\n"
        f"Результат: {'✅ Победа' if win else '❌ Поражение'}\n"
        f"Дата: {capt_date.strftime('%d.%m.%Y %H:%M')} МСК",
        ephemeral=True
    )

@tree.command(name="добавить_игрока", description="👤 Добавить игрока в капт", guild=discord.Object(GUILD_ID))
@app_commands.describe(
    игрок="@упоминание или ID",
    урон="Урон",
    киллы="Киллы",
    номер_капта="Номер капта (1 = последний)"
)
async def add_player(inter: discord.Interaction, игрок: discord.Member, урон: int, киллы: int, номер_капта: int = 1):
    if not is_admin(inter.user):
        await inter.response.send_message("❌ Нет доступа", ephemeral=True)
        return
    
    await log_command_start(inter, "добавить_игрока", {
        "игрок": f"{игрок.mention} ({игрок.display_name})",
        "урон": урон,
        "киллы": киллы,
        "номер_капта": номер_капта
    })

    capts = load_capts()
    if номер_капта < 1 or номер_капта > len(capts):
        await log_command_error(inter, "добавить_игрока", f"Капт не найден: номер {номер_капта}")
        await inter.response.send_message("❌ Капт не найден", ephemeral=True)
        return

    capt = capts[-номер_капта]
    
    if any(p["user_id"] == игрок.id for p in capt["players"]):
        await log_command_error(inter, "добавить_игрока", f"Игрок уже в капте: {игрок.display_name}")
        await inter.response.send_message(f"❌ {игрок.mention} уже в капте", ephemeral=True)
        return

    capt["players"].append({
        "user_id": игрок.id,
        "user_name": игрок.display_name,
        "damage": урон,
        "kills": киллы
    })

    st = load_stats()
    uid = str(игрок.id)
    if uid not in st:
        st[uid] = {"damage": 0, "kills": 0, "games": 0}
    
    st[uid]["damage"] += урон
    st[uid]["kills"] += киллы
    st[uid]["games"] += 1
    
    # Добавляем баллы игроку
    points_added, new_points = add_points_to_player(игрок.id, урон, киллы)
    
    save_stats(st)
    save_capts(capts)
    
    asyncio.create_task(update_avg_top())
    asyncio.create_task(update_kills_top())
    asyncio.create_task(update_capts_list())
    
    await log_command_success(inter, "добавить_игрока", 
                            f"Игрок {игрок.mention} добавлен в капт #{номер_капта}, начислено {points_added:.2f} баллов")
    
    await inter.response.send_message(
        f"✅ {игрок.mention} добавлен!\n"
        f"💥 Урон: **{урон:,}** │ ☠️ Киллы: **{киллы}**\n"
        f"⭐ Начислено баллов: **{points_added:.2f}**\n"
        f"💰 Общий баланс: **{new_points:.2f}**",
        ephemeral=True
    )

@tree.command(name="загрузить_игроков", description="📤 Загрузить игроков из текста", guild=discord.Object(GUILD_ID))
@app_commands.describe(
    данные="ID урон киллы (каждый с новой строки)",
    номер_капта="Номер капта"
)
async def upload_players(inter: discord.Interaction, данные: str, номер_капта: int = 1):
    if not is_admin(inter.user):
        await inter.response.send_message("❌ Нет доступа", ephemeral=True)
        return
    
    await log_command_start(inter, "загрузить_игроков", {
        "данные": f"{len(данные.splitlines())} строк",
        "номер_капта": номер_капта
    })
    
    await inter.response.defer(ephemeral=True)
    
    try:
        capts = load_capts()
        if номер_капта < 1 or номер_капта > len(capts):
            await log_command_error(inter, "загрузить_игроков", f"Капт не найден: номер {номер_капта}")
            await inter.followup.send("❌ Капт не найден", ephemeral=True)
            return
        
        capt = capts[-номер_капта]
        lines = данные.strip().split('\n')
        added = 0
        errors = []
        total_points_added = 0
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            parts = line.split()
            if len(parts) < 3:
                errors.append(f"❌ Неверный формат: {line}")
                continue
            
            try:
                user_id = int(parts[0])
                damage = int(parts[1].replace('k', '000').replace('K', '000'))
                kills = int(parts[2])
            except:
                errors.append(f"❌ Ошибка парсинга: {line}")
                continue
            
            try:
                member = await inter.guild.fetch_member(user_id)
            except:
                errors.append(f"❌ Игрок {user_id} не найден")
                continue
            
            if any(p["user_id"] == user_id for p in capt["players"]):
                errors.append(f"⚠️ {member.mention} уже добавлен")
                continue
            
            capt["players"].append({
                "user_id": user_id,
                "user_name": member.display_name,
                "damage": damage,
                "kills": kills
            })
            
            st = load_stats()
            uid = str(user_id)
            if uid not in st:
                st[uid] = {"damage": 0, "kills": 0, "games": 0}
            st[uid]["damage"] += damage
            st[uid]["kills"] += kills
            st[uid]["games"] += 1
            
            # Добавляем баллы
            points_added, _ = add_points_to_player(user_id, damage, kills)
            total_points_added += points_added
            
            save_stats(st)
            
            added += 1
        
        save_capts(capts)
        
        asyncio.create_task(update_avg_top())
        asyncio.create_task(update_kills_top())
        asyncio.create_task(update_capts_list())
        
        await log_command_success(inter, "загрузить_игроков", 
                                f"Добавлено {added} игроков, начислено {total_points_added:.2f} баллов, ошибок: {len(errors)}")
        
        msg = f"✅ Добавлено игроков: **{added}**\n"
        msg += f"⭐ Всего начислено баллов: **{total_points_added:.2f}**"
        
        if errors:
            msg += f"\n\n⚠️ Ошибки:\n" + "\n".join(errors[:5])
            if len(errors) > 5:
                msg += f"\n... и ещё {len(errors)-5}"
        
        await inter.followup.send(msg, ephemeral=True)
            
    except Exception as e:
        await log_command_error(inter, "загрузить_игроков", str(e))
        print(f"❌ Ошибка в upload_players: {e}")
        await inter.followup.send("❌ Произошла ошибка при выполнении команды", ephemeral=True)

@tree.command(name="загрузить_капты", description="📁 Загрузить капты из файла", guild=discord.Object(GUILD_ID))
@app_commands.describe(
    файл="Текстовый файл с каптами",
    результат="Результат по умолчанию (win/lose)"
)
async def upload_capts(inter: discord.Interaction, файл: discord.Attachment, результат: str = "win"):
    if not is_admin(inter.user):
        await inter.response.send_message("❌ Нет доступа", ephemeral=True)
        return
    
    await log_command_start(inter, "загрузить_капты", {
        "файл": файл.filename,
        "результат": результат
    })
    
    await inter.response.defer(ephemeral=True)
    
    try:
        if not файл.filename.endswith('.txt'):
            await log_command_error(inter, "загрузить_капты", "Файл не .txt")
            await inter.followup.send("❌ Файл должен быть .txt", ephemeral=True)
            return
        
        content = await файл.read()
        text = content.decode('utf-8')
        
        capts = load_capts()
        st = load_stats()
        lines = text.strip().split('\n')
        
        current_capt_players = []
        current_family_name = ""
        current_date_time = None
        current_result = результат
        added_capts = 0
        errors = []
        
        def save_current_capt():
            nonlocal added_capts
            if current_capt_players and current_family_name:
                try:
                    if current_date_time:
                        dt = current_date_time
                    else:
                        dt = now_msk()
                    
                    new_capt = {
                        "vs": current_family_name,
                        "date": dt.isoformat(),
                        "win": current_result.lower() in ["win", "w", "1", "true", "победа", "в"],
                        "players": current_capt_players.copy()
                    }
                    capts.append(new_capt)
                    added_capts += 1
                    
                    for player in current_capt_players:
                        uid = str(player["user_id"])
                        if uid not in st:
                            st[uid] = {"damage": 0, "kills": 0, "games": 0}
                        st[uid]["damage"] += player["damage"]
                        st[uid]["kills"] += player["kills"]
                        st[uid]["games"] += 1
                        
                except Exception as e:
                    errors.append(f"❌ Ошибка сохранения капта: {str(e)}")
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            
            if not line:
                save_current_capt()
                current_capt_players = []
                current_family_name = ""
                current_date_time = None
                current_result = результат
                continue
            
            if line.lower().startswith("семья"):
                save_current_capt()
                current_capt_players = []
                current_family_name = ""
                current_date_time = None
                current_result = результат
                
                try:
                    header = line[6:].strip()
                    date_match = re.search(r'(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2})', header)
                    if date_match:
                        date_time_str = date_match.group(1)
                        header_without_date = re.sub(r'(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2})', '', header).strip()
                        
                        dt = datetime.strptime(date_time_str, "%d.%m.%Y %H:%M")
                        dt = dt.replace(tzinfo=MSK_TZ)
                        current_date_time = dt
                        current_family_name = header_without_date
                    else:
                        current_family_name = header
                        current_date_time = now_msk()
                    
                    header_lower = header.lower()
                    if "win" in header_lower or "победа" in header_lower:
                        current_result = "win"
                    elif "lose" in header_lower or "поражение" in header_lower:
                        current_result = "lose"
                    
                except Exception as e:
                    errors.append(f"❌ Строка {line_num}: Ошибка парсинга заголовка - {str(e)}")
                    current_family_name = "Противник"
                    current_date_time = now_msk()
            
            elif current_family_name:
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        user_id = int(parts[0])
                        damage = int(parts[1])
                        kills = int(parts[2])
                        
                        if any(p["user_id"] == user_id for p in current_capt_players):
                            errors.append(f"⚠️ Строка {line_num}: Игрок {user_id} уже в капте")
                            continue
                        
                        try:
                            member = await inter.guild.fetch_member(user_id)
                            user_name = member.display_name
                        except:
                            user_name = f"Игрок {user_id}"
                        
                        current_capt_players.append({
                            "user_id": user_id,
                            "user_name": user_name,
                            "damage": damage,
                            "kills": kills
                        })
                        
                    except Exception as e:
                        errors.append(f"❌ Строка {line_num}: Ошибка обработки игрока - {str(e)}")
                else:
                    errors.append(f"❌ Строка {line_num}: Неверный формат данных игрока")
        
        save_current_capt()
        
        if added_capts > 0:
            save_capts(capts)
            save_stats(st)
            
            asyncio.create_task(update_avg_top())
            asyncio.create_task(update_kills_top())
            asyncio.create_task(update_capts_list())
        
        await log_command_success(inter, "загрузить_капты", f"Загружено {added_capts} каптов, ошибок: {len(errors)}")
        
        if added_capts == 0:
            msg = "❌ Не удалось загрузить ни одного капта"
            if errors:
                msg += f"\n\nОшибки:\n" + "\n".join(errors[:5])
        else:
            msg = f"✅ Загружено каптов: **{added_capts}**"
            if errors:
                msg += f"\n\n⚠️ Ошибки ({len(errors)}):\n" + "\n".join(errors[:5])
                if len(errors) > 5:
                    msg += f"\n... и ещё {len(errors) - 5} ошибок"
        
        await inter.followup.send(msg, ephemeral=True)
        
    except Exception as e:
        await log_command_error(inter, "загрузить_капты", str(e))
        print(f"❌ Ошибка в upload_capts: {e}")
        await inter.followup.send(f"❌ Ошибка загрузки: {str(e)}", ephemeral=True)

@tree.command(name="удалить_капт", description="🗑️ Удалить капт", guild=discord.Object(GUILD_ID))
@app_commands.describe(номер="Номер капта")
async def delete_capt(inter: discord.Interaction, номер: int):
    if not is_admin(inter.user):
        await inter.response.send_message("❌ Нет доступа", ephemeral=True)
        return
    
    await log_command_start(inter, "удалить_капт", {"номер": номер})
    
    capts = load_capts()
    if номер < 1 or номер > len(capts):
        await log_command_error(inter, "удалить_капт", f"Капт не найден: номер {номер}")
        await inter.response.send_message("❌ Капт не найден", ephemeral=True)
        return
    
    removed_capt = capts.pop(-номер)
    
    st = load_stats()
    total_points_removed = 0
    
    for player in removed_capt["players"]:
        uid = str(player["user_id"])
        if uid in st:
            st[uid]["damage"] -= player["damage"]
            st[uid]["kills"] -= player["kills"]
            st[uid]["games"] -= 1
            
            # Отнимаем баллы
            points_removed, _ = remove_points_from_player(
                player["user_id"], 
                player["damage"], 
                player["kills"]
            )
            total_points_removed += points_removed
            
            if st[uid]["games"] <= 0:
                del st[uid]
    
    save_stats(st)
    save_capts(capts)
    
    asyncio.create_task(update_avg_top())
    asyncio.create_task(update_kills_top())
    asyncio.create_task(update_capts_list())
    
    await log_command_success(inter, "удалить_капт", 
                            f"Удален капт #{номер} против {removed_capt['vs']}, снято {total_points_removed:.2f} баллов")
    
    await inter.response.send_message(
        f"✅ Капт против **{removed_capt['vs']}** удалён\n"
        f"📉 Снято баллов: **{total_points_removed:.2f}**",
        ephemeral=True
    )

@tree.command(name="сбросить_статистику", description="🔄 Сбросить всю статистику", guild=discord.Object(GUILD_ID))
async def reset_stats(inter: discord.Interaction):
    if not is_admin(inter.user):
        await inter.response.send_message("❌ Нет доступа", ephemeral=True)
        return
    
    await log_command_start(inter, "сбросить_статистику", {})
    
    capts = load_capts()
    stats_count = len(load_stats())
    points_count = len(load_points())
    
    save_stats({})
    save_capts([])
    save_points({})
    
    asyncio.create_task(update_avg_top())
    asyncio.create_task(update_kills_top())
    asyncio.create_task(update_capts_list())
    
    await log_command_success(inter, "сбросить_статистику", 
                            f"Удалено {len(capts)} каптов, {stats_count} записей статистики, {points_count} записей баллов")
    
    await inter.response.send_message(
        f"✅ Статистика сброшена\n"
        f"Удалено каптов: **{len(capts)}**\n"
        f"Удалено записей: **{stats_count}**\n"
        f"Удалено баллов: **{points_count}**",
        ephemeral=True
    )

@tree.command(name="список_каптов", description="📜 История каптов", guild=discord.Object(GUILD_ID))
@app_commands.describe(period="Период")
@app_commands.choices(period=[
    app_commands.Choice(name="За всё время", value="all"),
    app_commands.Choice(name="За неделю", value="week"),
    app_commands.Choice(name="За месяц", value="month")
])
async def list_capts(inter: discord.Interaction, period: str = "all"):
    if not is_viewer(inter.user):
        await inter.response.send_message("❌ Нет доступа", ephemeral=True)
        return
    
    await log_command_start(inter, "список_каптов", {"period": period})
    
    await inter.response.defer(ephemeral=True)
    
    try:
        view = CaptsListView(inter.guild, period)
        embed = await view.create_embed()
        
        await inter.followup.send(embed=embed, view=view, ephemeral=True)
        await log_command_success(inter, "список_каптов", f"Показан список каптов за период: {period}")
            
    except Exception as e:
        await log_command_error(inter, "список_каптов", str(e))
        print(f"❌ Ошибка в list_capts: {e}")
        await inter.followup.send("❌ Произошла ошибка при выполнении команды", ephemeral=True)

@tree.command(name="профиль", description="📊 Профиль игрока", guild=discord.Object(GUILD_ID))
@app_commands.describe(игрок="Игрок")
async def profile(inter: discord.Interaction, игрок: discord.Member = None):
    if not is_viewer(inter.user):
        await inter.response.send_message("❌ Нет доступа", ephemeral=True)
        return
    
    await log_command_start(inter, "профиль", {"игрок": f"{игрок.mention if игрок else inter.user.mention}"})
    
    target = игрок or inter.user
    
    # Получаем общую статистику
    st = load_stats()
    data = st.get(str(target.id))
    
    if not data or data["games"] == 0:
        await log_command_error(inter, "профиль", f"У {target.mention} нет статистики")
        await inter.response.send_message(f"📭 У {target.mention} нет статистики", ephemeral=True)
        return
    
    # Получаем капты игрока
    player_capts = get_player_capts(target.id)
    
    # Рассчитываем винрейт
    wins = 0
    total_games = len(player_capts)
    for pc in player_capts:
        if pc["capt"]["win"]:
            wins += 1
    
    winrate = (wins / total_games * 100) if total_games > 0 else 0
    
    # Последние 5 каптов
    recent_capts = player_capts[:5]
    
    # Последняя активность
    last_activity = "Неизвестно"
    if player_capts:
        last_capt = player_capts[0]
        try:
            dt = datetime.fromisoformat(last_capt["capt"]["date"])
            last_activity = dt.strftime("%d.%m.%Y %H:%M")
        except:
            pass
    
    # Баллы
    total_points = get_player_points(target.id)
    
    # Средний урон и киллы
    avg_dmg = data["damage"] // data["games"]
    avg_kills = data["kills"] / data["games"]
    
    # Автоматически рассчитанные баллы по формуле
    auto_points = calculate_points_from_stats(data["damage"], data["kills"])
    
    # Создаем embed
    embed = discord.Embed(
        title=f"📊 Профиль {target.mention}",
        description=f"*Статистика игрока*",
        color=0x3498db,
        timestamp=now_msk()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    
    # Основная статистика
    embed.add_field(
        name="📈 Основная статистика",
        value=f"```Игр:          {data['games']}\n"
              f"Винрейт:      {winrate:.1f}%\n"
              f"Побед:        {wins}\n"
              f"Всего урона:  {data['damage']:,}\n"
              f"Всего киллов: {data['kills']}\n"
              f"Ср.урон:      {avg_dmg:,}\n"
              f"Ср.киллы:     {avg_kills:.1f}```",
        inline=False
    )
    
    # Баллы
    embed.add_field(
        name="⭐ Баллы",
        value=f"**{total_points:.2f}**\n"
              f"*Формула: 1 килл = 0.5 балла\n1 урон = 0.001 балла*\n"
              f"Авторасчет: {auto_points:.2f}",
        inline=False
    )
    
    # Последние 5 каптов
    if recent_capts:
        capts_text = ""
        for pc in recent_capts:
            result = "✅" if pc["capt"]["win"] else "❌"
            try:
                date_str = datetime.fromisoformat(pc["capt"]["date"]).strftime("%d.%m")
            except:
                date_str = "??.??"
            
            capt_points = calculate_points_from_stats(pc["player_data"]["damage"], pc["player_data"]["kills"])
            capts_text += f"**#{pc['index']}** vs {pc['capt']['vs'][:15]} {result} - {date_str}\n"
            capts_text += f"💥 {pc['player_data']['damage']:,} | ☠️ {pc['player_data']['kills']} | ⭐ {capt_points:.2f}\n"
        
        embed.add_field(
            name="📅 Последние 5 каптов",
            value=capts_text,
            inline=False
        )
    
    # Последняя активность
    embed.add_field(
        name="🕐 Последняя активность",
        value=last_activity,
        inline=True
    )
    
    embed.set_footer(text=f"ID: {target.id}")
    
    await inter.response.send_message(embed=embed, ephemeral=True)
    await log_command_success(inter, "профиль", f"Показан профиль {target.mention}")

@tree.command(name="капт", description="📋 Детали капта", guild=discord.Object(GUILD_ID))
@app_commands.describe(номер="Номер капта (1 = последний)")
async def capt_details(inter: discord.Interaction, номер: int = 1):
    if not is_viewer(inter.user):
        await inter.response.send_message("❌ Нет доступа", ephemeral=True)
        return
    
    await log_command_start(inter, "капт", {"номер": номер})
    
    await inter.response.defer(ephemeral=True)
    
    try:
        capts = load_capts()
        if not capts or номер < 1 or номер > len(capts):
            await log_command_error(inter, "капт", f"Капт не найден: номер {номер}")
            await inter.followup.send("❌ Капт не найден", ephemeral=True)
            return

        capt = capts[-номер]
        
        try:
            date = datetime.fromisoformat(capt["date"]).strftime("%d.%m.%Y %H:%M")
        except:
            date = "Дата неизвестна"

        embed = discord.Embed(
            title=f"⚔️ YAK vs {capt['vs']}",
            description=f"📅 {date}\n{'✅ Победа' if capt['win'] else '❌ Поражение'}",
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
        
        # Рассчитываем баллы за капт
        total_points = calculate_points_from_stats(total_dmg, total_kills)

        embed.add_field(
            name="📊 Статистика",
            value=f"👥 {cnt} игроков\n💥 {total_dmg:,} урона\n☠️ {total_kills} киллов\n📈 {avg_dmg:,} ср. урона\n📊 {avg_kills:.1f} ср. киллов\n⭐ {total_points:.2f} баллов",
            inline=False
        )

        await inter.followup.send(embed=embed, ephemeral=True)
        await log_command_success(inter, "капт", f"Показан капт #{номер} против {capt['vs']}")
            
    except Exception as e:
        await log_command_error(inter, "капт", str(e))
        print(f"❌ Ошибка в capt_details: {e}")
        await inter.followup.send("❌ Произошла ошибка при выполнении команды", ephemeral=True)

@tree.command(name="топ_средний", description="🏆 Топ по среднему урону", guild=discord.Object(GUILD_ID))
@app_commands.describe(period="Период")
@app_commands.choices(period=[
    app_commands.Choice(name="За всё время", value="all"),
    app_commands.Choice(name="За неделю", value="week"),
    app_commands.Choice(name="За месяц", value="month")
])
async def top_avg(inter: discord.Interaction, period: str = "all"):
    if not is_viewer(inter.user):
        await inter.response.send_message("❌ Нет доступа", ephemeral=True)
        return
    
    await log_command_start(inter, "топ_средний", {"period": period})
    
    await inter.response.defer(ephemeral=True)
    
    try:
        if period == "week":
            capts = get_capts_in_period(7)
            period_text = "за неделю"
        elif period == "month":
            capts = get_capts_in_period(30)
            period_text = "за месяц"
        else:
            capts = load_capts()
            period_text = "за всё время"
        
        st = calculate_stats(capts)
        filtered = {uid: d for uid, d in st.items() if d["games"] >= 3}
        
        if not filtered:
            await log_command_error(inter, "топ_средний", "Нет игроков с 3+ играми")
            await inter.followup.send("📭 Нет игроков с 3+ играми", ephemeral=True)
            return

        users = sorted(filtered.items(), key=lambda x: x[1]["damage"]/x[1]["games"], reverse=True)[:10]
        
        embed = discord.Embed(
            title=f"🏆 ТОП-10 СРЕДНЕГО УРОНА",
            description=f"*Статистика {period_text}*",
            color=0x9b59b6,
            timestamp=now_msk()
        )
        
        desc = ""
        for i, (uid, data) in enumerate(users, 1):
            try:
                member = await inter.guild.fetch_member(int(uid))
                name = f"{member.mention} ({member.display_name})"
            except:
                name = f"Игрок {uid}"
            
            avg = data["damage"] // data["games"]
            
            if i <= 3:
                desc += f"{medal(i)} **{name}**\n"
            else:
                desc += f"`{i}.` **{name}**\n"
            
            desc += f"```Средний урон: {avg:,}\nИгр:         {data['games']}\nВсего урона: {data['damage']:,}```\n"
        
        embed.description = f"*Статистика {period_text}*\n\n" + desc
        embed.set_footer(text="Минимум 3 игры для участия")
        
        await inter.followup.send(embed=embed, ephemeral=True)
        await log_command_success(inter, "топ_средний", f"Показан топ среднего урона за период: {period}")
            
    except Exception as e:
        await log_command_error(inter, "топ_средний", str(e))
        print(f"❌ Ошибка в top_avg: {e}")
        await inter.followup.send("❌ Произошла ошибка при выполнении команды", ephemeral=True)

def calculate_stats(capts_list: list) -> dict:
    """Рассчитать статистику из списка каптов"""
    stats = {}
    for capt in capts_list:
        for player in capt["players"]:
            uid = str(player["user_id"])
            if uid not in stats:
                stats[uid] = {"damage": 0, "kills": 0, "games": 0}
            stats[uid]["damage"] += player["damage"]
            stats[uid]["kills"] += player["kills"]
            stats[uid]["games"] += 1
    return stats

@tree.command(name="топ_киллы", description="☠️ Топ по киллам", guild=discord.Object(GUILD_ID))
@app_commands.describe(period="Период")
@app_commands.choices(period=[
    app_commands.Choice(name="За всё время", value="all"),
    app_commands.Choice(name="За неделю", value="week"),
    app_commands.Choice(name="За месяц", value="month")
])
async def top_kills(inter: discord.Interaction, period: str = "all"):
    if not is_viewer(inter.user):
        await inter.response.send_message("❌ Нет доступа", ephemeral=True)
        return
    
    await log_command_start(inter, "топ_киллы", {"period": period})
    
    await inter.response.defer(ephemeral=True)
    
    try:
        if period == "week":
            capts = get_capts_in_period(7)
            period_text = "за неделю"
        elif period == "month":
            capts = get_capts_in_period(30)
            period_text = "за месяц"
        else:
            capts = load_capts()
            period_text = "за всё время"
        
        st = calculate_stats(capts)
        
        if not st:
            await log_command_error(inter, "топ_киллы", "Статистика пуста")
            await inter.followup.send("📭 Статистика пуста", ephemeral=True)
            return

        users = sorted(st.items(), key=lambda x: x[1]["kills"], reverse=True)[:10]

        embed = discord.Embed(
            title=f"☠️ ТОП-10 ПО КИЛЛАМ",
            description=f"*Статистика {period_text}*",
            color=0xe74c3c,
            timestamp=now_msk()
        )
        
        desc = ""
        for i, (uid, data) in enumerate(users, 1):
            try:
                member = await inter.guild.fetch_member(int(uid))
                name = f"{member.mention} ({member.display_name})"
            except:
                name = f"Игрок {uid}"
            
            if i <= 3:
                desc += f"{medal(i)} **{name}**\n"
            else:
                desc += f"`{i}.` **{name}**\n"
            
            desc += f"```Киллов:      {data['kills']}\nИгр:         {data['games']}\nСредний урон: {data['damage']//data['games']:,}```\n"
        
        embed.description = f"*Статистика {period_text}*\n\n" + desc
        
        await inter.followup.send(embed=embed, ephemeral=True)
        await log_command_success(inter, "топ_киллы", f"Показан топ киллов за период: {period}")
            
    except Exception as e:
        await log_command_error(inter, "топ_киллы", str(e))
        print(f"❌ Ошибка в top_kills: {e}")
        await inter.followup.send("❌ Произошла ошибка при выполнении команды", ephemeral=True)

@tree.command(name="топ_баллы", description="⭐ Топ по баллам", guild=discord.Object(GUILD_ID))
@app_commands.describe(period="Период")
@app_commands.choices(period=[
    app_commands.Choice(name="За всё время", value="all"),
    app_commands.Choice(name="За неделю", value="week"),
    app_commands.Choice(name="За месяц", value="month")
])
async def top_points(inter: discord.Interaction, period: str = "all"):
    if not is_viewer(inter.user):
        await inter.response.send_message("❌ Нет доступа", ephemeral=True)
        return
    
    await log_command_start(inter, "топ_баллы", {"period": period})
    
    await inter.response.defer(ephemeral=True)
    
    try:
        if period == "week":
            capts = get_capts_in_period(7)
            period_text = "за неделю"
        elif period == "month":
            capts = get_capts_in_period(30)
            period_text = "за месяц"
        else:
            # Для "все время" используем общие баллы из базы
            points_db = load_points()
            
            if not points_db:
                await log_command_error(inter, "топ_баллы", "Нет данных по баллам")
                await inter.followup.send("📭 Нет данных по баллам", ephemeral=True)
                return
            
            # Сортируем по баллам
            sorted_points = sorted(points_db.items(), key=lambda x: x[1], reverse=True)[:10]
            
            embed = discord.Embed(
                title=f"⭐ ТОП-10 ПО БАЛЛАМ",
                description=f"*За всё время*\n*1 килл = 0.5 балла, 1 урон = 0.001 балла*",
                color=0xf1c40f,
                timestamp=now_msk()
            )
            
            desc = ""
            for i, (uid, points) in enumerate(sorted_points, 1):
                try:
                    member = await inter.guild.fetch_member(int(uid))
                    name = f"{member.mention} ({member.display_name})"
                except:
                    name = f"Игрок {uid}"
                
                if i <= 3:
                    desc += f"{medal(i)} **{name}**\n"
                else:
                    desc += f"`{i}.` **{name}**\n"
                
                desc += f"```Баллы:      {points:.2f}```\n"
            
            embed.description = desc
            await inter.followup.send(embed=embed, ephemeral=True)
            await log_command_success(inter, "топ_баллы", f"Показан топ баллов за период: {period}")
            return
        
        # Для недели и месяца считаем баллы из каптов
        player_stats = {}
        for capt in capts:
            for player in capt["players"]:
                uid = str(player["user_id"])
                if uid not in player_stats:
                    player_stats[uid] = {
                        "damage": 0,
                        "kills": 0,
                        "games": 0
                    }
                player_stats[uid]["damage"] += player["damage"]
                player_stats[uid]["kills"] += player["kills"]
                player_stats[uid]["games"] += 1
        
        # Рассчитываем баллы для каждого игрока
        player_points = []
        for uid, stats in player_stats.items():
            points = calculate_points_from_stats(stats["damage"], stats["kills"])
            player_points.append((uid, points, stats))
        
        # Сортируем по баллам
        player_points.sort(key=lambda x: x[1], reverse=True)
        
        if not player_points:
            await log_command_error(inter, "топ_баллы", f"Нет статистики {period_text}")
            await inter.followup.send(f"📭 Нет статистики {period_text}", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"⭐ ТОП-10 ПО БАЛЛАМ",
            description=f"*Статистика {period_text}*\n*1 килл = 0.5 балла, 1 урон = 0.001 балла*",
            color=0xf1c40f,
            timestamp=now_msk()
        )
        
        desc = ""
        for i, (uid, points, stats) in enumerate(player_points[:10], 1):
            try:
                member = await inter.guild.fetch_member(int(uid))
                name = f"{member.mention} ({member.display_name})"
            except:
                name = f"Игрок {uid}"
            
            if i <= 3:
                desc += f"{medal(i)} **{name}**\n"
            else:
                desc += f"`{i}.` **{name}**\n"
            
            desc += f"```Баллы:      {points:.2f}\nУрон:       {stats['damage']:,}\nКиллы:      {stats['kills']}\nИгр:        {stats['games']}```\n"
        
        embed.description = desc
        
        await inter.followup.send(embed=embed, ephemeral=True)
        await log_command_success(inter, "топ_баллы", f"Показан топ баллов за период: {period}")
            
    except Exception as e:
        await log_command_error(inter, "топ_баллы", str(e))
        print(f"❌ Ошибка в top_points: {e}")
        await inter.followup.send("❌ Произошла ошибка при выполнении команды", ephemeral=True)

@tree.command(name="моя_статистика", description="📊 Ваша статистика", guild=discord.Object(GUILD_ID))
@app_commands.describe(period="Период")
@app_commands.choices(period=[
    app_commands.Choice(name="За всё время", value="all"),
    app_commands.Choice(name="За неделю", value="week"),
    app_commands.Choice(name="За месяц", value="month")
])
async def my_stats(inter: discord.Interaction, period: str = "all"):
    if not is_viewer(inter.user):
        await inter.response.send_message("❌ Нет доступа", ephemeral=True)
        return
    
    await log_command_start(inter, "моя_статистика", {"period": period})
    
    await inter.response.defer(ephemeral=True)
    
    try:
        if period == "week":
            capts = get_capts_in_period(7)
            period_text = "за неделю"
        elif period == "month":
            capts = get_capts_in_period(30)
            period_text = "за месяц"
        else:
            capts = load_capts()
            period_text = "за всё время"
        
        st = calculate_stats(capts)
        uid = str(inter.user.id)
        
        if uid not in st:
            await log_command_error(inter, "моя_статистика", f"Нет статистики {period_text}")
            await inter.followup.send(f"📭 Нет статистики {period_text}", ephemeral=True)
            return
        
        data = st[uid]
        avg = data["damage"] // data["games"] if data["games"] > 0 else 0
        
        # Рассчитываем винрейт для периода
        player_capts = []
        for capt in capts:
            for player in capt["players"]:
                if player["user_id"] == inter.user.id:
                    player_capts.append(capt)
                    break
        
        wins = sum(1 for capt in player_capts if capt["win"])
        winrate = (wins / len(player_capts) * 100) if player_capts else 0
        
        # Баллы за период
        period_points = calculate_points_from_stats(data["damage"], data["kills"])
        total_points = get_player_points(inter.user.id)
        
        embed = discord.Embed(
            title=f"📊 Статистика {inter.user.mention}",
            description=f"*{period_text.capitalize()}*",
            color=0x3498db,
            timestamp=now_msk()
        )
        embed.set_thumbnail(url=inter.user.display_avatar.url)
        
        embed.add_field(
            name="📈 Основная статистика",
            value=f"```Игр:         {data['games']}\n"
                  f"Винрейт:     {winrate:.1f}%\n"
                  f"Средний урон: {avg:,}\n"
                  f"Всего урона:  {data['damage']:,}\n"
                  f"Всего киллов: {data['kills']}\n"
                  f"Баллы за период: {period_points:.2f}\n"
                  f"Общие баллы:    {total_points:.2f}```",
            inline=False
        )
        
        # Позиции в рейтингах
        avg_users = sorted(st.items(), key=lambda x: x[1]["damage"]/x[1]["games"] if x[1]["games"] >= 3 else 0, reverse=True)
        kills_users = sorted(st.items(), key=lambda x: x[1]["kills"], reverse=True)
        
        avg_pos = next((i+1 for i, (u, _) in enumerate(avg_users) if u == uid and data["games"] >= 3), None)
        kills_pos = next((i+1 for i, (u, _) in enumerate(kills_users) if u == uid), None)
        
        positions = ""
        if avg_pos:
            positions += f"🏅 Место по среднему: **#{avg_pos}**\n"
        if kills_pos:
            positions += f"☠️ Место по киллам: **#{kills_pos}**\n"
        
        if positions:
            embed.add_field(name="🎯 Позиции в рейтинге", value=positions, inline=False)
        
        # Последние капты
        if player_capts:
            recent_text = ""
            for i, capt in enumerate(player_capts[:3], 1):
                result = "✅" if capt["win"] else "❌"
                try:
                    date_str = datetime.fromisoformat(capt["date"]).strftime("%d.%m")
                except:
                    date_str = "??.??"
                
                recent_text += f"vs {capt['vs'][:15]} {result} - {date_str}\n"
            
            if recent_text:
                embed.add_field(name="📅 Последние капты", value=recent_text, inline=False)
        
        await inter.followup.send(embed=embed, ephemeral=True)
        await log_command_success(inter, "моя_статистика", f"Показана статистика за период: {period}")
            
    except Exception as e:
        await log_command_error(inter, "моя_статистика", str(e))
        print(f"❌ Ошибка в my_stats: {e}")
        await inter.followup.send("❌ Произошла ошибка при выполнении команды", ephemeral=True)

@tree.command(name="справка", description="📚 Помощь по командам", guild=discord.Object(GUILD_ID))
async def help_cmd(inter: discord.Interaction):
    if not is_viewer(inter.user):
        await inter.response.send_message("❌ Нет доступа", ephemeral=True)
        return
    
    await log_command_start(inter, "справка", {})
    
    is_admin_user = is_admin(inter.user)
    
    embed = discord.Embed(
        title="📚 СПРАВКА ПО КОМАНДАМ",
        description="*Статистика Семьи YAK*",
        color=0xe74c3c,
        timestamp=now_msk()
    )
    
    embed.add_field(
        name="👥 Для всех",
        value=(
            "`/профиль` - Профиль игрока\n"
            "`/капт` - Детали капта\n"
            "`/список_каптов` - История каптов\n"
            "`/топ_средний` - Топ по урону\n"
            "`/топ_киллы` - Топ по киллам\n"
            "`/топ_баллы` - Топ по баллам\n"
            "`/моя_статистика` - Ваша стата\n"
            "`/справка` - Эта справка"
        ),
        inline=False
    )
    
    if is_admin_user:
        embed.add_field(
            name="👑 Для админов",
            value=(
                "`/добавить_капт` - Создать капт\n"
                "`/добавить_игрока` - Добавить игрока\n"
                "`/загрузить_игроков` - Массовое добавление\n"
                "`/загрузить_капты` - Загрузить из файла\n"
                "`/удалить_капт` - Удалить капт\n"
                "`/сбросить_статистику` - Сброс всего\n"
                "`/обновить` - Обновить все топы\n"
                "`/sync` - Синхронизация команд"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📝 Форматы загрузки",
            value=(
                "**Текст (игроки):**\n"
                "```ID урон киллы```\n"
                "**Файл (капты):**\n"
                "```ID урон киллы win\n\nID урон киллы lose```"
            ),
            inline=False
        )
    
    embed.set_footer(text="YAK Clan Stats Bot v7.2 • Все команды видны только вам")
    
    await inter.response.send_message(embed=embed, ephemeral=True)
    await log_command_success(inter, "справка", "Показана справка")

@tree.command(name="обновить", description="🔄 Принудительно обновить топы и список каптов", guild=discord.Object(GUILD_ID))
async def manual_update(inter: discord.Interaction):
    if not is_admin(inter.user):
        await inter.response.send_message("❌ Нет доступа", ephemeral=True)
        return
    
    await log_command_start(inter, "обновить", {})
    
    await inter.response.defer(ephemeral=True)
    
    try:
        await log_system_event("🔄 Ручное обновление топов", f"Инициировано пользователем {inter.user.mention}")
        
        await update_avg_top()
        await update_kills_top()
        await update_capts_list()
        
        # Также обновляем админ-меню
        asyncio.create_task(update_admin_menu())
        
        await log_command_success(inter, "обновить", "Все топы обновлены")
        await log_system_event("✅ Ручное обновление завершено", "Все топы успешно обновлены")
        await inter.followup.send("✅ Все топы успешно обновлены!", ephemeral=True)
        
    except Exception as e:
        await log_command_error(inter, "обновить", str(e))
        await log_system_event("❌ Ошибка ручного обновления", f"Ошибка: {str(e)}")
        await inter.followup.send(f"❌ Ошибка при обновлении: {str(e)}", ephemeral=True)

@tree.command(name="sync", description="🔄 Синхронизировать команды", guild=discord.Object(GUILD_ID))
async def sync_commands(inter: discord.Interaction):
    if not is_admin(inter.user):
        await inter.response.send_message("❌ Нет доступа", ephemeral=True)
        return
    
    await log_command_start(inter, "sync", {})
    
    await inter.response.defer(ephemeral=True)
    
    try:
        synced = await tree.sync(guild=discord.Object(GUILD_ID))
        
        await log_system_event("🔄 Синхронизация команд", f"Синхронизировано команд: {len(synced)}")
        
        embed = discord.Embed(
            title="✅ Команды синхронизированы",
            description=f"Синхронизировано команд: **{len(synced)}**",
            color=0x2ecc71,
            timestamp=now_msk()
        )
        
        commands_list = "\n".join([f"• `/{cmd.name}`" for cmd in synced])
        embed.add_field(
            name="📋 Синхронизированные команды",
            value=commands_list,
            inline=False
        )
        
        embed.set_footer(text="Команды обновлены")
        
        await inter.followup.send(embed=embed, ephemeral=True)
        await log_command_success(inter, "sync", f"Синхронизировано {len(synced)} команд")
        
    except Exception as e:
        embed = discord.Embed(
            title="❌ Ошибка синхронизации",
            description=f"```{str(e)}```",
            color=0xe74c3c,
            timestamp=now_msk()
        )
        await log_system_event("❌ Ошибка синхронизации", f"Ошибка: {str(e)}")
        await inter.followup.send(embed=embed, ephemeral=True)
        await log_command_error(inter, "sync", str(e))

# ==================== АВТООБНОВЛЕНИЕ ====================
async def update_avg_top():
    """Обновление топа по среднему урону"""
    channel = client.get_channel(STATS_AVG_CHANNEL_ID)
    if not channel:
        await log_system_event("❌ Канал не найден", f"Канал STATS_AVG_CHANNEL_ID ({STATS_AVG_CHANNEL_ID}) не найден")
        return

    try:
        st = load_stats()
        
        filtered = {uid: d for uid, d in st.items() if d["games"] >= 3}
        
        if not filtered:
            embed = discord.Embed(
                title="🏆 ТОП-10 СРЕДНЕГО УРОНА",
                description="📭 Нет игроков с 3+ играми",
                color=0x9b59b6,
                timestamp=now_msk()
            )
            embed.set_footer(text="Минимум 3 игры для участия")
            
            async for msg in channel.history(limit=50):
                if msg.author.id == client.user.id and msg.embeds:
                    if "ТОП-10 СРЕДНЕГО УРОНА" in msg.embeds[0].title:
                        try:
                            await msg.edit(embed=embed)
                            await log_system_event("✅ Топ урона обновлен", "Нет игроков с 3+ играми")
                            return
                        except Exception as e:
                            await log_system_event("❌ Ошибка редактирования топа урона", f"Ошибка: {str(e)}")
            
            try:
                await channel.send(embed=embed)
                await log_system_event("✅ Топ урона отправлен", "Нет игроков с 3+ играми")
            except Exception as e:
                await log_system_event("❌ Ошибка отправки топа урона", f"Ошибка: {str(e)}")
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
            bar = progress_bar(percent)

            desc += f"{medal(i)} **{i}. {name}**\n{bar} **{avg:,}** урона ({data['games']} игр)\n\n"

        embed.description = desc
        embed.set_footer(text="Обновляется каждый час • Минимум 3 игры")

        found = False
        async for msg in channel.history(limit=50):
            if msg.author.id == client.user.id and msg.embeds:
                if "ТОП-10 СРЕДНЕГО УРОНА" in msg.embeds[0].title:
                    try:
                        await msg.edit(embed=embed)
                        await log_system_event("✅ Топ урона обновлен", f"Обновлено {len(users)} игроков")
                        found = True
                        break
                    except Exception as e:
                        await log_system_event("❌ Ошибка редактирования топа урона", f"Ошибка: {str(e)}")
                        found = False
        
        if not found:
            try:
                await channel.send(embed=embed)
                await log_system_event("✅ Топ урона отправлен", f"Отправлено {len(users)} игроков")
            except Exception as e:
                await log_system_event("❌ Ошибка отправки топа урона", f"Ошибка: {str(e)}")
                
    except Exception as e:
        await log_system_event("❌ Критическая ошибка в update_avg_top", f"Ошибка: {str(e)}")

async def update_kills_top():
    """Обновление топа по киллам"""
    channel = client.get_channel(STATS_KILLS_CHANNEL_ID)
    if not channel:
        await log_system_event("❌ Канал не найден", f"Канал STATS_KILLS_CHANNEL_ID ({STATS_KILLS_CHANNEL_ID}) не найден")
        return

    try:
        st = load_stats()
        
        if not st:
            embed = discord.Embed(
                title="☠️ ТОП-10 ПО КИЛЛАМ",
                description="📭 Статистика пуста",
                color=0xe74c3c,
                timestamp=now_msk()
            )
            embed.set_footer(text="Обновляется каждый час")
            
            async for msg in channel.history(limit=50):
                if msg.author.id == client.user.id and msg.embeds:
                    if "ТОП-10 ПО КИЛЛАМ" in msg.embeds[0].title:
                        try:
                            await msg.edit(embed=embed)
                            await log_system_event("✅ Топ киллов обновлен", "Статистика пуста")
                            return
                        except Exception as e:
                            await log_system_event("❌ Ошибка редактирования топа киллов", f"Ошибка: {str(e)}")
            
            try:
                await channel.send(embed=embed)
                await log_system_event("✅ Топ киллов отправлен", "Статистика пуста")
            except Exception as e:
                await log_system_event("❌ Ошибка отправки топа киллов", f"Ошибка: {str(e)}")
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
            bar = progress_bar(percent)

            desc += f"{medal(i)} **{i}. {name}**\n{bar} **{data['kills']}** киллов ({data['games']} игр)\n\n"

        embed.description = desc
        embed.set_footer(text="Обновляется каждый час")

        found = False
        async for msg in channel.history(limit=50):
            if msg.author.id == client.user.id and msg.embeds:
                if "ТОП-10 ПО КИЛЛАМ" in msg.embeds[0].title:
                    try:
                        await msg.edit(embed=embed)
                        await log_system_event("✅ Топ киллов обновлен", f"Обновлено {len(users)} игроков")
                        found = True
                        break
                    except Exception as e:
                        await log_system_event("❌ Ошибка редактирования топа киллов", f"Ошибка: {str(e)}")
                        found = False
        
        if not found:
            try:
                await channel.send(embed=embed)
                await log_system_event("✅ Топ киллов отправлен", f"Отправлено {len(users)} игроков")
            except Exception as e:
                await log_system_event("❌ Ошибка отправки топа киллов", f"Ошибка: {str(e)}")
                
    except Exception as e:
        await log_system_event("❌ Критическая ошибка в update_kills_top", f"Ошибка: {str(e)}")

async def update_capts_list():
    """Обновление списка каптов"""
    channel = client.get_channel(CAPTS_LIST_CHANNEL_ID)
    if not channel:
        await log_system_event("❌ Канал не найден", f"Канал CAPTS_LIST_CHANNEL_ID ({CAPTS_LIST_CHANNEL_ID}) не найден")
        return

    try:
        view = CaptsListView(channel.guild, "all")
        embed = await view.create_embed()

        found = False
        async for msg in channel.history(limit=50):
            if msg.author.id == client.user.id and msg.embeds:
                if "История каптов" in msg.embeds[0].title:
                    try:
                        await msg.edit(embed=embed, view=view)
                        await log_system_event("✅ Список каптов обновлен", f"Загружено {len(view.capts)} каптов")
                        found = True
                        break
                    except Exception as e:
                        await log_system_event("❌ Ошибка редактирования списка каптов", f"Ошибка: {str(e)}")
                        found = False
        
        if not found:
            try:
                await channel.send(embed=embed, view=view)
                await log_system_event("✅ Список каптов отправлен", f"Загружено {len(view.capts)} каптов")
            except Exception as e:
                await log_system_event("❌ Ошибка отправки списка каптов", f"Ошибка: {str(e)}")
                
    except Exception as e:
        await log_system_event("❌ Критическая ошибка в update_capts_list", f"Ошибка: {str(e)}")

async def update_admin_menu():
    """Обновление админ-меню"""
    channel = client.get_channel(ADMIN_MENU_CHANNEL_ID)
    if not channel:
        return
    
    try:
        embed = discord.Embed(
            title="👑 АДМИН ПАНЕЛЬ УПРАВЛЕНИЯ",
            description="*Используйте кнопки ниже для управления статистикой*\n\n"
                       "**Формат ввода:**\n"
                       "• **Редактировать игрока:** ID, номер капта, киллы, урон, удалить (1/0)\n"
                       "• **Баллы:** ID, изменение (+/-)\n"
                       "• **Редактировать капт:** номер, название (не обязательно), win/lose (не обязательно)",
            color=0xe74c3c,
            timestamp=now_msk()
        )
        
        # Статистика
        stats = load_stats()
        capts = load_capts()
        points_db = load_points()
        
        total_points = sum(points_db.values())
        
        embed.add_field(
            name="📊 Статистика",
            value=f"Всего каптов: **{len(capts)}**\n"
                  f"Игроков в базе: **{len(stats)}**\n"
                  f"Всего баллов: **{total_points:.2f}**\n"
                  f"Последнее обновление: {now_msk().strftime('%d.%m.%Y %H:%M')}",
            inline=False
        )
        
        # Информация о баллах
        embed.add_field(
            name="⭐ Система баллов",
            value="**Формула:**\n"
                  "1 килл = 0.5 балла\n"
                  "1 урон = 0.001 балла\n\n"
                  "**В недельном отчете:**\n"
                  "• Показываются баллы за неделю\n"
                  "• У топ-10 снимается 10% баллов",
            inline=False
        )
        
        view = AdminMenuView()
        
        # Ищем существующее сообщение
        async for msg in channel.history(limit=50):
            if msg.author.id == client.user.id and msg.embeds:
                if "АДМИН ПАНЕЛЬ УПРАВЛЕНИЯ" in msg.embeds[0].title:
                    try:
                        await msg.edit(embed=embed, view=view)
                        return
                    except:
                        pass
        
        # Если не нашли, отправляем новое
        await channel.send(embed=embed, view=view)
        
    except Exception as e:
        await log_system_event("❌ Ошибка обновления админ-меню", f"Ошибка: {str(e)}")

@tasks.loop(hours=1)
async def auto_update():
    """Автоматическое обновление топов каждый час"""
    await log_system_event("⏰ Начало автообновления", "Запущено автоматическое обновление топов")
    await update_avg_top()
    await update_kills_top()
    await update_capts_list()
    await log_system_event("✅ Автообновление завершено", "Все топы успешно обновлены")

# ==================== СОБЫТИЯ ====================
@client.event
async def on_ready():
    print(f"✅ Бот запущен: {client.user}")
    
    try:
        synced = await tree.sync(guild=discord.Object(GUILD_ID))
        print(f"✅ Команды синхронизированы: {len(synced)} команд") 
        
        await log_system_event("✅ Бот запущен", f"Бот успешно запущен. Синхронизировано {len(synced)} команд")
        
        for cmd in synced:
            print(f"  • /{cmd.name}")
    except Exception as e:
        print(f"❌ Ошибка синхронизации: {e}")
        await log_system_event("❌ Ошибка синхронизации", f"Ошибка: {str(e)}")
    
    if not auto_update.is_running():
        auto_update.start()
        print("✅ Автообновление запущено")
        await log_system_event("✅ Автообновление запущено", "Топы будут обновляться каждый час")
    
    if not weekly_report_task.is_running():
        weekly_report_task.start()
        print("✅ Недельный отчет активирован")
        await log_system_event("✅ Недельный отчет активирован", "Отчеты будут отправляться каждую неделю")
    
    # Обновляем все списки при запуске
    try:
        await log_system_event("🔄 Обновление при запуске", "Начато принудительное обновление топов при запуске")
        await update_capts_list()
        await update_avg_top()
        await update_kills_top()
        
        # Создаем админ-меню
        await update_admin_menu()
        
        await log_system_event("✅ Обновление завершено", "Все топы обновлены при запуске")
        print("✅ Все списки обновлены при запуске")
    except Exception as e:
        print(f"⚠️ Ошибка при обновлении списков: {e}")
        await log_system_event("❌ Ошибка обновления", f"Ошибка при обновлении списков: {str(e)}")

@client.event
async def on_member_remove(member: discord.Member):
    st = load_stats()
    uid = str(member.id)
    
    if uid in st:
        del st[uid]
        save_stats(st)
        
        # Также удаляем баллы
        points_db = load_points()
        if uid in points_db:
            del points_db[uid]
            save_points(points_db)
        
        await log_system_event("👤 Игрок покинул сервер", 
                             f"Игрок {member.mention} ({member.display_name}) покинул сервер. Статистика и баллы удалены.")
        
        asyncio.create_task(update_avg_top())
        asyncio.create_task(update_kills_top())

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    # Создаем файлы базы данных, если они не существуют
    for db in [DB_STATS, DB_CAPTS, DB_POINTS]:
        if not os.path.exists(db):
            with open(db, "w", encoding="utf-8") as f:
                if db == DB_STATS:
                    json.dump({}, f)
                elif db == DB_CAPTS:
                    json.dump([], f)
                elif db == DB_POINTS:
                    json.dump({}, f)
            print(f"📁 Создан {db}")

    try:
        client.run(TOKEN)
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
