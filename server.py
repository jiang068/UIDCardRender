import asyncio
import json
import os
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from aiohttp import web

# ---------------------------
# Logging (名为 'unicon'，兼容历史记忆中的名称)
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
    """同步渲染入口，运行于线程池中。分流逻辑在 cards.XutheringWavesUID 中维护。"""
    from cards import render
    return render(html)

async def render_handler(request: web.Request) -> web.Response:
    """Stream request body to disk, parse JSON (support gzip), then hand HTML to renderer.

    This avoids loading large request bodies fully into memory.
    """
    import tempfile
    import gzip
    from pathlib import Path

    tmp_path = None
    try:
        # Create temp file in the project dir to avoid cross-drive issues on Windows
        out_dir = os.path.dirname(__file__)
        fd, tmp_path = tempfile.mkstemp(prefix='render_', suffix='.tmp', dir=out_dir)
        os.close(fd)

        # Stream incoming body to file
        with open(tmp_path, 'wb') as wf:
            async for chunk in request.content.iter_chunked(65536):
                if not chunk:
                    break
                wf.write(chunk)

        # Detect content-encoding header or gzip magic
        ce = request.headers.get('Content-Encoding', '').lower()
        is_gzip = ce == 'gzip'
        if not is_gzip:
            # check magic bytes
            with open(tmp_path, 'rb') as f:
                start = f.read(2)
            if start == b'\x1f\x8b':
                is_gzip = True

        # Read and decode
        if is_gzip:
            with gzip.open(tmp_path, 'rb') as f:
                body_bytes = f.read()
        else:
            with open(tmp_path, 'rb') as f:
                body_bytes = f.read()

        try:
            text = body_bytes.decode('utf-8')
        except Exception:
            try:
                text = body_bytes.decode('latin-1')
            except Exception:
                return web.json_response({'error': 'failed to decode request body'}, status=400)

        # Parse JSON
        try:
            data = json.loads(text)
        except Exception as e:
            return web.json_response({'error': f'invalid json: {e}'}, status=400)

        html = data.get('html')
        if not html:
            return web.json_response({'error': 'missing html'}, status=400)

        loop = asyncio.get_running_loop()
        # Run the CPU-bound render in a threadpool
        img_bytes = await loop.run_in_executor(request.app['pool'], _render_html, html)

        return web.Response(body=img_bytes, content_type='image/jpeg')
    except web.HTTPException:
        raise
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)
    finally:
        # clean up temp file
        try:
            if tmp_path and Path(tmp_path).exists():
                Path(tmp_path).unlink()
        except Exception:
            pass


async def health(request):
    return web.Response(text='ok')


def create_app():
    # Allow large request bodies (e.g. HTML payloads up to 50MB)
    app = web.Application(client_max_size=50 * 1024 * 1024)
    app.router.add_post('/render', render_handler)
    app.router.add_get('/health', health)

    # Thread pool
    app['pool'] = ThreadPoolExecutor(max_workers=2)
    
    # Background cache cleaner: periodically call cards.XutheringWavesUID.clear_image_caches
    # to avoid unbounded growth from per-request data: URIs being cached by many modules.
    async def _cache_cleaner_loop(app):
        import asyncio
        from cards.XutheringWavesUID import clear_image_caches
        while True:
            try:
                cleared = clear_image_caches()
                if cleared:
                    unicon_logger.debug('cleared image caches: %s', cleared)
            except Exception:
                unicon_logger.exception('cache cleaner failed')
            await asyncio.sleep(60 * 10)  # every 10 minutes

    async def _start_cache_cleaner(app):
        app['cache_cleaner_task'] = asyncio.create_task(_cache_cleaner_loop(app))

    async def _stop_cache_cleaner(app):
        task = app.get('cache_cleaner_task')
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app.on_startup.append(_start_cache_cleaner)
    app.on_cleanup.append(_stop_cache_cleaner)
    return app


def main():
    app = create_app()
    unicon_logger.info('starting server on %s:%s', HOST, PORT)
    web.run_app(app, host=HOST, port=PORT, access_log=unicon_logger)


if __name__ == '__main__':
    main()