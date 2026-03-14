## UIDCardRender

---

### 本地部署
```bash
uv venv --python 3.12
```
本地使用的依赖略有不同：
打开 `requiurements.txt`，改成：
```py
Pillow
beautifulsoup4
lxml

aiohttp
httpx

# fastapi
# uvicorn
# pydantic
```
然后再：
```bash
uv pip install -r requirements.txt
```

### 使用
```bash
uv run server.py
```

将会在 `http://127.0.0.1:32000` 启动。  
`gscore` 面板里填写 `http://127.0.0.1:32000/render` 即可。  

### 注意
已做内存优化，缓存大小是可控的。  
如果你想用内存换 cpu 速度，或者 cpu 不太行，就去 `server.py` 和 `cards\[包名]\__init__.py` 调大缓冲区；  
如果cpu好就可以不用管，不过每张卡片会多重复计算几步，多几毫秒。  

---

### vercel 部署

本项目已支持一键 vercel 部署。

- 推送: fork 该仓库，将代码推送至 GitHub 仓库。

- 导入: 在 Vercel 控制台导入该仓库，框架预设选择 Fastapi。

- 配置: 无需额外环境变量，直接点击 Deploy。

- 使用：`gscore` 面板里填写 `https://你的vercel域名.vercel.app/render` 即可。  

---