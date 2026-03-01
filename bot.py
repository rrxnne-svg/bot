# -------------- bot.py (исправленная версия 6.0) --------------
import discord, json, os, asyncio, re, traceback
from datetime import datetime, timedelta, timezone
from discord.ext import tasks
from discord import app_commands
from discord.ui import Button, View

# ==================== НАСТРОЙКИ ====================
TOKEN = os.getenv("TOKEN")
GUILD_ID = 1430087806952411230
ADMIN_ROLES = ["dep.YAK", "Owner", "Leader", "high.YAK"]
VIEW_ROLES = ["member", "Test", "Famlily", "Yak"]

# ID каналов
STATS_AVG_CHANNEL_ID = 1467543899643052312
STATS_KILLS_CHANNEL_ID = 1467543933209809076
CAPTS_LIST_CHANNEL_ID = 1467544000088117451
LOG_CHANNEL_ID = 1467598151269150822  # ID канала для логов

# Московское время (UTC+3)
MSK_TZ = timezone(timedelta(hours=3))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

DB_STATS = "stats.json"
DB_CAPTS = "capts.json"

# ==================== УТИЛИТЫ ====================
def now_msk():
    """Получить текущее время по Москве (UTC+3)"""
    return datetime.now(timezone.utc).astimezone(MSK_TZ)

