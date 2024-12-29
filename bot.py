import discord
from discord.ext import commands
from discord.ui import Button, View
import config

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Укажите ID голосового канала, который будет триггером
TRIGGER_VOICE_CHANNEL_ID = config.Post_Channel  

# Словарь для хранения данных о категориях
categories_data = {}


class CategoryManager:
    def __init__(self, creator, category, text_channel, voice_channel):
        self.creator = creator
        self.category = category
        self.text_channel = text_channel
        self.voice_channel = voice_channel
        self.admins = [creator]


@bot.event
async def on_ready():
    print(f"Бот {bot.user} запущен!")


@bot.event
async def on_voice_state_update(member, before, after):
    guild = member.guild

    # Если пользователь заходит в триггер-канал
    if after.channel and after.channel.id == TRIGGER_VOICE_CHANNEL_ID:
        # Проверяем, есть ли у пользователя уже созданная категория
        if member.id in categories_data:
            # Удаляем старую категорию и связанные каналы
            category_manager = categories_data[member.id]
            for channel in category_manager.category.channels:
                await channel.delete()
            await category_manager.category.delete()
            del categories_data[member.id]

        def_role = discord.utils.get(guild.roles, name="ARMATURA") 

        category = await guild.create_category_channel(
            name=f"Приватная комната {member.display_name}",
            overwrites={
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                def_role: discord.PermissionOverwrite(view_channel=False),
                member: discord.PermissionOverwrite(view_channel=True),
            },
            position=0
        )

        # Создание текстового канала для управления
        text_channel = await category.create_text_channel("Управление категорией")

        # Создание голосового канала
        voice_channel = await category.create_voice_channel(f"Голосовой {member.display_name}")

        # Перемещение пользователя в созданный голосовой канал
        if member.voice:
            await member.move_to(voice_channel)

        # Сохранение данных
        categories_data[member.id] = CategoryManager(member, category, text_channel, voice_channel)

        # Отправка меню управления в текстовый канал
        await send_control_menu(text_channel, member)

    if before.channel:
        category_manager = categories_data.get(member.id)
        if category_manager and category_manager.voice_channel == before.channel:
            # Проверяем, остался ли кто-либо в голосовом канале
            if len(category_manager.voice_channel.members) == 0:
                try:
                    for channel in category_manager.category.channels:
                        if channel:
                            await channel.delete()

                    if category_manager.category:
                        await category_manager.category.delete()

                    del categories_data[member.id]
                except discord.errors.NotFound:
                    print("tip")


async def send_control_menu(channel, creator):
    # Кнопки управления
    class ControlView(View):
        def __init__(self, guild):
            super().__init__(timeout=None)
            self.guild = guild  # Сохраняем гильдию для использования в методах

        @discord.ui.button(label="Изменить название категории", style=discord.ButtonStyle.primary)
        async def rename_category(self, interaction: discord.Interaction, button: Button):
            if interaction.user != creator:
                await interaction.response.send_message("Только создатель может управлять этой категорией.", ephemeral=True)
                return

            await interaction.response.send_message("Введите новое название для категории:", ephemeral=True)

            def check(m):
                return m.author == creator and m.channel == channel

            msg = await bot.wait_for("message", check=check)
            category_manager = categories_data.get(creator.id)
            if category_manager:
                await category_manager.category.edit(name=msg.content)
                await interaction.followup.send(f"Название категории изменено на: {msg.content}", ephemeral=True)

        @discord.ui.button(label="Изменить название голосового канала", style=discord.ButtonStyle.primary)
        async def rename_voice_channel(self, interaction: discord.Interaction, button: Button):
            if interaction.user != creator:
                await interaction.response.send_message("Только создатель может управлять этой категорией.", ephemeral=True)
                return

            await interaction.response.send_message("Введите новое название для голосового канала:", ephemeral=True)

            def check(m):
                return m.author == creator and m.channel == channel

            msg = await bot.wait_for("message", check=check)
            category_manager = categories_data.get(creator.id)
            if category_manager:
                await category_manager.voice_channel.edit(name=msg.content)
                await interaction.followup.send(f"Название голосового канала изменено на: {msg.content}", ephemeral=True)

        @discord.ui.button(label="Исключить участника", style=discord.ButtonStyle.danger)
        async def kick_member(self, interaction: discord.Interaction, button: Button):
            if interaction.user != creator:
                await interaction.response.send_message("Только создатель может управлять этой категорией.", ephemeral=True)
                return

            category_manager = categories_data.get(creator.id)
            if not category_manager:
                return

            members = category_manager.voice_channel.members
            if not members:
                await interaction.response.send_message("Никого нет в голосовом канале.", ephemeral=True)
                return

            # Составляем список участников с номерами
            member_list = [f"{index + 1} - {member.display_name}" for index, member in enumerate(members)]
            member_numbers = {str(index + 1): member.id for index, member in enumerate(members)}

            # Отправляем список участников с номерами
            await interaction.response.send_message(
                f"Выберите участника для исключения, отправив его номер:\n" + "\n".join(member_list),
                ephemeral=True
            )

            def check(m):
                return m.author == interaction.user and m.channel == channel

            # Ожидаем ввод номера участника
            msg = await bot.wait_for("message", check=check)

            # Проверяем, что введен правильный номер
            if msg.content.isdigit() and msg.content in member_numbers:
                member_id = member_numbers[msg.content]
                member_to_kick = discord.utils.get(self.guild.members, id=member_id)

                if member_to_kick:
                    # Исключаем участника из канала
                    await category_manager.voice_channel.set_permissions(member_to_kick, view_channel=False, connect=False)
                    await member_to_kick.move_to(None)  # Отключаем его от голосового канала
                    await interaction.followup.send(f"Участник {member_to_kick.display_name} исключен из голосового канала.", ephemeral=True)
                else:
                    await interaction.followup.send("Не удалось найти участника для исключения.", ephemeral=True)
            else:
                await interaction.followup.send("Номер участника неверен.", ephemeral=True)

        @discord.ui.button(label="Открыть голосовой канал", style=discord.ButtonStyle.success)
        async def open_voice_channel(self, interaction: discord.Interaction, button: Button):
            if interaction.user != creator:
                await interaction.response.send_message("Только создатель может управлять этой категорией.", ephemeral=True)
                return

            category_manager = categories_data.get(creator.id)
            if category_manager:
                await category_manager.category.set_permissions(interaction.guild.default_role, view_channel=True)
                await category_manager.voice_channel.set_permissions(interaction.guild.default_role, connect=True, view_channel=True)
                await interaction.response.send_message("Голосовой канал открыт для всех.", ephemeral=True)

        @discord.ui.button(label="Закрыть голосовой канал", style=discord.ButtonStyle.danger)
        async def close_voice_channel(self, interaction: discord.Interaction, button: Button):
            if interaction.user != creator:
                await interaction.response.send_message("Только создатель может управлять этой категорией.", ephemeral=True)
                return

            category_manager = categories_data.get(creator.id)
            if category_manager:
                await category_manager.category.set_permissions(interaction.guild.default_role, view_channel=False)
                await category_manager.voice_channel.set_permissions(interaction.guild.default_role, connect=False, view_channel=False)
                await interaction.response.send_message("Голосовой канал закрыт для всех.", ephemeral=True)

    # Отправка меню управления в текстовый канал
    await channel.send(f"{creator.mention}, используйте меню ниже для управления категорией:", view=ControlView(channel.guild))


bot.run(config.TOKEN +'-tbc2a5XwoRLO-kbkcSNq7mauLkRcw2I')
