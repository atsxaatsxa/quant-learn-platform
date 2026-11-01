"""
Web 服务：标准库 http.server（零额外依赖，保证「单机可运行」）。

路由：
  GET  /                      -> 前端首页 (static/index.html)
  GET  /static/<path>         -> 静态资源
  GET  /api/config            -> 配置摘要（标的池/成本/区间/假设/术语）
  GET  /api/strategies        -> 模板策略元信息 + 代码示例
  GET  /api/roadmap           -> 教学路线图步骤
  GET  /api/glossary          -> 术语白话表
  POST /api/backtest          -> 运行回测，返回完整报告 JSON
  GET  /api/data_status       -> 缓存数据状态
"""
import sys
import os
import json
import http.server
import socketserver
from urllib.parse import urlparse

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.util.config import get_config
from backend.strategies import registry
from backend.teaching import roadmap as RM
from backend.runner import run_backtest
from backend.data import datasource
from backend.engine.exceptions import ValidationError

STATIC_DIR = os.path.join(_ROOT, "backend", "static")
PORT = int(os.environ.get("PORT", "8000"))


class Handler(http.server.BaseHTTPRequestHandler):
    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type):
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self._send_json({"error": "not found"}, 404)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/" or path == "/index.html":
            return self._send_file(os.path.join(STATIC_DIR, "index.html"), "text/html; charset=utf-8")
        if path.startswith("/static/"):
            rel = path[len("/static/"):]
            fpath = os.path.join(STATIC_DIR, rel)
            # 防目录穿越
            if not os.path.abspath(fpath).startswith(os.path.abspath(STATIC_DIR)):
                return self._send_json({"error": "forbidden"}, 403)
            ctype = "text/plain"
            if rel.endswith(".html"): ctype = "text/html; charset=utf-8"
            elif rel.endswith(".js"): ctype = "application/javascript; charset=utf-8"
            elif rel.endswith(".css"): ctype = "text/css; charset=utf-8"
            return self._send_file(fpath, ctype)
        if path == "/api/config":
            return self._send_json(self._config())
        if path == "/api/strategies":
            return self._send_json({
                "templates": registry.get_template_meta(),
                "sample_code": registry.SAMPLE_CODE,
                "allow_code_mode": get_config()["strategies"]["allow_code_mode"],
            })
        if path == "/api/roadmap":
            return self._send_json({"steps": RM.get_roadmap(), "glossary": RM.get_glossary()})
        if path == "/api/glossary":
            return self._send_json(RM.get_glossary())
        if path == "/api/data_status":
            return self._send_json(self._data_status())
        return self._send_json({"error": "unknown route"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/backtest":
            return self._send_json({"error": "unknown route"}, 404)
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            req = json.loads(raw.decode("utf-8") or "{}")
        except Exception as e:  # noqa
            return self._send_json({"error": f"请求解析失败：{e}"}, 400)
        try:
            report = run_backtest(req)
            return self._send_json({"ok": True, "report": report})
        except ValidationError as e:
            # 一票否决：参数校验失败 -> 明确报错，绝不输出报告
            return self._send_json({"ok": False, "error": str(e), "field": e.field}, 400)
        except Exception as e:  # noqa
            return self._send_json({"ok": False, "error": f"回测执行失败：{e}"}, 500)

    def _config(self):
        cfg = get_config()
        return {
            "universe": cfg["universe"],
            "costs": cfg["costs"],
            "backtest": {k: cfg["backtest"][k] for k in ("initial_capital", "default_start", "default_end")},
            "metrics_assumptions": {
                "risk_free_rate": cfg["metrics"]["risk_free_rate"],
                "trading_days_per_year": cfg["metrics"]["trading_days_per_year"],
                "abnormal_return_threshold": cfg["metrics"]["abnormal_return_threshold"],
            },
            "source_info": datasource.describe_source(),
        }

    def _data_status(self):
        cfg = get_config()
        cache_dir = datasource._cache_dir()
        files = []
        if os.path.isdir(cache_dir):
            for fn in sorted(os.listdir(cache_dir)):
                fp = os.path.join(cache_dir, fn)
                files.append({"file": fn, "size": os.path.getsize(fp)})
        return {"cache_dir": cache_dir, "cached_files": files}

    def log_message(self, fmt, *args):
        sys.stderr.write("[server] " + (fmt % args) + "\n")


def main():
    # 启动时尝试确保默认数据已缓存（仅当缓存缺失时联网抓取；限流时快速失败不阻塞）
    try:
        cfg = get_config()
        syms = cfg["universe"]["default_symbols"] + [cfg["universe"]["benchmark"], cfg["universe"]["etf_example"]]
        datasource.load_market(syms, cfg["backtest"]["default_start"], cfg["backtest"]["default_end"],
                              allow_sleep=False, refresh=False)
    except Exception as e:  # noqa
        sys.stderr.write(f"[server] 数据预加载跳过（将按需联网抓取）：{e}\n")

    httpd = socketserver.ThreadingTCPServer(("0.0.0.0", PORT), Handler)
    sys.stderr.write(f"[server] 量化学习平台已启动： http://127.0.0.1:{PORT}\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


if __name__ == "__main__":
    main()
