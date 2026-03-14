import gzip
import json
import gc
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response, PlainTextResponse
from fastapi.concurrency import run_in_threadpool

# 假设原项目的 cards 文件夹在根目录
from cards import render

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('unicon')

app = FastAPI(title="UIDCardRender-Vercel")

def _render_html_sync(html_content: str) -> bytes:
    """同步渲染入口，配合 gc 回收内存"""
    try:
        return render(html_content)
    finally:
        # 【内存护城河】强制释放 PIL 产生的临时图层和遮罩内存
        gc.collect()

@app.post("/render")
async def render_handler(request: Request):
    """
    Vercel Serverless 环境下的渲染接口。
    保留了原作者的内存极简策略（阅后即焚）。
    """
    try:
        # 1. 异步读取请求体到内存
        body_bytes = await request.body()

        # 2. 内存中直接解压 Gzip
        ce = request.headers.get('Content-Encoding', '').lower()
        if ce == 'gzip' or body_bytes.startswith(b'\x1f\x8b'):
            body_bytes = gzip.decompress(body_bytes)

        # 3. 解码为字符串并立即销毁字节流
        text = body_bytes.decode('utf-8', errors='ignore')
        del body_bytes 

        # 4. 解析 JSON 并立即销毁长文本
        data = json.loads(text)
        del text 

        html = data.get('html')
        if not html:
            raise HTTPException(status_code=400, detail="missing html")

        # 5. 提取完毕，立刻销毁体积庞大的 JSON 字典对象
        del data 

        # 6. 将 CPU 密集型的 PIL 渲染扔进 FastAPI 的底层线程池执行
        # 这样在等待渲染时，Vercel 实例仍能响应其他轻量请求（比如 /health）
        img_bytes = await run_in_threadpool(_render_html_sync, html)

        if not img_bytes:
            raise HTTPException(status_code=400, detail="未匹配到任何卡片渲染规则")

        return Response(content=img_bytes, media_type="image/jpeg")

    except Exception as e:
        logger.error(f"Render error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return PlainTextResponse("ok")