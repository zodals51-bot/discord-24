import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, request, jsonify
import threading
import random
import string
import os
import json
import asyncio

# ================= 설정 =================
TOKEN = "" # main.py에 있던 토큰 기준
GUILD_ID = 1326498746933972993  # 서버 ID (필요시 변경)
DATA_FILE = "data.json"

UNVERIFIED_ROLE = "미인증"

# ================= 데이터베이스 관리 =================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"last_uid": 0, "users": {}, "codes": {}}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {"last_uid": 0, "users": {}, "codes": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# ================= 디코 봇 =================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

@bot.event
async def on_ready():
    await tree.sync()
    print(f"{bot.user} 고유번호 봇 실행 완료!")

# 🔑 /인증
@tree.command(name="인증", description="로블록스 연동 인증 코드를 개인 DM으로 발급받습니다.")
async def 인증(interaction: discord.Interaction):
    data = load_data()
    user_id_str = str(interaction.user.id)

    if user_id_str in data["users"]:
        return await interaction.response.send_message("❌ 이미 인증된 계정입니다.", ephemeral=True)

    # 기존 코드 확인 (재시도 시 덮어쓰기)
    code = generate_code()
    data["codes"][code] = user_id_str
    save_data(data)

    try:
        # 개인 DM으로 전송
        await interaction.user.send(
            f"✅ **인증 안내**\n"
            f"로블록스 인증 센터(https://www.roblox.com/ko/games/131467007908121/DBS) 에 접속하여 아래 코드를 입력해주세요:\n\n"
            f"🔑 **인증 코드:** `{code}`"
        )
        await interaction.response.send_message("✅ 개인 DM으로 인증 코드를 성공적으로 전송했습니다! DM을 확인해주세요.", ephemeral=True)
    except discord.Forbidden:
        # DM이 막혀있는 경우
        await interaction.response.send_message("❌ DM을 보낼 수 없습니다. 서버 개인정보 보호 설정에서 '서버 멤버가 보내는 다이렉트 메시지 허용'을 켜주세요.", ephemeral=True)

# 🛠️ /고유번호변경 (관리자 전용)
@tree.command(name="고유번호변경", description="[관리자] 특정 유저의 고유번호를 다른 번호로 강제 변경합니다.")
@app_commands.describe(member="변경할 대상", new_uid="새로운 고유번호 (숫자)")
@app_commands.default_permissions(administrator=True)
async def 고유번호변경(interaction: discord.Interaction, member: discord.Member, new_uid: int):
    data = load_data()
    user_id_str = str(member.id)

    if user_id_str not in data["users"]:
        return await interaction.response.send_message("❌ 인증되지 않은 유저입니다.", ephemeral=True)

    # 고유번호 중복 체크
    for uid, info in data["users"].items():
        if info["uid"] == new_uid:
            return await interaction.response.send_message(f"❌ 이미 다른 유저가 사용 중인 고유번호입니다 ({new_uid}).", ephemeral=True)

    # 변경 진행
    data["users"][user_id_str]["uid"] = new_uid
    save_data(data)

    # 닉네임 업데이트
    info = data["users"][user_id_str]
    nickname = f"{info['uid']}ㆍ{info['job']}ㆍ{info['roblox']}"
    try:
        await member.edit(nick=nickname)
    except Exception as e:
        return await interaction.response.send_message(f"✅ 데이터는 저장되었으나 권한 문제로 닉네임을 변경하지 못했습니다.\n(봇 권한보다 높은 역할이거나 서버 소유자입니다.)", ephemeral=True)

    await interaction.response.send_message(f"✅ {member.mention} 님의 고유번호가 **{new_uid}** (으)로 변경되었습니다.", ephemeral=True)

# 🗑️ /고유번호삭제 (관리자 전용)
@tree.command(name="고유번호삭제", description="[관리자] 특정 유저의 고유번호 및 인증 정보를 초기화합니다.")
@app_commands.describe(member="삭제할 대상")
@app_commands.default_permissions(administrator=True)
async def 고유번호삭제(interaction: discord.Interaction, member: discord.Member):
    data = load_data()
    user_id_str = str(member.id)

    if user_id_str not in data["users"]:
        return await interaction.response.send_message("❌ 인증되지 않은 유저이거나 이미 삭제된 유저입니다.", ephemeral=True)

    # 데이터 삭제
    del data["users"][user_id_str]
    save_data(data)

    # 초기화 진행 (닉네임 초기화 처리, 역할 관리 등)
    try:
        await member.edit(nick=None) # 닉네임 초기화
    except discord.Forbidden:
        pass # 권한 없는경우 무시

    # 미인증 역할이 있으면 다시 부여
    guild = member.guild
    unverified = discord.utils.get(guild.roles, name=UNVERIFIED_ROLE)
    if unverified:
        try:
            await member.add_roles(unverified)
        except:
            pass

    await interaction.response.send_message(f"✅ {member.mention} 님의 고유번호 및 인증 정보가 성공적으로 초기화/삭제 되었습니다.", ephemeral=True)


# ================= 24시간 가동 & 로블록스 통신용 서버 =================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Auth Server Running! (24시간 봇 가동 중)"

@app.route("/verify", methods=["POST"])
def verify():
    try:
        req_data = request.json
        code = req_data.get("code")
        roblox_name = req_data.get("roblox")

        data = load_data()

        if code in data["codes"]:
            user_id = data["codes"][code]
            
            # 발급할 순차적 고유번호
            data["last_uid"] += 1
            new_uid = data["last_uid"]

            # 유저 데이터 저장
            data["users"][user_id] = {
                "uid": new_uid,
                "job": "승객", # 기본 직업
                "roblox": roblox_name
            }
            
            # 사용한 코드 완전 식별/소모 (보안)
            del data["codes"][code]
            save_data(data)

            # 비동기로 디스코드 처리 (닉네임 및 역할 갱신)
            async def process():
                guild = bot.get_guild(GUILD_ID)
                if not guild:
                    return

                member = guild.get_member(int(user_id))
                if not member:
                    return

                # 고유번호ㆍ직업ㆍ로블록스닉네임 형식
                nickname = f"{new_uid}ㆍ승객ㆍ{roblox_name}"

                try:
                    await member.edit(nick=nickname)
                    
                    # 미인증 역할 제거
                    unverified = discord.utils.get(guild.roles, name=UNVERIFIED_ROLE)
                    if unverified and unverified in member.roles:
                        await member.remove_roles(unverified)
                except Exception as e:
                    print("디코 속성 변경 오류:", e)

            bot.loop.create_task(process())

            return jsonify({"status": "success", "uid": new_uid, "job": "승객"})

        return jsonify({"status": "fail", "message": "Invalid code"})

    except Exception as e:
        print("서버 오류:", e)
        return jsonify({"status": "error", "message": str(e)})

# ================= 24시간 봇 가동 (Keep Alive) 및 봇 실행 =================
def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    server = threading.Thread(target=run_flask)
    server.start()

# 24시간 가동 서버 시작
keep_alive()

# 봇 실행 (설정된 TOKEN 변수 사용)
bot.run(TOKEN)