# -------------- bot.py (исправленная версия 3.1 - БЕЗ ОШИБОК) --------------
import discord, json, os, asyncio, re, time, glob, shutil
from datetime import datetime, timedelta, timezone
from discord.ext import tasks
from discord import app_commands
from discord.ui import Button, View

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
ADMIN_CHANNEL_ID = 1467757228189810799
WEEKLY_REPORT_CHANNEL_ID = 1467757665076776960
TAG_CHANNEL_ID = 1438943706492309574
RAFFLE_CHANNEL_ID = 1454645262323810376
EVERYONE_ROLE_ID = 1430087806952411230
DEDUCT_ROLE_ID = 1430214760724430968

# DB файлы
DB_RAFFLES = "raffle.json"
DB_WEEKLY_CONFIG = "weekly_config.json"
DB_MESSAGES = "messages.json"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

DB_STATS = "stats.json"
DB_CAPTS = "capts.json"

# ==================== УТИЛИТЫ ====================
def now():
    """Получить текущее время UTC"""
    return datetime.now(timezone.utc)

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
            return json.load(f) or []
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_capts(data: list):
    with open(DB_CAPTS, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_raffles() -> list:
    try:
        with open(DB_RAFFLES, "r", encoding="utf-8") as f:
            return json.load(f) or []
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_raffles(data: list):
    with open(DB_RAFFLES, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

def load_weekly_config() -> dict:
    try:
        with open(DB_WEEKLY_CONFIG, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_weekly_config(cfg: dict):
    with open(DB_WEEKLY_CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2, default=str)

def load_message_map() -> dict:
    try:
        with open(DB_MESSAGES, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_message_map(m: dict):
    with open(DB_MESSAGES, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)

def has_role(member: discord.Member, roles):
    return any(r.name in roles for r in member.roles)

def calc_points(damage: int, kills: int) -> float:
    """Calculate points: 1 kill = 0.5 points, 1 damage = 0.001 points"""
    return round(kills * 0.5 + damage * 0.001, 3)

def progress_bar(percent: int, length: int = 10):
    filled = int(percent / 100 * length)
    filled = max(0, min(length, filled))
    return "█" * filled + "░" * (length - filled)

def medal(pos: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(pos, "")

def get_capts_in_period(days: int = None):
    """Получить капты за период"""
    capts = load_capts()
    if days is None:
        return capts
    
    cutoff = now() - timedelta(days=days)
    return [c for c in capts if datetime.fromisoformat(c["date"]).replace(tzinfo=timezone.utc) >= cutoff]

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

async def log_action(guild: discord.Guild, user: discord.Member, action: str, details: str = ""):
    """Логирование действий в лог-канал"""
    if not LOG_CHANNEL_ID:
        return
    
    channel = guild.get_channel(LOG_CHANNEL_ID)
    if not channel:
        return
    
    embed = discord.Embed(
        description=f"**{action}**\n{details}",
        color=0x3498db,
        timestamp=now()
    )
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    
    try:
        await channel.send(embed=embed)
    except:
        pass

def calculate_stats(capts_list: list) -> dict:
    """Рассчитать статистику из списка каптов"""
    stats = {}
    for capt in capts_list:
        for player in capt.get("players", []):
            uid = str(player.get("user_id"))
            if uid not in stats:
                stats[uid] = {"damage": 0, "kills": 0, "games": 0}
            stats[uid]["damage"] += int(player.get("damage", 0))
            stats[uid]["kills"] += int(player.get("kills", 0))
            stats[uid]["games"] += 1
    return stats

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
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_message(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.primary, custom_id="capts_page")
    async def page_info(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()

    @discord.ui.button(label="➡️", style=discord.ButtonStyle.secondary, custom_id="capts_next")
    async def next_page(self, interaction: discord.Interaction, button: Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            await self.update_message(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="🔄", style=discord.ButtonStyle.success, custom_id="capts_refresh")
    async def refresh(self, interaction: discord.Interaction, button: Button):
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
            await interaction.response.edit_message(embed=embed, view=self)
        except:
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
            timestamp=now()
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
                date = datetime.fromisoformat(capt["date"]).strftime("%d.%m.%Y %H:%M")
                result = "✅" if capt["win"] else "❌"
                players = len(capt["players"])
                damage = sum(p["damage"] for p in capt["players"])
                kills = sum(p["kills"] for p in capt["players"])

                desc += f"**#{num}. Семья vs {capt['vs']}** {result}\n"
                desc += f"🕐 {date} │ 👥 {players} │ 💥 {damage:,} │ ☠️ {kills}\n\n"

            embed.description = desc

            wins = sum(1 for c in self.capts if c["win"])
            total = len(self.capts)
            winrate = (wins/total*100) if total > 0 else 0

            embed.add_field(
                name="📊 Статистика",
                value=f"```Всего:     {total}\nПобед:     {wins}\nПоражений: {total-wins}\nВинрейт:   {winrate:.1f}%```",
                inline=False
            )

        embed.set_footer(text=f"Страница {self.current_page+1}/{self.total_pages}")
        return embed

# ==================== VIEW ДЛЯ РОЗЫГРЫШЕЙ ====================
class RaffleView(View):
    def __init__(self, raffle_id: str):
        super().__init__(timeout=None)
        self.raffle_id = raffle_id

    @discord.ui.button(label="Участвовать", style=discord.ButtonStyle.success, custom_id="raffle_join")
    async def join(self, interaction: discord.Interaction, button: Button):
        raffles = load_raffles()
        raffle = next((r for r in raffles if r.get("id") == self.raffle_id), None)
        if not raffle or not raffle.get("active", True):
            return await interaction.response.send_message("Розыгрыш не активен", ephemeral=True)

        uid = str(interaction.user.id)
        st = load_stats()
        if uid not in st:
            return await interaction.response.send_message("У вас нет статистики", ephemeral=True)

        if uid in raffle.get("participants", []):
            return await interaction.response.send_message("Вы уже участвуете", ephemeral=True)

        raffle.setdefault("participants", []).append(uid)
        save_raffles(raffles)
        await interaction.response.send_message("✅ Вы добавлены в розыгрыш", ephemeral=True)

    @discord.ui.button(label="Выйти", style=discord.ButtonStyle.secondary, custom_id="raffle_leave")
    async def leave(self, interaction: discord.Interaction, button: Button):
        raffles = load_raffles()
        raffle = next((r for r in raffles if r.get("id") == self.raffle_id), None)
        if not raffle:
            return await interaction.response.send_message("Розыгрыш не найден", ephemeral=True)

        uid = str(interaction.user.id)
        if uid in raffle.get("participants", []):
            raffle["participants"].remove(uid)
            save_raffles(raffles)
            return await interaction.response.send_message("✅ Вы удалены", ephemeral=True)
        return await interaction.response.send_message("Вы не участвуете", ephemeral=True)

    @discord.ui.button(label="Выбрать победителя", style=discord.ButtonStyle.danger, custom_id="raffle_pick")
    async def pick(self, interaction: discord.Interaction, button: Button):
        if not has_role(interaction.user, ADMIN_ROLES):
            return await interaction.response.send_message("Нет доступа", ephemeral=True)

        raffles = load_raffles()
        raffle = next((r for r in raffles if r.get("id") == self.raffle_id), None)
        if not raffle:
            return await interaction.response.send_message("Розыгрыш не найден", ephemeral=True)

        parts = raffle.get("participants", [])
        if not parts:
            return await interaction.response.send_message("Нет участников", ephemeral=True)

        import random
        winner = random.choice(parts)
        raffle.setdefault("winners", []).append(winner)
        raffle["active"] = False
        save_raffles(raffles)

        try:
            member = await interaction.guild.fetch_member(int(winner))
            name = member.mention
        except:
            name = f"ID {winner}"

        await interaction.response.send_message(f"Победитель: {name}", ephemeral=True)

# ==================== АДМИН-ПАНЕЛЬ ====================
class AdminPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Просмотр участников", style=discord.ButtonStyle.blurple, custom_id="admin_view_members", row=0)
    async def view_members(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_role(interaction.user, ADMIN_ROLES):
            return await interaction.response.send_message("Нет доступа", ephemeral=True)
        st = load_stats()
        embed = discord.Embed(title="👥 ВСЕ УЧАСТНИКИ", color=0x3498db)
        if not st:
            embed.description = "Нет участников"
        else:
            desc = ""
            for uid, data in sorted(st.items(), key=lambda x: x[1]["games"], reverse=True)[:20]:
                try:
                    member = await interaction.guild.fetch_member(int(uid))
                    name = member.display_name
                except:
                    name = f"ID {uid}"
                desc += f"**{name}** - {data['games']} игр, {data['damage']:,} урона\n"
            embed.description = desc
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Добавить участника", style=discord.ButtonStyle.green, custom_id="admin_add_member", row=0)
    async def add_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_role(interaction.user, ADMIN_ROLES):
            return await interaction.response.send_message("Нет доступа", ephemeral=True)
        class AddMemberModal(discord.ui.Modal, title="Добавить участника"):
            user_id = discord.ui.TextInput(label="ID участника", placeholder="12345")
            games = discord.ui.TextInput(label="Игр", placeholder="0", default="0")
            damage = discord.ui.TextInput(label="Урона", placeholder="0", default="0")
            kills = discord.ui.TextInput(label="Киллов", placeholder="0", default="0")
            async def on_submit(self, modal_interaction: discord.Interaction):
                try:
                    st = load_stats()
                    uid = str(int(self.user_id.value))
                    st[uid] = {"damage": int(self.damage.value), "kills": int(self.kills.value), "games": int(self.games.value), "points": 0.0}
                    save_stats(st)
                    await modal_interaction.response.send_message(f"✅ Участник добавлен", ephemeral=True)
                except Exception as e:
                    await modal_interaction.response.send_message(f"❌ Ошибка: {str(e)}", ephemeral=True)
        await interaction.response.send_modal(AddMemberModal())

    @discord.ui.button(label="Удалить участника", style=discord.ButtonStyle.red, custom_id="admin_del_member", row=0)
    async def del_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_role(interaction.user, ADMIN_ROLES):
            return await interaction.response.send_message("Нет доступа", ephemeral=True)
        class DelMemberModal(discord.ui.Modal, title="Удалить участника"):
            user_id = discord.ui.TextInput(label="ID участника", placeholder="12345")
            async def on_submit(self, modal_interaction: discord.Interaction):
                try:
                    st = load_stats()
                    uid = str(int(self.user_id.value))
                    if uid in st:
                        del st[uid]
                        save_stats(st)
                        await modal_interaction.response.send_message(f"✅ Участник удален", ephemeral=True)
                    else:
                        await modal_interaction.response.send_message(f"❌ Участник не найден", ephemeral=True)
                except Exception as e:
                    await modal_interaction.response.send_message(f"❌ Ошибка: {str(e)}", ephemeral=True)
        await interaction.response.send_modal(DelMemberModal())

    @discord.ui.button(label="Редактировать капт", style=discord.ButtonStyle.secondary, custom_id="admin_edit_capt", row=0)
    async def edit_capt_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_role(interaction.user, ADMIN_ROLES):
            return await interaction.response.send_message("Нет доступа", ephemeral=True)
        class CaptEditModal(discord.ui.Modal, title="Редактировать капт"):
            номер = discord.ui.TextInput(label="Номер капта (1=последний)", placeholder="1")
            vs = discord.ui.TextInput(label="Противник (оставьте пустым чтобы не менять)", required=False)
            дата = discord.ui.TextInput(label="Дата (ДД.MM.YYYY HH:MM) (опционально)", required=False)
            результат = discord.ui.TextInput(label="Результат (win/lose) (опционально)", required=False)
            async def on_submit(self, modal_interaction: discord.Interaction):
                try:
                    номер = int(self.номер.value)
                    capts = load_capts()
                    if номер < 1 or номер > len(capts):
                        return await modal_interaction.response.send_message("❌ Капт не найден", ephemeral=True)
                    capt = capts[-номер]
                    if self.vs.value:
                        capt['vs'] = self.vs.value
                    if self.дата.value:
                        try:
                            dt = datetime.strptime(self.дата.value, "%d.%m.%Y %H:%M")
                            capt['date'] = dt.replace(tzinfo=MSK_TZ).isoformat()
                        except:
                            pass
                    if self.результат.value:
                        capt['win'] = self.результат.value.strip().lower() in ['win','победа','в']
                    save_capts(capts)
                    asyncio.create_task(update_capts_list())
                    asyncio.create_task(update_avg_top())
                    asyncio.create_task(update_kills_top())
                    await modal_interaction.response.send_message("✅ Капт обновлён", ephemeral=True)
                except Exception as e:
                    await modal_interaction.response.send_message(f"❌ Ошибка: {str(e)}", ephemeral=True)
        await interaction.response.send_modal(CaptEditModal())

    @discord.ui.button(label="Редактировать игрока", style=discord.ButtonStyle.secondary, custom_id="admin_edit_player", row=0)
    async def edit_player_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_role(interaction.user, ADMIN_ROLES):
            return await interaction.response.send_message("Нет доступа", ephemeral=True)
        class PlayerEditModal(discord.ui.Modal, title="Редактировать игрока"):
            номер = discord.ui.TextInput(label="Номер капта (1=последний)", placeholder="1")
            user_id = discord.ui.TextInput(label="ID игрока", placeholder="12345")
            damage = discord.ui.TextInput(label="Урон", placeholder="0")
            kills = discord.ui.TextInput(label="Киллы", placeholder="0")
            async def on_submit(self, modal_interaction: discord.Interaction):
                try:
                    номер = int(self.номер.value)
                    uid = str(int(self.user_id.value))
                    new_damage = int(self.damage.value)
                    new_kills = int(self.kills.value)
                    capts = load_capts()
                    if номер < 1 or номер > len(capts):
                        return await modal_interaction.response.send_message("❌ Капт не найден", ephemeral=True)
                    capt = capts[-номер]
                    player = next((p for p in capt.get('players', []) if str(p.get('user_id')) == uid), None)
                    st = load_stats()
                    if player:
                        old_d = int(player.get('damage',0))
                        old_k = int(player.get('kills',0))
                        player['damage'] = new_damage
                        player['kills'] = new_kills
                        if uid in st:
                            st[uid]['damage'] = max(0, st[uid].get('damage',0) - old_d + new_damage)
                            st[uid]['kills'] = max(0, st[uid].get('kills',0) - old_k + new_kills)
                        else:
                            st[uid] = {'damage': new_damage, 'kills': new_kills, 'games': 1, 'points': 0.0}
                        save_stats(st)
                        save_capts(capts)
                        asyncio.create_task(update_capts_list())
                        asyncio.create_task(update_avg_top())
                        asyncio.create_task(update_kills_top())
                        await modal_interaction.response.send_message("✅ Игрок обновлён", ephemeral=True)
                    else:
                        await modal_interaction.response.send_message("❌ Игрок не найден в капте", ephemeral=True)
                except Exception as e:
                    await modal_interaction.response.send_message(f"❌ Ошибка: {str(e)}", ephemeral=True)
        await interaction.response.send_modal(PlayerEditModal())

    @discord.ui.button(label="Корректировать баллы", style=discord.ButtonStyle.blurple, custom_id="admin_points", row=1)
    async def adjust_points(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_role(interaction.user, ADMIN_ROLES):
            return await interaction.response.send_message("Нет доступа", ephemeral=True)
        class PointsModal(discord.ui.Modal, title="Корректировка баллов"):
            user_id = discord.ui.TextInput(label="ID участника", placeholder="12345")
            points = discord.ui.TextInput(label="Баллы (+/-)", placeholder="10")
            async def on_submit(self, modal_interaction: discord.Interaction):
                try:
                    st = load_stats()
                    uid = str(int(self.user_id.value))
                    if uid not in st:
                        st[uid] = {"damage": 0, "kills": 0, "games": 0, "points": 0.0}
                    delta = float(self.points.value)
                    st[uid]["points"] = max(0.0, round(st[uid].get("points", 0.0) + delta, 3))
                    save_stats(st)
                    await modal_interaction.response.send_message(f"✅ Баллы обновлены: {st[uid]['points']}", ephemeral=True)
                except Exception as e:
                    await modal_interaction.response.send_message(f"❌ Ошибка: {str(e)}", ephemeral=True)
        await interaction.response.send_modal(PointsModal())

    @discord.ui.button(label="Статистика всех", style=discord.ButtonStyle.blurple, custom_id="admin_stats", row=1)
    async def view_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_role(interaction.user, ADMIN_ROLES):
            return await interaction.response.send_message("Нет доступа", ephemeral=True)
        st = load_stats()
        embed = discord.Embed(title="📊 СТАТИСТИКА ВСЕХ ИГРОКОВ", color=0x9b59b6)
        if not st:
            embed.description = "Нет данных"
        else:
            top_damage = sorted(st.items(), key=lambda x: x[1]["damage"], reverse=True)[:5]
            top_kills = sorted(st.items(), key=lambda x: x[1]["kills"], reverse=True)[:5]
            desc = "**ТОП-5 ПО УРОНУ:**\n"
            for i, (uid, data) in enumerate(top_damage, 1):
                try:
                    member = await interaction.guild.fetch_member(int(uid))
                    name = member.display_name
                except:
                    name = f"ID {uid}"
                desc += f"{i}. {name} - {data['damage']:,}\n"
            desc += "\n**ТОП-5 ПО КИЛЛАМ:**\n"
            for i, (uid, data) in enumerate(top_kills, 1):
                try:
                    member = await interaction.guild.fetch_member(int(uid))
                    name = member.display_name
                except:
                    name = f"ID {uid}"
                desc += f"{i}. {name} - {data['kills']}\n"
            embed.description = desc
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Розыгрыши", style=discord.ButtonStyle.success, custom_id="admin_raffles", row=1)
    async def view_raffles(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_role(interaction.user, ADMIN_ROLES):
            return await interaction.response.send_message("Нет доступа", ephemeral=True)
        raffles = load_raffles()
        embed = discord.Embed(title="🎁 РОЗЫГРЫШИ", color=0xf39c12)
        if not raffles:
            embed.description = "Нет розыгрышей"
        else:
            desc = ""
            for r in raffles:
                status = "✅ Активен" if r.get("active") else "❌ Завершен"
                desc += f"**{r.get('name')}** {status}\n"
                desc += f"Участников: {len(r.get('participants', []))} | Победителей: {len(r.get('winners', []))}\n\n"
            embed.description = desc
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Теги на капт", style=discord.ButtonStyle.blurple, custom_id="admin_tags", row=2)
    async def manage_tags(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_role(interaction.user, ADMIN_ROLES):
            return await interaction.response.send_message("Нет доступа", ephemeral=True)
        class TagModal(discord.ui.Modal, title="Отправить тег на капт"):
            times = discord.ui.TextInput(label="Кол-во повторов", placeholder="1", default="1")
            message = discord.ui.TextInput(label="Текст сообщения", placeholder="Пример", required=False)
            async def on_submit(self, modal_interaction: discord.Interaction):
                try:
                    times = int(self.times.value)
                    channel = interaction.guild.get_channel(TAG_CHANNEL_ID)
                    role = interaction.guild.get_role(EVERYONE_ROLE_ID)
                    if not channel or not role:
                        await modal_interaction.response.send_message("❌ Канал или роль не найдены", ephemeral=True)
                        return
                    for _ in range(times):
                        await channel.send(f"{role.mention}\n{self.message.value if self.message.value else ''}")
                        await asyncio.sleep(2)
                    await modal_interaction.response.send_message("✅ Теги отправлены", ephemeral=True)
                except Exception as e:
                    await modal_interaction.response.send_message(f"❌ Ошибка: {str(e)}", ephemeral=True)
        await interaction.response.send_modal(TagModal())

    @discord.ui.button(label="Синхронизировать", style=discord.ButtonStyle.primary, custom_id="admin_sync", row=2)
    async def sync_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_role(interaction.user, ADMIN_ROLES):
            return await interaction.response.send_message("Нет доступа", ephemeral=True)
        try:
            synced = await tree.sync(guild=discord.Object(GUILD_ID))
            await interaction.response.send_message(f"Синхronized {len(synced)} commands", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)

# ==================== КОМАНДЫ ====================
@tree.command(name="добавить_капт", description="📝 Добавить новый капт", guild=discord.Object(GUILD_ID))
@app_commands.describe(
    против="Против кого играли",
    результат="win или lose",
    дата="Дата (ДД.ММ.ГГГГ ЧЧ:ММ)"
)
async def add_capt(inter: discord.Interaction, против: str, результат: str, дата: str = None):
    if not has_role(inter.user, ADMIN_ROLES):
        return await inter.response.send_message("❌ Нет доступа", ephemeral=True)
    
    result_text = результат.strip().lower()
    if result_text not in ["win", "lose", "победа", "поражение", "в", "п"]:
        return await inter.response.send_message("❌ Результат: win или lose", ephemeral=True)
    
    win = result_text in ["win", "победа", "в"]
    
    capt_date = now()
    if дата:
        try:
            capt_date = datetime.strptime(дата, "%d.%m.%Y %H:%M").replace(tzinfo=timezone.utc)
        except:
            try:
                capt_date = datetime.strptime(дата, "%d.%m.%Y").replace(tzinfo=timezone.utc)
            except:
                return await inter.response.send_message("❌ Неверный формат даты", ephemeral=True)
    
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
    
    await log_action(
        inter.guild, inter.user,
        "➕ Капт создан",
        f"Против: **{против}**\nРезультат: {'✅ Победа' if win else '❌ Поражение'}"
    )
    
    await inter.response.send_message(
        f"✅ Капт против **{против}** создан!\n"
        f"Результат: {'✅ Победа' if win else '❌ Поражение'}",
        ephemeral=True
    )

@tree.command(name="добавить_игрока", description="👤 Добавить игрока в капт", guild=discord.Object(GUILD_ID))
@app_commands.describe(
    игрок="@mention, ID, или имя",
    урон="Damage",
    киллы="Kills",
    номер_капта="Capt number (1 = latest)"
)
async def add_player(inter: discord.Interaction, игрок: str, урон: int, киллы: int, номер_капта: int = 1):
    if not has_role(inter.user, ADMIN_ROLES):
        return await inter.response.send_message("No access", ephemeral=True)
    
    mention_text = игрок.strip()
    user_id = None
    member = None
    
    # Try @mention format
    if mention_text.startswith("<@") and mention_text.endswith(">"):
        try:
            user_id = int(mention_text.strip("<@!>"))
            member = await inter.guild.fetch_member(user_id)
        except:
            pass
    
    # Try numeric ID
    if not member:
        try:
            user_id = int(mention_text)
            member = await inter.guild.fetch_member(user_id)
        except:
            pass
    
    # Try to find by name (search all guild members)
    if not member:
        try:
            # Search through guild members
            async for m in inter.guild.fetch_members(limit=None):
                if m.display_name.lower() == mention_text.lower() or m.name.lower() == mention_text.lower():
                    member = m
                    user_id = m.id
                    break
        except:
            pass
    
    if not member:
        return await inter.response.send_message(f"Player not found: {mention_text}", ephemeral=True)

    capts = load_capts()
    if номер_капта < 1 or номер_капта > len(capts):
        return await inter.response.send_message("Capt not found", ephemeral=True)

    capt = capts[-номер_капта]
    
    if any(p["user_id"] == user_id for p in capt["players"]):
        return await inter.response.send_message(f"Already added: {member.display_name}", ephemeral=True)

    capt["players"].append({
        "user_id": user_id,
        "user_name": member.display_name,
        "damage": урон,
        "kills": киллы
    })

    st = load_stats()
    uid = str(user_id)
    if uid not in st:
        st[uid] = {"damage": 0, "kills": 0, "games": 0}
    
    st[uid]["damage"] += урон
    st[uid]["kills"] += киллы
    st[uid]["games"] += 1
    
    save_stats(st)
    save_capts(capts)
    
    asyncio.create_task(update_capts_list())
    asyncio.create_task(update_avg_top())
    asyncio.create_task(update_kills_top())
    
    await log_action(
        inter.guild, inter.user,
        "Player added",
        f"Capt: {capt.get('vs', 'Unknown')}\nPlayer: {member.mention}\nDamage: {урон:,}\nKills: {киллы}"
    )
    
    await inter.response.send_message(
        f"Added: {member.display_name}\n"
        f"Damage: {урон:,} | Kills: {киллы}",
        ephemeral=True
    )

@tree.command(name="загрузить_игроков", description="📤 Загрузить игроков из текста", guild=discord.Object(GUILD_ID))
@app_commands.describe(
    данные="ID урон киллы (каждый с новой строки)",
    номер_капта="Номер капта"
)
async def upload_players(inter: discord.Interaction, данные: str, номер_капта: int = 1):
    if not has_role(inter.user, ADMIN_ROLES):
        return await inter.response.send_message("❌ Нет доступа", ephemeral=True)
    
    try:
        await inter.response.defer(ephemeral=True)
        defer_used = True
    except:
        defer_used = False
    
    try:
        capts = load_capts()
        if номер_капта < 1 or номер_капта > len(capts):
            if defer_used:
                await inter.followup.send("❌ Капт не найден", ephemeral=True)
            else:
                await inter.response.send_message("❌ Капт не найден", ephemeral=True)
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
                errors.append(f"⚠️ {member.display_name} уже добавлен")
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
        
        asyncio.create_task(update_capts_list())
        asyncio.create_task(update_avg_top())
        asyncio.create_task(update_kills_top())
        
        await log_action(
            inter.guild, inter.user,
            "📤 Массовое добавление",
            f"Капт #{len(capts) - номер_капта + 1}\nДобавлено: {added} игроков"
        )
        
        msg = f"✅ Добавлено игроков: **{added}**"
        if errors:
            msg += f"\n\n⚠️ Ошибки:\n" + "\n".join(errors[:5])
            if len(errors) > 5:
                msg += f"\n... и ещё {len(errors)-5}"
        
        if defer_used:
            await inter.followup.send(msg, ephemeral=True)
        else:
            await inter.response.send_message(msg, ephemeral=True)
            
    except Exception as e:
        print(f"❌ Ошибка в upload_players: {e}")
        try:
            if defer_used:
                await inter.followup.send("❌ Произошла ошибка при выполнении команды", ephemeral=True)
            else:
                await inter.response.send_message("❌ Произошла ошибка при выполнении команды", ephemeral=True)
        except:
            pass

@tree.command(name="загрузить_каптов", description="📁 Загрузить капты (Семья (ИМЯ) (WIN/LOSE) (ДАТА)\\nid kills dmg...)", guild=discord.Object(GUILD_ID))
@app_commands.describe(данные="Текст в формате: Семья (ИМЯ) (WIN/LOSE) (ДАТА)\\nid kills dmg")
async def upload_capts(inter: discord.Interaction, данные: str):
    if not has_role(inter.user, ADMIN_ROLES):
        return await inter.response.send_message("Нет доступа", ephemeral=True)
    
    try:
        await inter.response.defer(ephemeral=True)
    except:
        pass
    
    try:
        capts = load_capts()
        st = load_stats()
        lines = данные.strip().split('\n')
        
        added_capts = 0
        current_capt_info = None
        current_players = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check if this is a header line: Семья (Name) (WIN/LOSE) (DATE)
            if line.startswith("Семья"):
                # Save previous capt if exists
                if current_capt_info and current_players:
                    new_capt = {
                        "vs": current_capt_info["vs"],
                        "date": current_capt_info["date"],
                        "win": current_capt_info["win"],
                        "players": current_players
                    }
                    capts.append(new_capt)
                    added_capts += 1
                
                # Parse header
                import re
                match = re.match(r"Семья\s*\(([^)]+)\)\s*\(([^)]+)\)\s*\(([^)]+)\)", line)
                if not match:
                    continue
                
                vs_name, result_str, date_str = match.groups()
                result = result_str.strip().upper() in ["WIN", "ПОБЕДА", "В"]
                
                # Parse date
                try:
                    capt_date = datetime.strptime(date_str.strip(), "%d.%m.%Y %H:%M").replace(tzinfo=timezone.utc)
                except:
                    try:
                        capt_date = datetime.strptime(date_str.strip(), "%d.%m.%Y").replace(tzinfo=timezone.utc)
                    except:
                        capt_date = now()
                
                current_capt_info = {
                    "vs": vs_name.strip(),
                    "date": capt_date.isoformat(),
                    "win": result
                }
                current_players = []
            
            elif current_capt_info and line.startswith("id"):
                # Parse player line: id (discord_id) kills dmg OR id discord_id kills dmg
                parts = line.split()
                if len(parts) < 4:
                    continue
                
                try:
                    # Remove 'id' prefix and parentheses if present
                    user_id_str = parts[1].strip("()")
                    user_id = int(user_id_str)
                    kills = int(parts[2].replace("k", "").replace("K", ""))
                    damage = int(parts[3].replace("dmg", "").replace("k", "000").replace("K", "000"))
                    
                    # Get user name
                    try:
                        member = await inter.guild.fetch_member(user_id)
                        user_name = member.display_name
                    except:
                        user_name = f"User {user_id}"
                    
                    current_players.append({
                        "user_id": user_id,
                        "user_name": user_name,
                        "damage": damage,
                        "kills": kills
                    })
                    
                    # Update stats
                    uid = str(user_id)
                    if uid not in st:
                        st[uid] = {"damage": 0, "kills": 0, "games": 0}
                    st[uid]["damage"] += damage
                    st[uid]["kills"] += kills
                    st[uid]["games"] += 1
                except Exception as e:
                    print(f"[ERROR] Player parse error: {e}")
                    continue
        
        # Save last capt
        if current_capt_info and current_players:
            new_capt = {
                "vs": current_capt_info["vs"],
                "date": current_capt_info["date"],
                "win": current_capt_info["win"],
                "players": current_players
            }
            capts.append(new_capt)
            added_capts += 1
        
        save_capts(capts)
        save_stats(st)
        
        asyncio.create_task(update_capts_list())
        asyncio.create_task(update_avg_top())
        asyncio.create_task(update_kills_top())
        
        try:
            await inter.followup.send(f"Loaded: {added_capts} capts", ephemeral=True)
        except:
            await inter.response.send_message(f"Loaded: {added_capts} capts", ephemeral=True)
        
    except Exception as e:
        print(f"[ERROR] upload_capts: {e}")
        try:
            await inter.followup.send(f"Error: {str(e)}", ephemeral=True)
        except:
            await inter.response.send_message(f"Error: {str(e)}", ephemeral=True)

@tree.command(name="удалить_капт", description="🗑️ Удалить капт", guild=discord.Object(GUILD_ID))
@app_commands.describe(номер="Номер капта")
async def delete_capt(inter: discord.Interaction, номер: int):
    if not has_role(inter.user, ADMIN_ROLES):
        return await inter.response.send_message("❌ Нет доступа", ephemeral=True)
    
    capts = load_capts()
    if номер < 1 or номер > len(capts):
        return await inter.response.send_message("❌ Капт не найден", ephemeral=True)
    
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
    
    asyncio.create_task(update_capts_list())
    asyncio.create_task(update_avg_top())
    asyncio.create_task(update_kills_top())
    
    await log_action(
        inter.guild, inter.user,
        "🗑️ Капт удалён",
        f"Против: **{removed_capt['vs']}**"
    )
    
    await inter.response.send_message(
        f"✅ Капт против **{removed_capt['vs']}** удалён",
        ephemeral=True
    )

@tree.command(name="сбросить_статистику", description="🔄 Сбросить всю статистику", guild=discord.Object(GUILD_ID))
async def reset_stats(inter: discord.Interaction):
    if not has_role(inter.user, ADMIN_ROLES):
        return await inter.response.send_message("❌ Нет доступа", ephemeral=True)
    
    # Подтверждение через кнопку
    class ResetConfirmView(View):
        @discord.ui.button(label="✅ Подтвердить сброс", style=discord.ButtonStyle.danger)
        async def confirm(self, button_inter: discord.Interaction, button: discord.ui.Button):
            if button_inter.user.id != inter.user.id:
                return await button_inter.response.send_message("❌ Вы не можете это делать", ephemeral=True)
            
            # Создаем бекап
            import time
            backup_time = time.strftime("%Y-%m-%d_%H-%M-%S")
            
            capts = load_capts()
            stats = load_stats()
            
            try:
                with open(f"backup_stats_{backup_time}.json", "w", encoding="utf-8") as f:
                    json.dump(stats, f, ensure_ascii=False, indent=2)
                with open(f"backup_capts_{backup_time}.json", "w", encoding="utf-8") as f:
                    json.dump(capts, f, ensure_ascii=False, indent=2)
            except:
                pass
            
            save_stats({})
            save_capts([])
            
            asyncio.create_task(update_capts_list())
            asyncio.create_task(update_avg_top())
            asyncio.create_task(update_kills_top())
            
            await log_action(inter.guild, inter.user, "Сброс статистики", f"Удалено {len(capts)} каптов и {len(stats)} записей (бекап: backup_{backup_time})")
            
            embed = discord.Embed(title="✅ Статистика сброшена", description=f"Бекап сохранен: backup_{backup_time}", color=0x2ecc71)
            await button_inter.response.send_message(embed=embed, ephemeral=True)
        
        @discord.ui.button(label="❌ Отмена", style=discord.ButtonStyle.grey)
        async def cancel(self, button_inter: discord.Interaction, button: discord.ui.Button):
            if button_inter.user.id != inter.user.id:
                return
            await button_inter.response.send_message("✅ Отменено", ephemeral=True)
    
    embed = discord.Embed(title="⚠️ ВНИМАНИЕ", description="Вы уверены? Это удалит ВСЮ статистику! Будет создан бекап.", color=0xe74c3c)
    await inter.response.send_message(embed=embed, view=ResetConfirmView(), ephemeral=True)

@tree.command(name="список_каптов", description="📜 История каптов", guild=discord.Object(GUILD_ID))
@app_commands.describe(period="Период")
@app_commands.choices(period=[
    app_commands.Choice(name="За всё время", value="all"),
    app_commands.Choice(name="За неделю", value="week"),
    app_commands.Choice(name="За месяц", value="month")
])
async def list_capts(inter: discord.Interaction, period: str = "all"):
    if not has_role(inter.user, VIEW_ROLES):
        return await inter.response.send_message("❌ Нет доступа", ephemeral=True)
    
    try:
        await inter.response.defer(ephemeral=True)
        defer_used = True
    except:
        defer_used = False
    
    try:
        view = CaptsListView(inter.guild, period)
        embed = await view.create_embed()
        
        if defer_used:
            await inter.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await inter.response.send_message(embed=embed, view=view, ephemeral=True)
            
    except Exception as e:
        print(f"❌ Ошибка в list_capts: {e}")
        try:
            if defer_used:
                await inter.followup.send("❌ Произошла ошибка при выполнении команды", ephemeral=True)
            else:
                await inter.response.send_message("❌ Произошла ошибка при выполнении команды", ephemeral=True)
        except:
            pass

@tree.command(name="список_бекапов", description="💾 Список бекапов", guild=discord.Object(GUILD_ID))
async def list_backups(inter: discord.Interaction):
    if not has_role(inter.user, ADMIN_ROLES):
        return await inter.response.send_message("Нет доступа", ephemeral=True)
    
    import os
    import glob
    backups = glob.glob("backup_*.json")
    
    embed = discord.Embed(title="💾 ДОСТУПНЫЕ БЕКАПЫ", color=0x3498db)
    if not backups:
        embed.description = "Нет бекапов"
    else:
        desc = ""
        for backup in sorted(backups, reverse=True)[:10]:
            size = os.path.getsize(backup) / 1024
            desc += f"📄 `{backup}` ({size:.1f} KB)\n"
        embed.description = desc
    
    await inter.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="восстановить_бекап", description="♻️ Восстановить из бекапа", guild=discord.Object(GUILD_ID))
@app_commands.describe(файл="Имя файла бекапа")
async def restore_backup(inter: discord.Interaction, файл: str):
    if not has_role(inter.user, ADMIN_ROLES):
        return await inter.response.send_message("Нет доступа", ephemeral=True)
    
    try:
        with open(файл, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if "backup_stats" in файл:
            save_stats(data)
            await inter.response.send_message(f"✅ Статистика восстановлена из {файл}", ephemeral=True)
        elif "backup_capts" in файл:
            save_capts(data)
            await inter.response.send_message(f"✅ Капты восстановлены из {файл}", ephemeral=True)
        else:
            await inter.response.send_message("❌ Неизвестный тип бекапа", ephemeral=True)
        
        asyncio.create_task(update_capts_list())
        asyncio.create_task(update_avg_top())
        asyncio.create_task(update_kills_top())
        
    except FileNotFoundError:
        await inter.response.send_message(f"❌ Файл {файл} не найден", ephemeral=True)
    except Exception as e:
        await inter.response.send_message(f"❌ Ошибка: {str(e)}", ephemeral=True)

@tree.command(name="топ_средний", description="🏆 Топ по среднему урону", guild=discord.Object(GUILD_ID))
@app_commands.describe(period="Период")
@app_commands.choices(period=[
    app_commands.Choice(name="За всё время", value="all"),
    app_commands.Choice(name="За неделю", value="week"),
    app_commands.Choice(name="За месяц", value="month")
])
async def top_avg(inter: discord.Interaction, period: str = "all"):
    if not has_role(inter.user, VIEW_ROLES):
        return await inter.response.send_message("❌ Нет доступа", ephemeral=True)
    
    try:
        await inter.response.defer(ephemeral=True)
        defer_used = True
    except:
        defer_used = False
    
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
            if defer_used:
                await inter.followup.send("📭 Нет игроков с 3+ играми", ephemeral=True)
            else:
                await inter.response.send_message("📭 Нет игроков с 3+ играми", ephemeral=True)
            return

        users = sorted(filtered.items(), key=lambda x: x[1]["damage"]/x[1]["games"], reverse=True)[:10]
        
        embed = discord.Embed(
            title=f"🏆 ТОП-10 СРЕДНЕГО УРОНА",
            description=f"*Статистика {period_text}*",
            color=0x9b59b6,
            timestamp=now()
        )
        
        desc = ""
        for i, (uid, data) in enumerate(users, 1):
            try:
                member = await inter.guild.fetch_member(int(uid))
                name = member.display_name
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
        
        if defer_used:
            await inter.followup.send(embed=embed, ephemeral=True)
        else:
            await inter.response.send_message(embed=embed, ephemeral=True)
            
    except Exception as e:
        print(f"❌ Ошибка в top_avg: {e}")
        try:
            if defer_used:
                await inter.followup.send("❌ Произошла ошибка при выполнении команды", ephemeral=True)
            else:
                await inter.response.send_message("❌ Произошла ошибка при выполнении команды", ephemeral=True)
        except:
            pass

@tree.command(name="топ_киллы", description="☠️ Топ по киллам", guild=discord.Object(GUILD_ID))
@app_commands.describe(period="Период")
@app_commands.choices(period=[
    app_commands.Choice(name="За всё время", value="all"),
    app_commands.Choice(name="За неделю", value="week"),
    app_commands.Choice(name="За месяц", value="month")
])
async def top_kills(inter: discord.Interaction, period: str = "all"):
    if not has_role(inter.user, VIEW_ROLES):
        return await inter.response.send_message("❌ Нет доступа", ephemeral=True)
    
    try:
        await inter.response.defer(ephemeral=True)
        defer_used = True
    except:
        defer_used = False
    
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
            if defer_used:
                await inter.followup.send("📭 Статистика пуста", ephemeral=True)
            else:
                await inter.response.send_message("📭 Статистика пуста", ephemeral=True)
            return

        users = sorted(st.items(), key=lambda x: x[1]["kills"], reverse=True)[:10]

        embed = discord.Embed(
            title=f"☠️ ТОП-10 ПО КИЛЛАМ",
            description=f"*Статистика {period_text}*",
            color=0xe74c3c,
            timestamp=now()
        )
        
        desc = ""
        for i, (uid, data) in enumerate(users, 1):
            try:
                member = await inter.guild.fetch_member(int(uid))
                name = member.display_name
            except:
                name = f"Игрок {uid}"
            
            if i <= 3:
                desc += f"{medal(i)} **{name}**\n"
            else:
                desc += f"`{i}.` **{name}**\n"
            
            desc += f"```Киллов:      {data['kills']}\nИгр:         {data['games']}\nСредний урон: {data['damage']//data['games']:,}```\n"
        
        embed.description = f"*Статистика {period_text}*\n\n" + desc
        
        if defer_used:
            await inter.followup.send(embed=embed, ephemeral=True)
        else:
            await inter.response.send_message(embed=embed, ephemeral=True)
            
    except Exception as e:
        print(f"❌ Ошибка в top_kills: {e}")
        try:
            if defer_used:
                await inter.followup.send("❌ Произошла ошибка при выполнении команды", ephemeral=True)
            else:
                await inter.response.send_message("❌ Произошла ошибка при выполнении команды", ephemeral=True)
        except:
            pass

@tree.command(name="моя_статистика", description="📊 Ваша статистика", guild=discord.Object(GUILD_ID))
@app_commands.describe(period="Период")
@app_commands.choices(period=[
    app_commands.Choice(name="За всё время", value="all"),
    app_commands.Choice(name="За неделю", value="week"),
    app_commands.Choice(name="За месяц", value="month")
])
async def my_stats(inter: discord.Interaction, period: str = "all"):
    if not has_role(inter.user, VIEW_ROLES):
        return await inter.response.send_message("❌ Нет доступа", ephemeral=True)
    
    try:
        await inter.response.defer(ephemeral=True)
        defer_used = True
    except:
        defer_used = False
    
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
            if defer_used:
                await inter.followup.send(f"📭 Нет статистики {period_text}", ephemeral=True)
            else:
                await inter.response.send_message(f"📭 Нет статистики {period_text}", ephemeral=True)
            return
        
        data = st[uid]
        avg = data["damage"] // data["games"] if data["games"] > 0 else 0
        
        embed = discord.Embed(
            title=f"📊 Статистика {inter.user.display_name}",
            description=f"*{period_text.capitalize()}*",
            color=0x3498db,
            timestamp=now()
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
        
        if defer_used:
            await inter.followup.send(embed=embed, ephemeral=True)
        else:
            await inter.response.send_message(embed=embed, ephemeral=True)
            
    except Exception as e:
        print(f"❌ Ошибка в my_stats: {e}")
        try:
            if defer_used:
                await inter.followup.send("❌ Произошла ошибка при выполнении команды", ephemeral=True)
            else:
                await inter.response.send_message("❌ Произошла ошибка при выполнении команды", ephemeral=True)
        except:
            pass

@tree.command(name="справка", description="📚 Помощь по командам", guild=discord.Object(GUILD_ID))
async def help_cmd(inter: discord.Interaction):
    is_admin = has_role(inter.user, ADMIN_ROLES)
    
    embed = discord.Embed(
        title="📚 СПРАВКА ПО КОМАНДАМ",
        description="*Статистика Семьи YAK*",
        color=0xe74c3c,
        timestamp=now()
    )
    
    embed.add_field(
        name="👥 Для всех",
        value=(
            "`/список_каптов` - История каптов\n"
            "`/топ_средний` - Топ по урону\n"
            "`/топ_киллы` - Топ по киллам\n"
            "`/моя_статистика` - Ваша стата\n"
            "`/справка` - Эта справка"
        ),
        inline=False
    )
    
    if is_admin:
        embed.add_field(
            name="👑 Для админов",
            value=(
                "`/добавить_капт` - Создать капт\n"
                "`/добавить_игрока` - Добавить игрока\n"
                "`/загрузить_игроков` - Массовое добавление\n"
                "`/загрузить_каптов` - Загрузить из файла\n"
                "`/удалить_капт` - Удалить капт\n"
                "`/сбросить_статистику` - Сброс всего\n"
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
    
    embed.set_footer(text="YAK Clan Stats Bot v3.1")
    
    await inter.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="sync", description="🔄 Синхронизировать команды", guild=discord.Object(GUILD_ID))
async def sync_commands(inter: discord.Interaction):
    if not has_role(inter.user, ADMIN_ROLES):
        return await inter.response.send_message("❌ Нет доступа", ephemeral=True)
    
    try:
        synced = await tree.sync(guild=discord.Object(GUILD_ID))
        
        embed = discord.Embed(
            title="✅ Команды синхронизированы",
            description=f"Синхронизировано команд: **{len(synced)}**",
            color=0x2ecc71,
            timestamp=now()
        )
        
        commands_list = "\n".join([f"• `/{cmd.name}`" for cmd in synced[:15]])
        if len(synced) > 15:
            commands_list += f"\n*...и ещё {len(synced) - 15}*"
        
        embed.add_field(
            name="📋 Синхронизированные команды",
            value=commands_list,
            inline=False
        )
        
        embed.set_footer(text="Команды обновлены")
        
        await log_action(
            inter.guild, inter.user,
            "🔄 Синхронизация команд",
            f"Синхронизировано: {len(synced)} команд"
        )
        
        await inter.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        embed = discord.Embed(
            title="❌ Ошибка синхронизации",
            description=f"```{str(e)}```",
            color=0xe74c3c,
            timestamp=now()
        )
        await inter.response.send_message(embed=embed, ephemeral=True)

# admin_menu command removed — admin panel is posted automatically on startup

@tree.command(name="создать_розыгрыш", description="🎁 Создать розыгрыш", guild=discord.Object(GUILD_ID))
@app_commands.describe(название="Название розыгрыша")
async def create_raffle(inter: discord.Interaction, название: str):
    if not has_role(inter.user, ADMIN_ROLES):
        return await inter.response.send_message("Нет доступа", ephemeral=True)
    
    raffle_id = f"raffle_{int(now().timestamp())}"
    raffles = load_raffles()
    raffle = {
        "id": raffle_id,
        "name": название,
        "active": True,
        "participants": [],
        "winners": [],
        "created_at": now().isoformat(),
        "channel_id": inter.channel_id
    }
    raffles.append(raffle)
    save_raffles(raffles)
    
    embed = discord.Embed(
        title=f"🎁 {название}",
        description="Нажмите кнопку ниже чтобы участвовать",
        color=0xf39c12
    )
    embed.set_footer(text=f"ID: {raffle_id}")
    
    channel = inter.guild.get_channel(RAFFLE_CHANNEL_ID)
    if channel:
        role = inter.guild.get_role(EVERYONE_ROLE_ID)
        mention = role.mention if role else "@everyone"
        await channel.send(mention, embed=embed, view=RaffleView(raffle_id))
        await inter.response.send_message(f"✅ Розыгрыш отправлен в <#{RAFFLE_CHANNEL_ID}>", ephemeral=True)
    else:
        await inter.response.send_message(embed=embed, view=RaffleView(raffle_id))

@tree.command(name="backup", description="💾 Создать бекап текущих данных", guild=discord.Object(GUILD_ID))
async def backup_command(inter: discord.Interaction):
    if not has_role(inter.user, ADMIN_ROLES):
        return await inter.response.send_message("Нет доступа", ephemeral=True)
    
    try:
        backup_time = time.strftime("%Y-%m-%d_%H-%M-%S")
        shutil.copy(DB_STATS, f"backup_stats_{backup_time}.json")
        shutil.copy(DB_CAPTS, f"backup_capts_{backup_time}.json")
        await inter.response.send_message(f"✅ Бекап создан: backup_*_{backup_time}.json", ephemeral=True)
    except Exception as e:
        await inter.response.send_message(f"❌ Ошибка: {str(e)}", ephemeral=True)

@tree.command(name="капт", description="Edit a capt: view, edit players, edit capt", guild=discord.Object(GUILD_ID))
@app_commands.describe(номер="Capt number (1=latest)")
async def edit_capt_cmd(inter: discord.Interaction, номер: int = 1):
    if not has_role(inter.user, ADMIN_ROLES):
        return await inter.response.send_message("No access", ephemeral=True)
    
    capts = load_capts()
    if номер < 1 or номер > len(capts):
        return await inter.response.send_message("Capt not found", ephemeral=True)
    
    capt_idx = -номер
    capt = capts[capt_idx]
    
    # Create view with options to edit capt details or player
    class CaptEditView(discord.ui.View):
        def __init__(self, capt_data, capt_idx):
            super().__init__(timeout=300)
            self.capt = capt_data
            self.idx = capt_idx
        
        @discord.ui.button(label="Edit Capt", style=discord.ButtonStyle.primary, custom_id="edit_capt_details")
        async def edit_capt_details(self, btn_inter: discord.Interaction, button: discord.ui.Button):
            class EditCaptModal(discord.ui.Modal, title="Edit Capt"):
                vs = discord.ui.TextInput(label="Enemy name", default=self.capt.get("vs", ""))
                win = discord.ui.TextInput(label="Result (win/lose)", default="win" if self.capt.get("win") else "lose")
                
                async def on_submit(self, modal_inter: discord.Interaction):
                    self.capt["vs"] = self.vs.value.strip()
                    self.capt["win"] = self.win.value.strip().lower() in ["win", "победа", "в"]
                    save_capts(capts)
                    asyncio.create_task(update_capts_list())
                    await modal_inter.response.send_message("Capt updated", ephemeral=True)
            
            await btn_inter.response.send_modal(EditCaptModal())
        
        @discord.ui.button(label="Edit Player", style=discord.ButtonStyle.secondary, custom_id="edit_player_in_capt")
        async def edit_player_in_capt(self, btn_inter: discord.Interaction, button: discord.ui.Button):
            if not self.capt.get("players"):
                return await btn_inter.response.send_message("No players", ephemeral=True)
            
            # Create select menu for players
            class PlayerSelect(discord.ui.Select):
                def __init__(self, players_list):
                    options = [
                        discord.SelectOption(
                            label=f"{i+1}. {p.get('user_name', 'Unknown')} - {p.get('kills')}k {p.get('damage')}dmg",
                            value=str(i)
                        ) for i, p in enumerate(players_list)
                    ]
                    super().__init__(placeholder="Select player", options=options)
                    self.players = players_list
                
                async def callback(self, select_inter: discord.Interaction):
                    idx = int(self.values[0])
                    player = self.players[idx]
                    
                    class EditPlayerModal(discord.ui.Modal, title="Edit Player"):
                        kills = discord.ui.TextInput(label="Kills", default=str(player.get("kills", 0)))
                        damage = discord.ui.TextInput(label="Damage", default=str(player.get("damage", 0)))
                        
                        async def on_submit(self, edit_inter: discord.Interaction):
                            try:
                                old_k = player.get("kills", 0)
                                old_d = player.get("damage", 0)
                                new_k = int(self.kills.value)
                                new_d = int(self.damage.value)
                                
                                player["kills"] = new_k
                                player["damage"] = new_d
                                
                                # Update stats
                                st = load_stats()
                                uid = str(player["user_id"])
                                if uid in st:
                                    st[uid]["kills"] += (new_k - old_k)
                                    st[uid]["damage"] += (new_d - old_d)
                                    save_stats(st)
                                
                                save_capts(capts)
                                asyncio.create_task(update_capts_list())
                                asyncio.create_task(update_avg_top())
                                asyncio.create_task(update_kills_top())
                                
                                await edit_inter.response.send_message("Player updated", ephemeral=True)
                            except Exception as e:
                                await edit_inter.response.send_message(f"Error: {str(e)}", ephemeral=True)
                    
                    await select_inter.response.send_modal(EditPlayerModal())
            
            view = discord.ui.View()
            view.add_item(PlayerSelect(self.capt.get("players", [])))
            await btn_inter.response.send_message("Select player to edit:", view=view, ephemeral=True)
    
    # Show capt info
    embed = discord.Embed(title=f"Capt #{номер}", color=0x3498db)
    embed.add_field(name="Enemy", value=capt.get("vs", "Unknown"), inline=True)
    embed.add_field(name="Result", value="WIN" if capt.get("win") else "LOSE", inline=True)
    embed.add_field(name="Players", value=str(len(capt.get("players", []))), inline=True)
    
    players_text = ""
    for i, p in enumerate(capt.get("players", []), 1):
        players_text += f"{i}. {p.get('user_name', 'Unknown')} - {p.get('kills')}k {p.get('damage')}dmg\n"
    
    if players_text:
        embed.add_field(name="Players list", value=players_text, inline=False)
    
    await inter.response.send_message(embed=embed, view=CaptEditView(capt, capt_idx), ephemeral=True)

@tree.command(name="конфиг_недельный_отчет", description="🔧 Настроить еженедельный отчет", guild=discord.Object(GUILD_ID))
@app_commands.describe(
    день="День недели (0=пн, 6=вс)",
    час="Час отправки (0-23)"
)
async def config_weekly(inter: discord.Interaction, день: int = 0, час: int = 10):
    if not has_role(inter.user, ADMIN_ROLES):
        return await inter.response.send_message("Нет доступа", ephemeral=True)
    
    cfg = load_weekly_config()
    cfg["day"] = день
    cfg["hour"] = час
    save_weekly_config(cfg)
    
    days = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    await inter.response.send_message(f"✅ Отчет будет отправляться в {days[день % 7]} в {час:02d}:00", ephemeral=True)

# ==================== АВТООБНОВЛЕНИЕ ====================
async def update_avg_top():
    channel = client.get_channel(STATS_AVG_CHANNEL_ID)
    if not channel:
        return

    st = load_stats()
    filtered = {uid: d for uid, d in st.items() if d["games"] >= 3}
    if not filtered:
        return

    users = sorted(filtered.items(), key=lambda x: x[1]["damage"]/x[1]["games"], reverse=True)[:10]

    embed = discord.Embed(
        title="🏆 ТОП-10 СРЕДНЕГО УРОНА",
        color=0x9b59b6,
        timestamp=now()
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

    async for msg in channel.history(limit=50):
        if msg.author.id == client.user.id and msg.embeds:
            if "ТОП-10 СРЕДНЕГО УРОНА" in msg.embeds[0].title:
                try:
                    await msg.edit(embed=embed)
                    return
                except:
                    pass

    try:
        await channel.send(embed=embed)
    except:
        pass

async def update_kills_top():
    channel = client.get_channel(STATS_KILLS_CHANNEL_ID)
    if not channel:
        return

    st = load_stats()
    if not st:
        return

    users = sorted(st.items(), key=lambda x: x[1]["kills"], reverse=True)[:10]

    embed = discord.Embed(
        title="☠️ ТОП-10 ПО КИЛЛАМ",
        color=0xe74c3c,
        timestamp=now()
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

    async for msg in channel.history(limit=50):
        if msg.author.id == client.user.id and msg.embeds:
            if "ТОП-10 ПО КИЛЛАМ" in msg.embeds[0].title:
                try:
                    await msg.edit(embed=embed)
                    return
                except:
                    pass

    try:
        await channel.send(embed=embed)
    except:
        pass

async def update_capts_list():
    channel = client.get_channel(CAPTS_LIST_CHANNEL_ID)
    if not channel:
        return

    view = CaptsListView(channel.guild, "all")
    embed = await view.create_embed()

    async for msg in channel.history(limit=50):
        if msg.author.id == client.user.id and msg.embeds:
            if "История каптов" in msg.embeds[0].title:
                try:
                    await msg.edit(embed=embed, view=view)
                    print("[OK] Capts list updated")
                    return
                except:
                    pass

    try:
        await channel.send(embed=embed, view=view)
        print("[OK] Capts list sent")
    except:
        pass

async def send_weekly_report():
    """Отправить еженедельный отчет"""
    channel = client.get_channel(WEEKLY_REPORT_CHANNEL_ID)
    if not channel:
        return
    
    capts = load_capts()
    st = calculate_stats(capts)
    
    if not st:
        return
    
    embed = discord.Embed(
        title="📊 ЕЖЕНЕДЕЛЬНЫЙ ОТЧЕТ",
        color=0x3498db,
        timestamp=now()
    )
    
    top_avg = sorted(st.items(), key=lambda x: x[1]["damage"]/x[1]["games"] if x[1]["games"] >= 3 else 0, reverse=True)[:5]
    top_kills = sorted(st.items(), key=lambda x: x[1]["kills"], reverse=True)[:5]
    
    desc = ""
    for i, (uid, data) in enumerate(top_avg, 1):
        try:
            member = await channel.guild.fetch_member(int(uid))
            name = member.display_name
        except:
            name = f"Игрок {uid}"
        avg = data["damage"] // data["games"] if data["games"] > 0 else 0
        desc += f"{i}. **{name}** - {avg:,} ср. урона\n"
    
    embed.add_field(name="🏆 ТОП-5 СРЕДНЕГО УРОНА", value=desc or "Нет данных", inline=False)
    
    desc = ""
    for i, (uid, data) in enumerate(top_kills, 1):
        try:
            member = await channel.guild.fetch_member(int(uid))
            name = member.display_name
        except:
            name = f"Игрок {uid}"
        desc += f"{i}. **{name}** - {data['kills']} киллов\n"
    
    embed.add_field(name="☠️ ТОП-5 ПО КИЛЛАМ", value=desc or "Нет данных", inline=False)
    
    try:
        await channel.send(embed=embed)
    except:
        pass

@tasks.loop(hours=1)

async def auto_update():
    await update_avg_top()
    await update_kills_top()
    await update_capts_list()
    print(f"[OK] Auto-update done: {datetime.now().strftime('%H:%M:%S')}")

@tasks.loop(hours=24)
async def weekly_report_task():
    """Отправить еженедельный отчет в заданный день и час"""
    cfg = load_weekly_config()
    if not cfg:
        return
    
    now_dt = datetime.now()
    target_day = cfg.get("day", 0)
    target_hour = cfg.get("hour", 10)
    
    if now_dt.weekday() == target_day and now_dt.hour == target_hour:
        await send_weekly_report()

# ==================== СОБЫТИЯ ====================
@client.event
async def on_ready():
    print(f"[OK] Bot started: {client.user}")
    
    try:
        await tree.sync(guild=discord.Object(GUILD_ID))
        print("[OK] Commands synced")
    except Exception as e:
        print(f"[ERROR] Sync error: {e}")
    
    if not auto_update.is_running():
        auto_update.start()
        print("[OK] Auto-update started")
    
    if not weekly_report_task.is_running():
        weekly_report_task.start()
        print("[OK] Weekly report started")
    # Post admin panel message to ADMIN_CHANNEL_ID on startup (edit existing if present)
    try:
        channel = client.get_channel(ADMIN_CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title="🔧 ПАНЕЛЬ УПРАВЛЕНИЯ ДЛЯ ДОВЕРЕННЫХ ЧЛЕНОВ СЕМЬИ",
                description="Взаимодействие с ботом осуществляется преимущественно через это меню, которое включает 14 кнопок.",
                color=0xe74c3c
            )
            embed.set_image(url="https://images-ext-1.discordapp.net/external/VYxjKWsWfuy15MhjbNSdZTAnAw7ncsq0QzRpea-7fnA/https/i.pinimg.com/736x/e2/6f/ad/e26fadfad4179906f627b7cbc253f559.jpg?format=webp&width=662&height=617")
            embed.add_field(name="🔸 Просмотр всех участников семьи", value="Отображает участников и их активность", inline=False)
            embed.add_field(name="🔸 Добавить участника", value="Внести участника в базу данных", inline=False)
            embed.add_field(name="🔸 Удалить участника", value="Удалить участника из базы данных", inline=False)
            embed.add_field(name="🔸 Корректировать баллы", value="Взаимодействие с панелью баллов", inline=False)
            embed.add_field(name="🔸 Статистика всех", value="Просмотр статистики всех игроков", inline=False)
            embed.add_field(name="🔸 Розыгрыши", value="Розыгрыши призов для членов семьи", inline=False)
            embed.add_field(name="🔸 Теги на капт", value="Отправка упоминаний в канал", inline=False)
            embed.add_field(name="🔸 Синхронизировать", value="Синхронизация команд", inline=False)

            msgs = load_message_map()
            mid = msgs.get('admin')
            if mid:
                try:
                    m = await channel.fetch_message(int(mid))
                    if m and m.author.id == client.user.id:
                        try:
                            await m.edit(embed=embed, view=AdminPanelView())
                        except:
                            pass
                        else:
                            msgs['admin'] = m.id
                            save_message_map(msgs)
                except:
                    pass

            # Fallback: search recent messages and edit the panel if found
            found = False
            async for msg in channel.history(limit=50):
                if msg.author.id == client.user.id and msg.embeds:
                    if "ПАНЕЛЬ УПРАВЛЕНИЯ" in (msg.embeds[0].title or ""):
                        try:
                            await msg.edit(embed=embed, view=AdminPanelView())
                            msgs['admin'] = msg.id
                            save_message_map(msgs)
                            found = True
                            break
                        except:
                            pass

            if not found:
                try:
                    sent = await channel.send(embed=embed, view=AdminPanelView())
                    msgs['admin'] = sent.id
                    save_message_map(msgs)
                except:
                    pass
    except Exception:
        pass

@client.event
async def on_member_remove(member: discord.Member):
    st = load_stats()
    uid = str(member.id)
    
    if uid in st:
        del st[uid]
        save_stats(st)
        
        await log_action(
            member.guild, client.user,
            "👋 Игрок покинул сервер",
            f"{member.mention} ({member.display_name})\nСтатистика удалена"
        )
        
        asyncio.create_task(update_avg_top())
        asyncio.create_task(update_kills_top())

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    for db in [DB_STATS, DB_CAPTS]:
        if not os.path.exists(db):
            with open(db, "w", encoding="utf-8") as f:
                json.dump({} if db == DB_STATS else [], f)
            print(f"📁 Создан {db}")

    client.run(TOKEN)
