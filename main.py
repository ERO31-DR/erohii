import os
import requests
from flask import Flask, redirect, request, session
from dotenv import load_dotenv
import discord
from discord.ext import commands
import threading

load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI") # Örn: https://proje-adin.onrender.com/callback
BOT_TOKEN = os.getenv("BOT_TOKEN")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", 1537506949577445426))

DISCORD_API = "https://discord.com/api/v10"

app = Flask(__name__)
app.secret_key = os.urandom(24)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

AUTHORIZED_ACCOUNTS = {}

@app.route("/")
def home():
    return "Arrow Toplu Sunucu Çıkış Paneli Aktif ve Çalışıyor!"

@app.route("/login")
def login():
    discord_login_url = (
        f"{DISCORD_API}/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=identify+guilds"
    )
    return redirect(discord_login_url)

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "Yetkilendirme kodu bulunamadı."
        
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    response = requests.post(f"{DISCORD_API}/oauth2/token", data=data, headers=headers)
    token_json = response.json()
    access_token = token_json.get("access_token")
    
    if not access_token:
        return "Discord token alınamadı."
        
    user_resp = requests.get(f"{DISCORD_API}/users/@me", headers={"Authorization": f"Bearer {access_token}"})
    if user_resp.status_code != 200:
        return "Kullanıcı bilgileri alınamadı."
        
    user_data = user_resp.json()
    user_id = user_data.get("id")
    username = user_data.get("username")
    
    AUTHORIZED_ACCOUNTS[user_id] = {
        "username": username,
        "access_token": access_token
    }
    
    return f"<h3>İzin Başarılı, {username}!</h3><p>Discord'a dönerek yönetici komutunu kullanabilirsin. Bu pencereyi kapatabilirsin.</p>"


@bot.event
async def on_ready():
    print(f"Bot aktif: {bot.user.name}")
    try:
        await bot.tree.sync()
        print("Komutlar senkronize edildi.")
    except Exception as e:
        print(e)


@bot.tree.command(name="arrow", description="Arrow hesabı için erişim izni bağlantısı oluşturur.")
async def arrow(interaction: discord.Interaction):
    auth_url = (
        f"{DISCORD_API}/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=identify+guilds"
    )
    
    embed = discord.Embed(
        title="Arrow Hesap Erişim Paneli",
        description=(
            "Tüm sunuculardan çıkış yapabilmek için öncelikle hesaba izin vermelisin.\n\n"
            f"👉 **[Buraya tıklayarak hesap erişim izni ver]({auth_url})**"
        ),
        color=discord.Color.dark_embed()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


class CikisModal(discord.ui.Modal, title="Yönetici Çıkış ve Log Paneli"):
    veda_mesaji = discord.ui.TextInput(
        label="Log Kanalına Yazılacak Veda Mesajı",
        style=discord.TextStyle.paragraph,
        placeholder="Sunuculardan çıkmadan önce log kanalında görünecek mesajı yazın...",
        required=True,
        max_length=1000
    )

    def __init__(self, selected_user_id: str):
        super().__init__()
        self.selected_user_id = selected_user_id

    async def on_submit(self, interaction: discord.Interaction):
        if self.selected_user_id not in AUTHORIZED_ACCOUNTS:
            await interaction.response.send_message("❌ Seçilen hesap veritabanında bulunamadı veya süresi dolmuş.", ephemeral=True)
            return

        acc_data = AUTHORIZED_ACCOUNTS[self.selected_user_id]
        access_token = acc_data["access_token"]
        username = acc_data["username"]
        mesaj = self.veda_mesaji.value

        await interaction.response.send_message(f"🚀 **{username}** adlı hesap için işlem başlatıldı. Sunuculardan çıkılıyor...", ephemeral=True)

        user_headers = {"Authorization": f"Bearer {access_token}"}
        bot_headers = {"Authorization": f"Bot {BOT_TOKEN}"}

        guilds_resp = requests.get(f"{DISCORD_API}/users/@me/guilds", headers=user_headers)
        if guilds_resp.status_code != 200:
            await interaction.followup.send("Kullanıcının sunucuları alınamadı. Token geçersiz olabilir.", ephemeral=True)
            return

        guilds = guilds_resp.json()
        success_count = 0

        for guild in guilds:
            guild_id = guild["id"]
            
            if LOG_CHANNEL_ID:
                msg_payload = {"content": f"**[{username}]** {mesaj} (Çıkış yapılan sunucu: {guild['name']})"}
                requests.post(f"{DISCORD_API}/channels/{LOG_CHANNEL_ID}/messages", headers=bot_headers, json=msg_payload)

            leave_resp = requests.delete(f"{DISCORD_API}/users/@me/guilds/{guild_id}", headers=user_headers)
            if leave_resp.status_code == 204:
                success_count += 1

        del AUTHORIZED_ACCOUNTS[self.selected_user_id]

        await interaction.followup.send(f"✅ İşlem tamamlandı! **{username}** hesabı toplam **{success_count}** sunucudan başarıyla çıkarıldı ve log gönderildi.", ephemeral=True)


class HesapSelectView(discord.ui.View):
    def __init__(self, accounts: dict):
        super().__init__()
        options = []
        for uid, data in accounts.items():
            options.append(discord.SelectOption(label=data["username"], value=uid, description=f"ID: {uid}"))
        self.add_item(HesapSelect(options))

class HesapSelect(discord.ui.Select):
    def __init__(self, options):
        super().__init__(placeholder="Çıkış yapılacak hesabı seçin...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_user_id = self.values[0]
        await interaction.response.send_modal(CikisModal(selected_user_id))


@bot.tree.command(name="cikisyap", description="İzin veren hesapları listeler, yönetici seçip veda mesajını girerek çıkış yapar.")
@discord.app.commands.default_permissions(administrator=True)
async def cikisyap(interaction: discord.Interaction):
    if not AUTHORIZED_ACCOUNTS:
        await interaction.response.send_message("❌ Henüz hesap erişim izni veren kimse yok! Önce `/arrow` ile izin alınmalı.", ephemeral=True)
        return

    view = HesapSelectView(AUTHORIZED_ACCOUNTS)
    await interaction.response.send_message("Aşağıdaki menüden çıkış yapmak istediğin **hesabı seç**:", view=view, ephemeral=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    
    flask_thread = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=port))
    flask_thread.daemon = True
    flask_thread.start()
    
    bot.run(BOT_TOKEN)
