import os
import json
import asyncio
import datetime
import discord
from discord.ext import commands
from discord import app_commands
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

ai_client = AsyncOpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

CONFIG_FILE = "config.json"

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"ticket_types": []}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

# ----------------- VIEWS -----------------

class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="Закрыть тикет", style=discord.ButtonStyle.red, custom_id="ticket_control:close", emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Тикет будет закрыт через 5 секунд...", ephemeral=True)
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except Exception as e:
            try:
                await interaction.channel.send(f"⚠️ **Ошибка при удалении канала:**\nУ бота нет прав `Управлять каналами` (Manage Channels) на этом сервере или в этой категории.\nТехническая ошибка: `{e}`")
            except:
                pass

class TicketSelect(discord.ui.Select):
    def __init__(self):
        config = load_config()
        types = config.get("ticket_types", [])
        
        options = []
        for t in types:
            emoji = t.get("emoji")
            if isinstance(emoji, str):
                emoji = emoji.strip()
                if not emoji or emoji.lower() == "none" or emoji == "null":
                    emoji = None

            desc = t.get("description", "")
            if isinstance(desc, str):
                desc = desc.strip() or None

            # Some users accidentally type text instead of an emoji, which crashes Discord API.
            # We wrap SelectOption in try/except, but unfortunately discord.py doesn't catch it until send().
            # So we just pass the sanitized emoji.
            try:
                opt = discord.SelectOption(
                    label=t["label"][:100], 
                    value=t["label"][:100],
                    description=desc[:100] if desc else None,
                    emoji=emoji
                )
                options.append(opt)
            except:
                opt = discord.SelectOption(
                    label=t["label"][:100], 
                    value=t["label"][:100],
                    description=desc[:100] if desc else None,
                    emoji=None
                )
                options.append(opt)
                
        if not options:
            options = [discord.SelectOption(label="Нет доступных категорий", value="none")]
            
        super().__init__(
            custom_id="ticket_panel:select",
            placeholder="Выберите категорию обращения",
            min_values=1, 
            max_values=1, 
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            return await interaction.response.send_message("Категории не настроены.", ephemeral=True)
            
        category_name = self.values[0]
        guild = interaction.guild
        
        # Checking if user already has a ticket
        existing_channel = discord.utils.get(guild.channels, name=f"ticket-{interaction.user.name.lower()}")
        if existing_channel:
            return await interaction.response.send_message(f"У вас уже есть открытый тикет: {existing_channel.mention}", ephemeral=True)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        
        channel_name = f"ticket-{interaction.user.name}"
        
        config = load_config()
        category_id = config.get("ticket_category_id")
        target_category = None
        if category_id:
            target_category = discord.utils.get(guild.categories, id=category_id)
            
        try:
            ticket_channel = await guild.create_text_channel(
                channel_name,
                category=target_category,
                overwrites=overwrites,
                topic=f"Тикет от {interaction.user} | Категория: {category_name}"
            )
        except discord.Forbidden:
            return await interaction.response.send_message("У бота нет прав на создание каналов.", ephemeral=True)
        
        await interaction.response.send_message(f"Ваш тикет успешно создан: {ticket_channel.mention}", ephemeral=True)
        
        embed = discord.Embed(
            title=f"Тикет: {category_name}",
            description=f"Привет! Опишите вашу проблему, и наш AI-помощник постарается вам помочь.",
            color=discord.Color.green()
        )
        await ticket_channel.send(embed=embed, view=TicketControlView())

class TicketSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

# ----------------- BOT CORE -----------------

class TicketBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # ОБЯЗАТЕЛЬНО для чтения текста сообщений
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Add persistent views so they work after bot restarts
        self.add_view(TicketSelectView())
        self.add_view(TicketControlView())
        await self.tree.sync()
        print(f"Synced slash commands for {self.user}")

bot = TicketBot()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

# ----------------- COMMANDS -----------------

@bot.tree.command(name="setup_panel", description="Отправить панель создания тикетов (Embed + Select)")
@app_commands.checks.has_permissions(administrator=True)
async def setup_panel(interaction: discord.Interaction, title: str = "Поддержка", description: str = "Выберите нужную категорию в меню ниже, чтобы создать тикет."):
    embed = discord.Embed(title=title, description=description, color=discord.Color.blurple())
    view = TicketSelectView()
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("Панель успешно отправлена!", ephemeral=True)

@bot.tree.command(name="add_ticket_type", description="Добавить новую категорию тикетов в выпадающее меню")
@app_commands.checks.has_permissions(administrator=True)
async def add_ticket_type(interaction: discord.Interaction, label: str, description: str = "", emoji: str = ""):
    config = load_config()
    types = config.get("ticket_types", [])
    
    # Check if exists
    for t in types:
        if t["label"].lower() == label.lower():
            return await interaction.response.send_message("Такая категория уже существует!", ephemeral=True)
            
    new_type = {"label": label, "description": description, "emoji": emoji}
    types.append(new_type)
    config["ticket_types"] = types
    save_config(config)
    
    await interaction.response.send_message(f"Категория `{label}` добавлена! Пересоздайте панель через /setup_panel, чтобы изменения вступили в силу.", ephemeral=True)

@bot.tree.command(name="remove_ticket_type", description="Удалить категорию тикетов из выпадающего меню")
@app_commands.checks.has_permissions(administrator=True)
async def remove_ticket_type(interaction: discord.Interaction, label: str):
    config = load_config()
    types = config.get("ticket_types", [])
    
    new_types = [t for t in types if t["label"].lower() != label.lower()]
    
    if len(types) == len(new_types):
        return await interaction.response.send_message("Категория не найдена.", ephemeral=True)
        
    config["ticket_types"] = new_types
    save_config(config)
    
    await interaction.response.send_message(f"Категория `{label}` удалена! Пересоздайте панель через /setup_panel, чтобы изменения вступили в силу.", ephemeral=True)

@bot.tree.command(name="set_ticket_category", description="Указать категорию Discord, где будут создаваться новые тикеты")
@app_commands.checks.has_permissions(administrator=True)
async def set_ticket_category(interaction: discord.Interaction, category: discord.CategoryChannel):
    config = load_config()
    config["ticket_category_id"] = category.id
    save_config(config)
    await interaction.response.send_message(f"✅ Тикеты теперь будут создаваться в категории: **{category.name}**", ephemeral=True)

@bot.tree.command(name="toggle_ai", description="Включить или выключить авто-ответы ИИ в тикетах")
@app_commands.checks.has_permissions(administrator=True)
async def toggle_ai(interaction: discord.Interaction):
    config = load_config()
    current_state = config.get("ai_enabled", True)
    config["ai_enabled"] = not current_state
    save_config(config)
    
    status = "включены ✅" if not current_state else "отключены ❌"
    await interaction.response.send_message(f"Авто-ответы ИИ теперь **{status}**.", ephemeral=True)

# ----------------- AI LISTENER -----------------

@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return
        
    # Check if we are in a ticket channel (very basic check)
    if message.channel.name.startswith("ticket-"):
        async with message.channel.typing():
            try:
                
                config = load_config()
                if not config.get("ai_enabled", True):
                    return  # ИИ отключен

                # Получаем историю сообщений (последние 10)
                messages_history = [msg async for msg in message.channel.history(limit=10)]
                messages_history.reverse() # Старые сначала, новые в конце
                
                history_text = ""
                for msg in messages_history[:-1]:
                    # Берём текст из content или clean_content
                    text = (msg.clean_content or msg.content or "").replace("@", "").strip()
                    if not text:
                        continue
                    if "an error occurred" in text.lower() or "ваш тикет создан" in text.lower() or "тикет будет закрыт" in text.lower():
                        continue
                    speaker = "Бот" if msg.author == bot.user else "Пользователь"
                    history_text += f"{speaker}: {text}\n"
                        
                last_msg = (message.clean_content or message.content or "").replace("@", "").strip()
                
                if not last_msg:
                    return  # Нечего обрабатывать (пустое сообщение, картинка и т.д.)
                
                prompt = (
                    "Ты — Discord-бот поддержки. Отвечай ТОЛЬКО на русском языке.\n"
                    "Твоя задача — помочь пользователю с его вопросом.\n"
                    "Правила:\n"
                    "- Отвечай коротко (1-3 предложения)\n"
                    "- Если пользователь описал проблему, задай уточняющий вопрос\n"
                    "- Если пользователь здоровается, поздоровайся ОДИН раз и спроси чем помочь\n"
                    "- Если ты уже здоровался в истории, НЕ здоровайся снова\n"
                    "- Отвечай строго на последнее сообщение пользователя\n"
                    "- ЕСЛИ ПОЛЬЗОВАТЕЛЬ ПРОСИТ ЗАКРЫТЬ ТИКЕТ, напиши ровно одну фразу: [CLOSE_TICKET]\n\n"
                )
                
                if history_text:
                    prompt += f"Предыдущие сообщения:\n{history_text}\n"
                
                prompt += f"Пользователь: {last_msg}\nТы:"
                
                api_messages = [{"role": "user", "content": prompt}]

                model_name = os.getenv("GROQ_MODEL", "qwen/qwen3.6-27b")
                response = await ai_client.chat.completions.create(
                    model=model_name,
                    messages=api_messages,
                    max_tokens=500,
                    temperature=0.5
                )
                
                reply = response.choices[0].message.content
                # Последняя линия обороны: вырезаем любые упоминания из ответа
                import re
                reply = re.sub(r'<@!?\d+>', '', reply).strip()
                reply = reply.replace("@", "").strip()
                
                if "[CLOSE_TICKET]" in reply.upper() or "CLOSE_TICKET" in reply.upper():
                    await message.channel.send("Понял вас! Тикет будет закрыт через 5 секунд...", allowed_mentions=discord.AllowedMentions.none())
                    await asyncio.sleep(5)
                    try:
                        await message.channel.delete()
                    except:
                        pass
                    return
                
                if reply:
                    await message.channel.send(reply, allowed_mentions=discord.AllowedMentions.none())
            except Exception as e:
                await message.channel.send(f"Ошибка ИИ: {str(e)}", allowed_mentions=discord.AllowedMentions.none())
                
    await bot.process_commands(message)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("Please set your DISCORD_TOKEN in the .env file")
    else:
        bot.run(DISCORD_TOKEN)