def now():
    """Алиас для now_msk для совместимости"""
    return now_msk()

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
        await interaction.response.defer()
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_message(interaction)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.primary, custom_id="capts_page")
    async def page_info(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()

    @discord.ui.button(label="➡️", style=discord.ButtonStyle.secondary, custom_id="capts_next")
    async def next_page(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            await self.update_message(interaction)

    @discord.ui.button(label="🔄", style=discord.ButtonStyle.success, custom_id="capts_refresh")
    async def refresh(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
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

# ==================== VIEW ДЛЯ ДЕТАЛЕЙ КАПТА ====================
class CaptDetailsView(View):
    def __init__(self, capt_index: int, capt_data: dict, original_inter: discord.Interaction):
        super().__init__(timeout=180)
        self.capt_index = capt_index
        self.capt_data = capt_data
        self.original_inter = original_inter
        self.current_page = 0
        self.players_per_page = 10
        self.update_players()

    def update_players(self):
        self.players_sorted = sorted(self.capt_data["players"], key=lambda x: x["damage"], reverse=True)
        self.total_pages = max(1, (len(self.players_sorted) + self.players_per_page - 1) // self.players_per_page)

    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.secondary, row=0)
    async def prev_page(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_embed(interaction)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.primary, row=0, disabled=True)
    async def page_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()

    @discord.ui.button(label="➡️", style=discord.ButtonStyle.secondary, row=0)
    async def next_page(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            await self.update_embed(interaction)

    @discord.ui.button(label="🔄 Обновить", style=discord.ButtonStyle.success, row=1)
    async def refresh(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        capts = load_capts()
        if self.capt_index <= len(capts):
            self.capt_data = capts[-self.capt_index]
            self.update_players()
            await self.update_embed(interaction)

    async def update_embed(self, interaction: discord.Interaction):
        try:
            date = datetime.fromisoformat(self.capt_data["date"]).strftime("%d.%m.%Y %H:%M")
        except:
            date = "Дата неизвестна"

        embed = discord.Embed(
            title=f"⚔️ YAK vs {self.capt_data['vs']}",
            description=f"📅 {date}\n{'✅ Победа' if self.capt_data['win'] else '❌ Поражение'}",
            color=0x2ecc71 if self.capt_data["win"] else 0xe74c3c,
            timestamp=now_msk()
        )

        for child in self.children:
            if isinstance(child, Button) and child.label == "1/1":
                child.label = f"{self.current_page+1}/{self.total_pages}"
            elif isinstance(child, Button) and child.label == "⬅️":
                child.disabled = self.current_page == 0
            elif isinstance(child, Button) and child.label == "➡️":
                child.disabled = self.current_page >= self.total_pages - 1

        if not self.players_sorted:
            embed.add_field(name="👥 Участники", value="Нет данных", inline=False)
        else:
            start = self.current_page * self.players_per_page
            end = min(start + self.players_per_page, len(self.players_sorted))

            text = ""
            for i in range(start, end):
                p = self.players_sorted[i]
                try:
                    member = await interaction.guild.fetch_member(p["user_id"])
                    name = f"{member.mention} ({member.display_name})"
                except:
                    name = f"Игрок {p['user_id']}"
                text += f"**{i+1}.** {name} — {p['damage']:,} урона, {p['kills']} киллов\n"

            embed.add_field(name=f"👥 Участники — стр. {self.current_page+1}/{self.total_pages}", value=text, inline=False)
        
        total_dmg = sum(p["damage"] for p in self.capt_data["players"])
        total_kills = sum(p["kills"] for p in self.capt_data["players"])
        cnt = len(self.capt_data["players"])
        avg_dmg = total_dmg // cnt if cnt else 0
        avg_kills = total_kills / cnt if cnt else 0

        embed.add_field(
            name="📊 Статистика",
            value=f"👥 {cnt} игроков\n💥 {total_dmg:,} урона\n☠️ {total_kills} киллов\n📈 {avg_dmg:,} ср. урона\n📊 {avg_kills:.1f} ср. киллов",
            inline=False
        )

        try:
            await interaction.message.edit(embed=embed, view=self)
        except:
            pass

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
    
    save_stats(st)
    save_capts(capts)
    
    asyncio.create_task(update_avg_top())
    asyncio.create_task(update_kills_top())
    asyncio.create_task(update_capts_list())
    
    await log_command_success(inter, "добавить_игрока", f"Игрок {игрок.mention} добавлен в капт #{номер_капта}")
    
    await inter.response.send_message(
        f"✅ {игрок.mention} добавлен!\n"
        f"💥 Урон: **{урон:,}** │ ☠️ Киллы: **{киллы}**",
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
            save_stats(st)
            
            added += 1
        
        save_capts(capts)
        
        asyncio.create_task(update_avg_top())
        asyncio.create_task(update_kills_top())
        asyncio.create_task(update_capts_list())
        
        await log_command_success(inter, "загрузить_игроков", f"Добавлено {added} игроков, ошибок: {len(errors)}")
        
        msg = f"✅ Добавлено игроков: **{added}**"
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
    for player in removed_capt["players"]:
        uid = str(player["user_id"])
        if uid in st:
            st[uid]["damage"] -= player["damage"]
            st[uid]["kills"] -= player["kills"]
            st[uid]["games"] -= 1
            if st[uid]["games"] <= 0:
                del st[uid]
    
    save_stats(st)
    save_capts(capts)
    
    asyncio.create_task(update_avg_top())
    asyncio.create_task(update_kills_top())
    asyncio.create_task(update_capts_list())
    
    await log_command_success(inter, "удалить_капт", f"Удален капт #{номер} против {removed_capt['vs']}")
    
    await inter.response.send_message(
        f"✅ Капт против **{removed_capt['vs']}** удалён",
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
    
    save_stats({})
    save_capts([])
    
    asyncio.create_task(update_avg_top())
    asyncio.create_task(update_kills_top())
    asyncio.create_task(update_capts_list())
    
    await log_command_success(inter, "сбросить_статистику", f"Удалено {len(capts)} каптов и {stats_count} записей статистики")
    
    await inter.response.send_message(
        f"✅ Статистика сброшена\n"
        f"Удалено каптов: **{len(capts)}**\n"
        f"Удалено записей: **{stats_count}**",
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
    st = load_stats()
    data = st.get(str(target.id))
    
    if not data or data["games"] == 0:
        await log_command_error(inter, "профиль", f"У {target.mention} нет статистики")
        await inter.response.send_message(f"📭 У {target.mention} нет статистики", ephemeral=True)
        return
    
    avg_dmg = data["damage"] // data["games"]
    avg_kills = data["kills"] / data["games"]
    
    embed = discord.Embed(
        title=f"📊 Профиль {target.mention}",
        description=f"Статистика игрока",
        color=0x3498db,
        timestamp=now_msk()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="🎮 Игр", value=data["games"], inline=True)
    embed.add_field(name="💥 Урон", value=f"{data['damage']:,}", inline=True)
    embed.add_field(name="☠️ Киллы", value=data["kills"], inline=True)
    embed.add_field(name="📈 Ср.урон", value=f"{avg_dmg:,}", inline=True)
    embed.add_field(name="📊 Ср.киллы", value=f"{avg_kills:.1f}", inline=True)
    
    await inter.response.send_message(embed=embed)
    await log_command_success(inter, "профиль", f"Показан профиль {target.mention}")

@tree.command(name="капт", description="📋 Детали капта", guild=discord.Object(GUILD_ID))
@app_commands.describe(номер="Номер капта (1 = последний)")
async def capt_details(inter: discord.Interaction, номер: int = 1):
    if not is_viewer(inter.user):
        await inter.response.send_message("❌ Нет доступа", ephemeral=True)
        return
    
    await log_command_start(inter, "капт", {"номер": номер})
    
    await inter.response.defer()
    
    try:
        capts = load_capts()
        if not capts or номер < 1 or номер > len(capts):
            await log_command_error(inter, "капт", f"Капт не найден: номер {номер}")
            await inter.followup.send("❌ Капт не найден", ephemeral=True)
            return

        view = CaptDetailsView(номер, capts[-номер], inter)
        
        try:
            date = datetime.fromisoformat(view.capt_data["date"]).strftime("%d.%m.%Y %H:%M")
        except:
            date = "Дата неизвестна"

        embed = discord.Embed(
            title=f"⚔️ YAK vs {view.capt_data['vs']}",
            description=f"📅 {date}\n{'✅ Победа' if view.capt_data['win'] else '❌ Поражение'}",
            color=0x2ecc71 if view.capt_data["win"] else 0xe74c3c,
            timestamp=now_msk()
        )

        if view.players_sorted:
            text = ""
            for i, p in enumerate(view.players_sorted[:10], 1):
                try:
                    member = await inter.guild.fetch_member(p["user_id"])
                    name = f"{member.mention} ({member.display_name})"
                except:
                    name = f"Игрок {p['user_id']}"
                text += f"**{i}.** {name} — {p['damage']:,} урона, {p['kills']} киллов\n"
            embed.add_field(name="👥 Участники (первые 10)", value=text, inline=False)

        await inter.followup.send(embed=embed, view=view)
        await log_command_success(inter, "капт", f"Показан капт #{номер} против {view.capt_data['vs']}")
            
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
        
        embed = discord.Embed(
            title=f"📊 Статистика {inter.user.mention}",
            description=f"*{period_text.capitalize()}*",
            color=0x3498db,
            timestamp=now_msk()
        )
        embed.set_thumbnail(url=inter.user.display_avatar.url)
        
        embed.add_field(
            name="📈 Основная статистика",
            value=f"```Игр:         {data['games']}\nСредний урон: {avg:,}\nВсего урона:  {data['damage']:,}\nВсего киллов: {data['kills']}```",
            inline=False
        )
        
        avg_users = sorted(st.items(), key=lambda x: x[1]["damage"]/x[1]["games"] if x[1]["games"] >= 3 else 0, reverse=True)
        kills_users = sorted(st.items(), key=lambda x: x[1]["kills"], reverse=True)
        
        avg_pos = next((i+1 for i, (u, _) in enumerate(avg_users) if u == uid and data["games"] >= 3), None)
        kills_pos = next((i+1 for i, (u, _) in enumerate(kills_users) if u == uid), None)
        
        positions = ""
        if avg_pos:
            positions += f"🏅 Место по среднему: **#{avg_pos}**\n"
        if kills_pos:
            positions += f"☠️ Место по киллам: **#{kills_pos}**"
        
        if positions:
            embed.add_field(name="🎯 Позиции в рейтинге", value=positions, inline=False)
        
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
                "`/загрузить_каптов` - Загрузить из файла\n"
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
    
    embed.set_footer(text="YAK Clan Stats Bot v6.0")
    
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
        # Логируем начало обновления
        await log_system_event("🔄 Ручное обновление топов", f"Инициировано пользователем {inter.user.mention}")
        
        # Обновляем все топы
        await update_avg_top()
        await update_kills_top()
        await update_capts_list()
        
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
        
        # Логируем синхронизацию
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
        
        # Фильтруем только игроков с 3+ играми
        filtered = {uid: d for uid, d in st.items() if d["games"] >= 3}
        
        if not filtered:
            # Если нет игроков с 3+ играми, покажем сообщение об этом
            embed = discord.Embed(
                title="🏆 ТОП-10 СРЕДНЕГО УРОНА",
                description="📭 Нет игроков с 3+ играми",
                color=0x9b59b6,
                timestamp=now_msk()
            )
            embed.set_footer(text="Минимум 3 игры для участия")
            
            # Ищем сообщение для редактирования
            async for msg in channel.history(limit=50):
                if msg.author.id == client.user.id and msg.embeds:
                    if "ТОП-10 СРЕДНЕГО УРОНА" in msg.embeds[0].title:
                        try:
                            await msg.edit(embed=embed)
                            await log_system_event("✅ Топ урона обновлен", "Нет игроков с 3+ играми")
                            return
                        except Exception as e:
                            await log_system_event("❌ Ошибка редактирования топа урона", f"Ошибка: {str(e)}")
            
            # Если не нашли сообщение, отправляем новое
            try:
                await channel.send(embed=embed)
                await log_system_event("✅ Топ урона отправлен", "Нет игроков с 3+ играми")
            except Exception as e:
                await log_system_event("❌ Ошибка отправки топа урона", f"Ошибка: {str(e)}")
            return

        # Сортируем игроков по среднему урону
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

        # Ищем существующее сообщение для редактирования
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
        
        # Если не нашли сообщение, отправляем новое
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
        # Синхронизируем команды только для указанной гильдии
        synced = await tree.sync(guild=discord.Object(GUILD_ID))
        print(f"✅ Команды синхронизированы: {len(synced)} команд")
        
        # Логируем запуск
        await log_system_event("✅ Бот запущен", f"Бот успешно запущен. Синхронизировано {len(synced)} команд")
        
        # Показываем список синхронизированных команд
        for cmd in synced:
            print(f"  • /{cmd.name}")
    except Exception as e:
        print(f"❌ Ошибка синхронизации: {e}")
        await log_system_event("❌ Ошибка синхронизации", f"Ошибка: {str(e)}")
    
    if not auto_update.is_running():
        auto_update.start()
        print("✅ Автообновление запущено")
        await log_system_event("✅ Автообновление запущено", "Топы будут обновляться каждый час")
    
    # Принудительно обновляем все списки при запуске
    try:
        await log_system_event("🔄 Обновление при запуске", "Начато принудительное обновление топов при запуске")
        await update_capts_list()
        await update_avg_top()
        await update_kills_top()
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
        
        await log_system_event("👤 Игрок покинул сервер", 
                             f"Игрок {member.mention} ({member.display_name}) покинул сервер. Статистика удалена.")
        
        asyncio.create_task(update_avg_top())
        asyncio.create_task(update_kills_top())

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    # Создаем файлы базы данных, если они не существуют
    for db in [DB_STATS, DB_CAPTS]:
        if not os.path.exists(db):
            with open(db, "w", encoding="utf-8") as f:
                json.dump({} if db == DB_STATS else [], f)
            print(f"📁 Создан {db}")

    try:
        client.run(TOKEN)
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
