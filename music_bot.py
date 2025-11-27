import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
from dotenv import load_dotenv

# --- Configuration ---
# 1. Load token from .env file
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN") 
COMMAND_PREFIX = '/'

# Define intents
intents = discord.Intents.default()
intents.message_content = True 

# Initialize the Bot
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

# --- FFMPEG and YTDL Configuration ---
# FFMPEG options to re-establish connection on stream interruptions (crucial for YouTube streams)
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn' # -vn means no video
}

# YTDL options for extracting audio information
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'nocheckcertificate': True,
    # 🚨 FIX FOR YOUTUBE AUTHENTICATION ERROR 🚨
    # This tells yt-dlp to use cookies from a file named 'cookies.txt'
    'cookiefile': 'cookies.txt', 
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

# Create a YTDL object using the installed yt-dlp library
ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

# Custom class to handle audio source extraction asynchronously
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.uploader = data.get('uploader')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        
        # This function runs the blocking yt-dlp operation in a separate thread
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # Take first item from a playlist or search result
            data = data['entries'][0]

        # The actual stream URL for FFMPEG to play
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        
        # Create the audio source object
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)

# --- Bot Events ---

@bot.event
async def on_ready():
    """Confirms the bot has logged in successfully."""
    print('----------------------------------')
    print(f'Bot Logged in as: {bot.user.name}')
    print(f'ID: {bot.user.id}')
    print('----------------------------------')
    await bot.change_presence(activity=discord.Game(name=f'{COMMAND_PREFIX}help for commands'))


# --- Core Commands ---

@bot.command(name='join', aliases=['connect'], help='Tells the bot to join the voice channel')
async def join(ctx):
    """Joins the user's voice channel."""
    if not ctx.author.voice:
        return await ctx.send(f"{ctx.author.name}, you are not connected to a voice channel.")

    channel = ctx.author.voice.channel

    if ctx.voice_client is not None:
        await ctx.voice_client.move_to(channel)
        return

    await channel.connect()
    await ctx.send(f"Connected to **{channel.name}**!")


@bot.command(name='leave', aliases=['disconnect', 'stop'], help='Tells the bot to leave the voice channel and stop playback')
async def leave(ctx):
    """Disconnects the bot from the voice channel."""
    if ctx.voice_client:
        # Stop any currently playing audio
        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            
        await ctx.voice_client.disconnect()
        await ctx.send("Disconnected.")
    else:
        await ctx.send("I'm not in a voice channel.")


@bot.command(name='play', help='Plays audio from a specified URL or search query')
async def play(ctx, *, query):
    """Plays music from a URL or search query."""
    # 1. Ensure the bot is connected
    if not ctx.voice_client:
        try:
            # Attempt to join the user's channel automatically
            await join(ctx)
        except Exception:
            return await ctx.send("I need to be in a voice channel to play music. Use `!join` first.")
    
    # 2. Check for current playback (Basic, no queueing implemented yet)
    if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
        return await ctx.send("I am currently playing/paused. Please use `/stop` before playing a new song.")

    try:
        # 3. Use the corrected 'typing' context manager
        async with ctx.typing():
            # Get the audio source from yt-dlp
            player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
        
        # 4. Start playing the audio
        ctx.voice_client.play(player, after=lambda e: print(f'Player error: {e}') if e else None)
        
        await ctx.send(f'🎶 Now playing: **{player.title}** by *{player.uploader}*')

    except Exception as e:
        print(f"Error during play command: {e}")
        await ctx.send("Sorry, I could not find or play that song. Check your URL or search term.")


@bot.command(name='pause', help='Pauses the currently playing song')
async def pause(ctx):
    """Pauses the currently playing song."""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Paused.")
    else:
        await ctx.send("I am not currently playing any audio.")


@bot.command(name='resume', help='Resumes a paused song')
async def resume(ctx):
    """Resumes a paused song."""
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Resumed.")
    else:
        await ctx.send("I am not paused.")


# --- Run the Bot ---

if __name__ == '__main__':
    # Checking if the token was loaded from the environment
    if TOKEN is None:
        print("\n!!! ERROR: DISCORD_TOKEN environment variable not found. Check your .env file or environment settings. !!!\n")
    else:
        try:
            bot.run(TOKEN)
        except discord.LoginFailure:
            print("\n!!! ERROR: Invalid token provided. Please check your DISCORD_TOKEN environment variable. !!!\n")
        except Exception as e:
            print(f"\n!!! An unexpected error occurred: {e} !!!\n")
