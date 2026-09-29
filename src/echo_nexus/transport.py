"""Optional neocortex and MCP transports. Never invoke tools from model text."""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import urllib.parse
from pathlib import Path

import httpx

from .config import state_dir


def endpoint(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    if parts.username or parts.password or parts.query or parts.fragment or not parts.hostname:
        raise ValueError("Usa una URL base sin credenciales, parámetros ni fragmento")
    if parts.scheme != "https" and not (parts.scheme == "http" and parts.hostname in ("127.0.0.1", "localhost", "::1")):
        raise ValueError("La API necesita HTTPS; HTTP solo se permite en localhost")
    return url.rstrip("/")


SYSTEM = ("Eres el neocórtex lingüístico opcional de echo-nexus. Tus respuestas son propuestas, "
          "no hechos verificados por ECHO. No afirmes haber ejecutado pruebas, observado neuronas "
          "o cambiado el motor. No tienes herramientas ni acceso automático a archivos. "
          "Explica de forma concisa y separa observaciones proporcionadas e hipótesis.")


class Cortex:
    def __init__(self, url: str, model: str, key_env: str | None = None, protocol="openai"):
        self.url = endpoint(url)
        if not model or protocol not in ("openai", "anthropic"):
            raise ValueError("Modelo o protocolo no válido")
        if key_env and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key_env):
            raise ValueError("Indica el NOMBRE de una variable de entorno, no la clave")
        self.model, self.key_env, self.protocol = model, key_env, protocol
        self.history = []

    async def ask(self, prompt):
        headers = {"Content-Type": "application/json"}
        key = os.getenv(self.key_env, "") if self.key_env else ""
        if self.key_env and not key:
            raise ValueError(f"Falta la variable de entorno {self.key_env}")
        history = self.history[-10:] + [{"role": "user", "content": prompt[:24000]}]
        if self.protocol == "anthropic":
            if key:
                headers["x-api-key"] = key
            headers["anthropic-version"] = "2023-06-01"
            body = {"model": self.model, "system": SYSTEM, "messages": history, "max_tokens": 1024}
            route = "/messages"
        else:
            if key:
                headers["Authorization"] = "Bearer " + key
            body = {"model": self.model, "messages": [{"role": "system", "content": SYSTEM}] + history,
                    "stream": False, "max_tokens": 1024}
            route = "/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=90, follow_redirects=False) as client:
                async with client.stream("POST", self.url + route, json=body, headers=headers) as response:
                    if not 200 <= response.status_code < 300:
                        raise RuntimeError(f"La API devolvió HTTP {response.status_code}; revisa URL, modelo y clave")
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 2_000_000:
                            raise ValueError("Respuesta demasiado grande")
                    result = json.loads(raw)
        except httpx.HTTPError:
            raise RuntimeError("No se pudo conectar con la API; revisa red, URL y tiempo de espera") from None
        if self.protocol == "anthropic":
            text = "\n".join(p.get("text", "") for p in result.get("content", []) if p.get("type") == "text")
        else:
            text = result["choices"][0]["message"].get("content")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("El proveedor no devolvió texto; este conector no ejecuta tool calls")
        self.history = (history + [{"role": "assistant", "content": text[:24000]}])[-12:]
        return text

class LocalModel:
    def __init__(self):
        self.process = None
        self.log = None

    async def start(self, path):
        file = Path(path).expanduser().resolve()
        if not file.is_file() or file.suffix.lower() != ".gguf":
            raise ValueError("Indica un archivo .gguf existente")
        with file.open("rb") as f:
            if f.read(4) != b"GGUF":
                raise ValueError("El archivo no tiene la cabecera GGUF")
        binary = shutil.which("llama-server")
        if not binary:
            raise ValueError("Instala llama-server para cargar modelos GGUF")
        await self.close()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        root = state_dir()
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.log_path = root / f"llama-{os.getpid()}.log"
        self.log = os.fdopen(os.open(self.log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w")
        self.process = await asyncio.create_subprocess_exec(
            binary, "--model", str(file), "--alias", "echo-local", "--host", "127.0.0.1", "--port", str(port),
            "--ctx-size", "4096", "--threads", "4", stdout=self.log, stderr=self.log)
        async def healthy():
            try:
                async with httpx.AsyncClient(timeout=1, trust_env=False) as client:
                    response = await client.get(f"http://127.0.0.1:{port}/health")
                    return response.status_code == 200
            except httpx.HTTPError:
                return False
        try:
            for _ in range(180):
                if self.process.returncode is not None:
                    raise RuntimeError(f"llama-server terminó; consulta {self.log_path}")
                if await healthy():
                    return Cortex(f"http://127.0.0.1:{port}/v1", "echo-local")
                await asyncio.sleep(1)
            raise TimeoutError(f"Carga GGUF agotó 180 s; consulta {self.log_path}")
        except BaseException:
            await self.close()
            raise

    async def close(self):
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 4)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        if self.log:
            self.log.close()
        self.process = self.log = None


class MCP:
    """MCP stdio client; tool execution requires an explicit operator command."""
    def __init__(self):
        self.process = None
        self.next_id = 0
        self.lock = asyncio.Lock()
        self.tools = []

    async def connect(self, argv: list[str], cwd=None):
        if not argv:
            raise ValueError("Falta el comando MCP")
        self.process = await asyncio.create_subprocess_exec(*argv, cwd=cwd, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, limit=2_000_000,
            **({"start_new_session": True} if os.name == "posix" else {}))
        try:
            result = await self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "echo-nexus", "version": "0.1.0"}})
            if result.get("protocolVersion") not in ("2025-06-18", "2025-03-26", "2024-11-05", "2025-11-25"):
                raise ValueError("Versión MCP no compatible")
            self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            cursor = None
            for _ in range(20):
                page = await self.request("tools/list", {"cursor": cursor} if cursor else {})
                self.tools.extend(page.get("tools", []))
                cursor = page.get("nextCursor")
                if not cursor:
                    break
            else:
                raise ValueError("El catálogo MCP excede 20 páginas")
            return result
        except BaseException:
            await self.close()
            raise

    def send(self, message):
        self.process.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode())

    async def request(self, method, params, timeout=30):
        async with self.lock:
            self.next_id += 1
            mid = self.next_id
            self.send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params})
            await self.process.stdin.drain()
            async def receive():
                while True:
                    line = await self.process.stdout.readline()
                    if not line:
                        raise RuntimeError("El servidor MCP cerró la conexión")
                    response = json.loads(line)
                    if "method" in response and "id" in response:
                        self.send({"jsonrpc": "2.0", "id": response["id"], "error": {
                            "code": -32601, "message": "Client capabilities not supported"}})
                    elif response.get("id") == mid:
                        if "error" in response:
                            raise RuntimeError("MCP: " + str(response["error"].get("message", "error")))
                        return response.get("result", {})
            return await asyncio.wait_for(receive(), timeout)

    async def call(self, name, arguments):
        if name not in {t["name"] for t in self.tools}:
            raise ValueError("Herramienta no anunciada por el servidor")
        return await self.request("tools/call", {"name": name, "arguments": arguments}, timeout=120)

    async def close(self):
        if self.process:
            try:
                os.killpg(self.process.pid, signal.SIGTERM) if os.name == "posix" else self.process.terminate()
                await asyncio.wait_for(self.process.wait(), 3)
            except asyncio.TimeoutError:
                os.killpg(self.process.pid, signal.SIGKILL) if os.name == "posix" else self.process.kill()
                await self.process.wait()
            except ProcessLookupError:
                pass
        self.process = None
        self.tools = []
