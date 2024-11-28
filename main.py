import json
import requests
import urllib.parse
import time
import os
import re
import base64
from typing import Union

from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi import Response, Cookie, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.responses import RedirectResponse as redirect
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.templating import Jinja2Templates

from cache import cache

max_api_wait_time = 3
max_time = 10
url = "https://yukibbs-server.onrender.com/"
version = "1.0"


def get_info(request):
    global version
    # return json.dumps()
    return json.dumps(
        [
            version,
            os.environ.get("RENDER_EXTERNAL_URL"),
            str(request.scope["headers"]),
            str(request.scope["router"])[39:-2],
        ]
    )


def parse_html_to_json(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')

    # 話題を取得
    if soup.find('h3'):
        topic_html = str(soup.find('h3').decode_contents())
        topic = topic_html.replace('<br>', '\n').replace('<br/>', '\n')[5:]

    messages = []
    for row in soup.find_all('tr')[1:]:  # ヘッダー行をスキップ
        cols = row.find_all('td')
        if len(cols) == 3:
            number = cols[0].get_text()
            name_cell = cols[1]

            # 名前の色を取得
            name_color = None
            name_font = name_cell.find('font', color=True)
            if name_font and not name_font.get_text().startswith('@'):
                name_color = name_font.get('color')

            # IDとその色を取得
            id_match = re.search(r'@[A-Za-z0-9]{7}', name_cell.get_text())
            user_id = id_match.group(0) if id_match else None
            id_color = None
            id_font = name_cell.find('font', string=lambda s: s and '@' in s)
            if id_font:
                id_color = id_font.get('color')

            # 追加テキストを取得
            extra_text = None
            extra_font = name_cell.find_all('font')[-1] if name_cell.find_all('font') else None
            if extra_font and extra_font.get('color', '') == 'magenta':  # 完全一致チェックに変更
                extra_text = extra_font.get_text()

            # 名前を取得（色付きフォントとIDを除いた部分）
            name = name_cell.get_text()
            if user_id:
                name = name.replace(user_id, '').strip()
            if extra_text:
                name = name.replace(extra_text, '').strip()

            messages.append({
                'number': number,
                'name': name,
                'name_color': name_color,
                'user_id': user_id,
                'id_color': id_color,
                'extra_text': extra_text,
                'message': cols[2].get_text().replace('<br>', '\n').replace('<br/>', '\n')
            })

    return {
        'topic': topic,
        'messages': messages
    }


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1000)

template = Jinja2Templates(directory="views").TemplateResponse


@app.get("/", response_class=HTMLResponse)
def home(response: Response, request: Request, yuki: Union[str] = Cookie(None)):
    return redirect("/bbs")


@app.get("/bbs", response_class=HTMLResponse)
def view_index(
    request: Request,
    name: Union[str, None] = "",
    seed: Union[str, None] = "",
    channel: Union[str, None] = "main",
    verify: Union[str, None] = "false",
    yuki: Union[str] = Cookie(None),
):
    # res = HTMLResponse(requests.get(fr"{url}bbs?name={urllib.parse.quote(name)}&seed={urllib.parse.quote(seed)}&channel={urllib.parse.quote(channel)}&verify={urllib.parse.quote(verify)}",cookies={"yuki":"True"}).text)
    return template("bbs.html", {"request": request})
    # return res


@app.get("/bbs/info", response_class=HTMLResponse)
def view_info(
    request: Request,
    name: Union[str, None] = "",
    seed: Union[str, None] = "",
    channel: Union[str, None] = "main",
    verify: Union[str, None] = "false",
    yuki: Union[str] = Cookie(None),
):
    res = HTMLResponse(requests.get(rf"{url}bbs/info").text)
    return res


@cache(seconds=5)
def bbsapi_cached(verify, channel):
    return requests.get(
        rf"{url}bbs/api?t={urllib.parse.quote(str(int(time.time() * 1000)))}&verify={urllib.parse.quote(verify)}&channel={urllib.parse.quote(channel)}",
        cookies={"yuki": "True"},
    ).text


@app.get("/bbs/api", response_class=HTMLResponse)
def view_bbs(
    request: Request,
    t: str,
    channel: Union[str, None] = "main",
    verify: Union[str, None] = "false",
):
    html_content = bbsapi_cached(verify, channel)
    json_data = parse_html_to_json(html_content)
    return json.dumps(json_data, ensure_ascii=False)


@app.post("/bbs/result")
async def write_bbs(request: Request):
    body = await request.json()
    message = base64.b64decode(body['message']).decode("utf-8")
    message = message.replace('\n', '<br>')
    name = body.get('name', '')
    seed = body.get('seed', '')
    channel = body.get('channel', 'main')
    verify = body.get('verify', 'false')

    t = requests.get(
        rf"{url}bbs/result?name={urllib.parse.quote(name)}&message={urllib.parse.quote(message)}&seed={urllib.parse.quote(seed)}&channel={urllib.parse.quote(channel)}&verify={urllib.parse.quote(verify)}&info={urllib.parse.quote(get_info(request))}",
        cookies={"yuki": "True"},
        allow_redirects=False,
    )

    return HTMLResponse(t.text)


@cache(seconds=30)
def how_cached():
    return requests.get(rf"{url}bbs/how").text


@app.get("/bbs/how", response_class=PlainTextResponse)
def view_commonds(request: Request, yuki: Union[str] = Cookie(None)):
    return how_cached()


@app.get("/load_instance")
def reload():
    global url
    url = requests.get(
        r"https://raw.githubusercontent.com/mochidukiyukimi/yuki-youtube-instance/main/instance.txt"
    ).text.rstrip()
