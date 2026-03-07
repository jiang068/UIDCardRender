#!/usr/bin/env python3
"""Async HTTP server (aiohttp) for rendering HTML -> image using a PIL renderer.

This replaces the previous simple TCP debug server. It exposes a POST /render endpoint
that accepts JSON: {"html": "..."} and returns image/jpeg bytes.

It runs the CPU-bound PIL rendering function in a ThreadPoolExecutor to avoid blocking
the event loop.
"""
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

HOST = '0.0.0.0'
PORT = int(os.environ.get('PORT', '32000'))


def _render_html(html: str) -> bytes:
    """同步渲染入口，运行于线程池中。根据 HTML 特征分派到对应卡片渲染器。"""
    
    # 1. 伴行积分卡片
    if '鸣潮伴行积分' in html or 'COMPANION REWARD SYSTEM' in html:
        try:
            from cards import wwjf as wwjf_card
            unicon_logger.info('dispatch -> wwjf (积分)')
            return wwjf_card.render(html)
        except Exception:
            unicon_logger.exception('failed to render with wwjf')

    # 2. 海墟卡（Slash / 海墟）
    if '海墟' in html or 'slash-block' in html or '冥歌海墟' in html:
        try:
            from cards import wwmh as wwmh_card
            unicon_logger.info('dispatch -> wwmh (海墟)')
            return wwmh_card.render(html)
        except Exception:
            unicon_logger.exception('failed to render with wwmh')

    # 3. 每日体力卡片
    if '鸣潮体力' in html or 'stat-cur' in html or 'progress-fill' in html:
        try:
            from cards import wwmr as wwmr_card
            unicon_logger.info('dispatch -> wwmr (体力)')
            return wwmr_card.render(html)
        except Exception:
            unicon_logger.exception('failed to render with wwmr')

    # 4. 鸣潮角色卡片（全家福）
    if '鸣潮角色卡片' in html or 'ROVER RESONANCE CARD' in html or 'role-grid' in html:
        try:
            from cards import wwkp as wwkp_card
            unicon_logger.info('dispatch -> wwkp (角色)')
            return wwkp_card.render(html)
        except Exception:
            unicon_logger.exception('failed to render with wwkp')

    # 5. 默认：深塔卡片 (兜底处理)
    try:
        from cards import wwst as wwst_card
        unicon_logger.info('dispatch -> wwst (深塔)')
        return wwst_card.render(html)
    except Exception:
        unicon_logger.exception('failed to render with wwst')
        raise


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
    return app


def main():
    app = create_app()
    unicon_logger.info('starting server on %s:%s', HOST, PORT)
    web.run_app(app, host=HOST, port=PORT, access_log=unicon_logger)


if __name__ == '__main__':
    main()