import os
import discord
from discord.ext import commands
from discord import app_commands
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Using Groq API (which is free and compatible with OpenAI client)
ai_client = AsyncOpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

class TicketBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())

    async def setup_hook(self):
        await self.tree.sync()
        print(f"Synced slash commands for {self.user}")

bot = TicketBot()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Closing ticket in 5 seconds...", ephemeral=True)
        await discord.utils.sleep_until(discord.utils.utcnow() + discord.utils.timedelta(seconds=5))
        await interaction.channel.delete()

@bot.tree.command(name="ticket", description="Create a new support ticket")
async def create_ticket(interaction: discord.Interaction, issue: str):
    guild = interaction.guild
    # You might want to get the category from env or config
    # category = discord.utils.get(guild.categories, id=int(os.getenv("TICKET_CATEGORY_ID")))
    
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    
    channel_name = f"ticket-{interaction.user.name}"
    ticket_channel = await guild.create_text_channel(
        channel_name, 
        overwrites=overwrites,
        # category=category 
    )
    
    await interaction.response.send_message(f"Ticket created: {ticket_channel.mention}", ephemeral=True)
    
    view = TicketView()
    await ticket_channel.send(f"Hello {interaction.user.mention}! How can we help you today with: **{issue}**?", view=view)

@bot.event
async def on_message(message: discord.Message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return
        
    # Check if we are in a ticket channel (very basic check)
    if message.channel.name.startswith("ticket-"):
        # We can add an indicator that the bot is thinking
        async with message.channel.typing():
            try:
                # Query Groq API
                response = await ai_client.chat.completions.create(
                    model="llama-3.1-70b-versatile", # Free and very smart model
                    messages=[
                        {"role": "system", "content": "You are a helpful support assistant resolving user issues in a Discord ticket. Answer in the same language the user speaks (e.g. Russian)."},
                        {"role": "user", "content": message.content}
                    ],
                    max_tokens=1000
                )
                
                reply = response.choices[0].message.content
                await message.channel.send(reply)
            except Exception as e:
                await message.channel.send(f"An error occurred while contacting AI: {str(e)}")
                
    await bot.process_commands(message)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("Please set your DISCORD_TOKEN in the .env file")
    else:
        bot.run(DISCORD_TOKEN)
