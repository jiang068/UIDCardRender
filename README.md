## UIDCardRender
### 安装
```bash
uv venv --python 3.12
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