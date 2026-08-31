#!/usr/bin/env python3
# Run from repo root:
#   .venv/bin/python src/mineru/mineru_vllm_proxy.py --listen-port 8004 --upstream http://127.0.0.1:8005 --served-model-name mineru
"""Small local proxy for MinerU's vLLM OpenAI-compatible server.

Some vLLM/MinerU combinations can serve inference correctly while raising 500
from /v1/models. MinerU's vlm-http-client requires that endpoint before it sends
chat requests, so this proxy returns a stable one-model response and forwards all
other requests to the real vLLM server.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Final


HOP_BY_HOP_HEADERS: Final[set[str]] = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Proxy MinerU vLLM requests and provide a stable /v1/models.")
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=8004)
    parser.add_argument("--upstream", default="http://127.0.0.1:8005")
    parser.add_argument("--served-model-name", default="mineru")
    parser.add_argument("--model-root", default="/srv/models/MinerU/MinerU2.5-Pro-2605-1.2B")
    return parser


class MinerUVllmProxy(BaseHTTPRequestHandler):
    server_version = "MinerUVllmProxy/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}", flush=True)

    @property
    def proxy_server(self) -> "ProxyHTTPServer":
        return self.server  # type: ignore[return-value]

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] == "/v1/models":
            self.handle_models()
            return
        self.forward()

    def do_POST(self) -> None:  # noqa: N802
        self.forward()

    def do_HEAD(self) -> None:  # noqa: N802
        self.forward()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.forward()

    def handle_models(self) -> None:
        now = int(time.time())
        payload = {
            "object": "list",
            "data": [
                {
                    "id": self.proxy_server.served_model_name,
                    "object": "model",
                    "created": now,
                    "owned_by": "vllm",
                    "root": self.proxy_server.model_root,
                    "parent": None,
                    "permission": [],
                }
            ],
        }
        self.send_json(HTTPStatus.OK, payload)

    def send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def forward(self) -> None:
        content_length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(content_length) if content_length else None
        url = self.proxy_server.upstream.rstrip("/") + self.path
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "host"
        }
        request = urllib.request.Request(url, data=body, headers=headers, method=self.command)
        try:
            with urllib.request.urlopen(request, timeout=None) as response:
                response_body = response.read()
                self.send_response(response.status)
                self.copy_response_headers(response.headers.items(), len(response_body))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(response_body)
        except urllib.error.HTTPError as exc:
            response_body = exc.read()
            self.send_response(exc.code)
            self.copy_response_headers(exc.headers.items(), len(response_body))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(response_body)
        except Exception as exc:  # noqa: BLE001
            payload = {
                "error": {
                    "message": f"Failed to proxy request to {url}: {exc}",
                    "type": "proxy_error",
                    "code": HTTPStatus.BAD_GATEWAY,
                }
            }
            self.send_json(HTTPStatus.BAD_GATEWAY, payload)

    def copy_response_headers(self, headers: object, content_length: int) -> None:
        for key, value in headers:
            lowered = key.lower()
            if lowered in HOP_BY_HOP_HEADERS or lowered == "content-length":
                continue
            self.send_header(key, value)
        self.send_header("content-length", str(content_length))


class ProxyHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        *,
        upstream: str,
        served_model_name: str,
        model_root: str,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.upstream = upstream
        self.served_model_name = served_model_name
        self.model_root = model_root


def main() -> None:
    args = build_parser().parse_args()
    server = ProxyHTTPServer(
        (args.listen_host, args.listen_port),
        MinerUVllmProxy,
        upstream=args.upstream,
        served_model_name=args.served_model_name,
        model_root=args.model_root,
    )
    print(
        f"Starting MinerU vLLM proxy on http://{args.listen_host}:{args.listen_port}; "
        f"upstream={args.upstream}; served_model_name={args.served_model_name}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
