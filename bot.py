import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
import youtube_dl
from discord.ui import View, Button, Modal, TextInput, Select

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

ytdl_format_options = {
    'format': 'bestaudio/best',
    'quiet': True,
    'noplaylist': True,
    'extract_flat': False
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)
music_queue = []
current_player = None
current_controller = None
looping = False
volume_level = 0.5

class LinkModal(Modal, title="➕ เพิ่มลิงก์หรือชื่อเพลง"):
    link_input = TextInput(label="ชื่อเพลงหรือลิงก์ YouTube", placeholder="https://youtube.com/... หรือชื่อเพลง", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        global current_controller
        if interaction.user.voice is None:
            return await interaction.response.send_message("❌ เข้าห้องเสียงก่อนนะ", ephemeral=True)

        current_controller = interaction.user.id
        url = self.link_input.value
        music_queue.append(url)

        if not interaction.guild.voice_client:
            vc = await interaction.user.voice.channel.connect()
            await play_next(interaction.guild)

        await interaction.response.send_message(f"✅ เพิ่มเพลงแล้ว: {url}", ephemeral=True)

class VolumeModal(Modal, title="🔊 ปรับเสียง 1-100%"):
    vol_input = TextInput(label="ระดับเสียง (%)", placeholder="เช่น 50", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        global volume_level
        try:
            vol = int(self.vol_input.value)
            if 1 <= vol <= 100:
                volume_level = vol / 100
                vc = interaction.guild.voice_client
                if vc and vc.source:
                    vc.source.volume = volume_level
                await interaction.response.send_message(f"✅ ปรับเสียงเป็น {vol}%", ephemeral=True)
            else:
                raise ValueError
        except:
            await interaction.response.send_message("❌ ใส่ตัวเลข 1-100 เท่านั้น", ephemeral=True)

class QueueDropdown(discord.ui.Select):
    def __init__(self, placeholder="เลือกเพลงจากคิว"):
        super().__init__(
            placeholder=placeholder,
            options=[],
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        global music_queue
        if interaction.user.id != current_controller:
            return await interaction.response.send_message("❌ คุณไม่ใช่ผู้ควบคุม", ephemeral=True)
        index = self.options.index(next(o for o in self.options if o.value == self.values[0]))
        song = music_queue.pop(index)
        music_queue.insert(0, song)
        await interaction.response.send_message(f"✅ ย้ายเพลง {song} มาเล่นถัดไปแล้ว", ephemeral=True)

class MusicControlView(View):
    @discord.ui.button(label="▶️/⏸️", style=discord.ButtonStyle.primary)
    async def play_pause(self, interaction: discord.Interaction, button: Button):
        vc = interaction.guild.voice_client
        if vc:
            if vc.is_playing(): vc.pause()
            elif vc.is_paused(): vc.resume()
        await interaction.response.defer()

    @discord.ui.button(label="➕ เพิ่มเพลง", style=discord.ButtonStyle.success)
    async def add_song(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(LinkModal())

    @discord.ui.button(label="🔊 ปรับเสียง", style=discord.ButtonStyle.secondary)
    async def adjust_volume(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(VolumeModal())

    @discord.ui.button(label="🔁 loop", style=discord.ButtonStyle.secondary)
    async def toggle_loop(self, interaction: discord.Interaction, button: Button):
        global looping
        if interaction.user.id != current_controller:
            return await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ควบคุม", ephemeral=True)
        looping = not looping
        await interaction.response.send_message(f"Loop {'เปิด' if looping else 'ปิด'} แล้ว", ephemeral=True)

    @discord.ui.button(label="👑 เปลี่ยนผู้ควบคุม", style=discord.ButtonStyle.danger)
    async def change_controller(self, interaction: discord.Interaction, button: Button):
        class ControllerModal(Modal, title="👑 ใส่ ID ผู้ใช้คนใหม่"):
            user_input = TextInput(label="User ID", placeholder="ใส่เฉพาะตัวเลข")

            async def on_submit(self2, interaction2):
                global current_controller
                if interaction.user.id != current_controller:
                    return await interaction2.response.send_message("❌ คุณไม่มีสิทธิ์เปลี่ยนผู้ควบคุม", ephemeral=True)
                try:
                    new_id = int(self2.user_input.value)
                    current_controller = new_id
                    await interaction2.response.send_message("✅ เปลี่ยนผู้ควบคุมแล้ว", ephemeral=True)
                except:
                    await interaction2.response.send_message("❌ ใส่ ID ไม่ถูกต้อง", ephemeral=True)

        await interaction.response.send_modal(ControllerModal())

    @discord.ui.select(cls=QueueDropdown)
    async def show_queue(self, select, interaction: discord.Interaction):
        pass

async def play_next(guild):
    global current_player
    if not music_queue:
        await guild.voice_client.disconnect()
        return
    url = music_queue[0]
    data = ytdl.extract_info(url, download=False)
    audio_url = data['url']
    source = await discord.FFmpegOpusAudio.from_probe(audio_url, method="fallback")
    source.volume = volume_level
    current_player = source
    guild.voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(guild), bot.loop) if not looping else guild.voice_client.play(source))

@bot.tree.command(name="setup_music", description="🎵 ตั้งค่าควบคุมเพลงก่อนใช้งาน")
async def setup_music(interaction: discord.Interaction):
    embed = discord.Embed(title="🎶 แผงควบคุมเพลง",
                          description=f"🌊 ตอนนี้ยังไม่มีเพลง\n\n👑 ควบคุมโดย: <@{interaction.user.id}>",
                          color=discord.Color.green())
    await interaction.channel.send(embed=embed, view=MusicControlView())
    await interaction.response.send_message("✅ ส่งแผงควบคุมเพลงแล้ว", ephemeral=True)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user}")

bot.run(os.environ["TOKEN"])
