import asyncio
import json
import os
import logging
import gzip
import gc
from concurrent.futures import ThreadPoolExecutor
from aiohttp import web

# ---------------------------
# Logging 
# ---------------------------
LOG_LEVEL = os.environ.get('UNICON_LOG_LEVEL', os.environ.get('LOG_LEVEL', 'INFO')).upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s %(levelname)-8s %(name)s: %(message)s',
)
unicon_logger = logging.getLogger('unicon')
unicon_logger.debug('logger initialized, level=%s', LOG_LEVEL)

HOST = '127.0.0.1'
PORT = int(os.environ.get('PORT', '32000'))


def _render_html(html: str) -> bytes:
    """同步渲染入口，运行于线程池中。"""
    from cards import render
    try:
        return render(html)
    finally:
        # 【内存护城河】渲染结束时，强制释放 PIL 产生的临时图层和遮罩内存
        gc.collect()

async def render_handler(request: web.Request) -> web.Response:
    """
    纯内存数据流转，零磁盘 I/O 消耗。
    采用“阅后即焚”策略，及时销毁中间变量以节省内存。
    """
    try:
        # 1. 直接读取到内存 (抛弃慢速的硬盘 tmp 临时文件)
        body_bytes = await request.read()

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
            return web.json_response({'error': 'missing html'}, status=400)

        # 5. 提取完毕，立刻销毁体积庞大的 JSON 字典对象
        del data 

        # 6. 将干净纯粹的 html 丢给子线程渲染
        loop = asyncio.get_running_loop()
        img_bytes = await loop.run_in_executor(request.app['pool'], _render_html, html)

        return web.Response(body=img_bytes, content_type='image/jpeg')

    except web.HTTPException:
        raise
    except Exception as e:
        unicon_logger.error(f"Render error: {e}", exc_info=True)
        return web.json_response({'error': str(e)}, status=500)


async def health(request):
    return web.Response(text='ok')


def create_app():
    # 限制单次请求最大 40MB (完全足够纯文字或带几个 base64 的 html)
    app = web.Application(client_max_size=40 * 1024 * 1024)
    app.router.add_post('/render', render_handler)
    app.router.add_get('/health', health)

    # 【内存护城河】严格限制并发数为 1 或 2，防止瞬间内存激增
    # 设为 1 最省内存，设为 2 处理稍微快点。这里默认设为 2。
    app['pool'] = ThreadPoolExecutor(max_workers=2)
    
    return app


def main():
    app = create_app()
    unicon_logger.info('starting unicon server on %s:%s (Optimized Low-Mem Edition)', HOST, PORT)
    web.run_app(app, host=HOST, port=PORT, access_log=unicon_logger)


if __name__ == '__main__':
    main()