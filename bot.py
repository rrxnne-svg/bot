import discord
from discord.ext import commands
import asyncio

# Настройки

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = 1430087808177147997
IMAGE_URL = ‘https://pin.it/5h3NCblx1’  # URL картинки
MESSAGE_TEXT = ‘все пока от юкича спасибо за все особенно лакерио роме рину я ухажууууу дасвидание’
MESSAGE_COUNT = 15  # Количество сообщений
DELAY = 1  # Задержка в секундах между сообщениями

# Создаем бота с интентами

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=’!’, intents=intents)

@bot.event
async def on_ready():
print(f’Бот {bot.user} успешно запущен!’)
# Получаем канал по ID
channel = bot.get_channel(CHANNEL_ID)

if channel is None:
    print(f'Канал с ID {CHANNEL_ID} не найден!')
    return

print(f'Начинаю отправку сообщений в канал: {channel.name}')

# Отправляем 15 сообщений с задержкой 1 секунда
for i in range(MESSAGE_COUNT):
    try:
        # Создаем embed с картинкой
        embed = discord.Embed(description=MESSAGE_TEXT)
        embed.set_image(url=IMAGE_URL)
        
        await channel.send(embed=embed)
        print(f'Отправлено сообщение {i + 1}/{MESSAGE_COUNT}')
        
        # Ждем 1 секунду перед следующим сообщением (кроме последнего)
        if i < MESSAGE_COUNT - 1:
            await asyncio.sleep(DELAY)
    except Exception as e:
        print(f'Ошибка при отправке сообщения {i + 1}: {e}')

print('Все сообщения отправлены! Бот завершает работу.')
await bot.close()

# Запускаем бота

bot.run(TOKEN)