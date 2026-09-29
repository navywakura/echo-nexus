"""The echo-nexus terminal. Views consume evidence; they cannot change ECHO."""
from __future__ import annotations

import asyncio
import json
import shlex
import shutil
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.suggester import SuggestFromList
from textual.widgets import Footer, Input, RichLog, Static

from . import __version__
from .backend import Runner, Tail, demo_test, read_manifest
from .commands import COMMANDS, matches
from .connections import parse, profile, describe, name as connection_name
from .config import SessionLog, detect, load_config, redact, save_config, state_dir
from .transport import Cortex, LocalModel, MCP
from .visual import grid_text, image_text, telemetry_tree

BANNER = """  █▀▀ █▀▀ █ █ █▀█   /  N E X U S
  ██▄ █▄▄ █▀█ █▄█   /  observe · connect · verify"""


class Nexus(App):
    TITLE = "echo-nexus · RxLabs"
    SUB_TITLE = "developer: rxlabs"
    CSS = """
    Screen { background: #09060f; color: #eee8f5; }
    #stars { height: 1; color: #8965b4; background: #09060f; }
    #banner { height: 4; color: #cfb1ff; padding: 0 2; }
    #status { height: 2; padding: 0 2; color: #a98bc8; border-bottom: solid #372244; }
    #body { height: 1fr; padding: 0 1; }
    #conversation { width: 2fr; min-width: 30; border: round #50366a; padding: 0 1; }
    #side { width: 1fr; min-width: 32; margin-left: 1; }
    #telemetry { height: 1fr; min-height: 8; border: round #50366a; padding: 0 1; overflow-y: auto; }
    #world { height: 1fr; min-height: 8; border: round #50366a; padding: 0 1; content-align: center middle; }
    #origin { height: 2; color: #ba91ff; padding: 0 1; }
    #hints { height: 3; color: #b3a1c7; padding: 0 2; overflow: hidden; }
    #prompt { margin: 0 1; border: tall #674387; background: #171023; }
    #prompt:focus { border: tall #ba91ff; }
    Footer { background: #1b1129; color: #c4a3ea; }
    Footer > .footer--key { background: #39224e; color: #ffffff; }
    .narrow #side { display: none; }
    .expanded #side { display: block; width: 1fr; }
    .expanded #conversation { display: none; }
    """
    BINDINGS = [Binding("ctrl+c", "cancel", "Detener", priority=True),
                Binding("ctrl+q", "quit", "Salir", priority=True),
                Binding("f1", "help", "Ayuda"), Binding("f2", "tree", "Telemetría"),
                Binding("tab", "complete", "Completar", priority=True)]

    def __init__(self, backend=None, stars=True, connect=None, autoconnect=True):
        super().__init__()
        self.config = load_config()
        self.backend_path = backend or self.config.get("backend")
        self.catalog = []
        self.runner = Runner()
        self.local_model = LocalModel()
        self.cortex = None
        self.connection = None
        self.active_profile = None
        self.start_connection = (connect or self.config.get("default_connection")) if autoconnect else None
        self.mcps = {}
        self.tail = None
        self.row = {}
        self.grid = None
        self.image_path = None
        self.stars_enabled = stars
        self.star_tick = 0
        self.active_task = None
        self.session = SessionLog()
        self.history = []

    def compose(self) -> ComposeResult:
        yield Static("", id="stars")
        yield Static(Text(BANNER), id="banner")
        yield Static("", id="status")
        with Horizontal(id="body"):
            yield RichLog(id="conversation", highlight=False, markup=False, wrap=True, max_lines=1500)
            with Vertical(id="side"):
                yield Static(telemetry_tree(), id="telemetry")
                yield Static("Sin imagen\n/devtest · /watch · /image", id="world")
                yield Static("SIN TELEMETRÍA · esperando una fuente", id="origin")
        yield Static("/devtest  pruebas  ·  /connect  neocórtex  ·  /agents  conexiones", id="hints")
        yield Input(placeholder="Escribe / para comandos, o conversa con el neocórtex…", id="prompt",
                    suggester=SuggestFromList(sorted({c[0] for c in COMMANDS}), case_sensitive=True))
        yield Footer()

    def on_mount(self):
        self.query_one("#conversation").border_title = "01 / SESIÓN"
        self.query_one("#telemetry").border_title = "02 / ÁRBOL OBSERVABLE"
        self.query_one("#world").border_title = "03 / MUNDO · IMAGEN"
        self.say("echo-nexus", f"v{__version__} · developer: rxlabs · © 2026 RxLabs\n"
                 "Una ventana al trabajo de ECHO. Pruebas, observaciones y conexiones en un lugar.\n"
                 "Escribe /help. Tab completa comandos; F2 amplía el árbol y el mundo.")
        if self.backend_path:
            try:
                self.load_backend(self.backend_path)
            except (OSError, ValueError) as e:
                self.say("backend", str(e), "#f0b783")
        elif binary := shutil.which("echoai"):
            self.catalog = [{"id": name, "title": title, "kind": "development", "default": name == "info",
                "argv": [binary, name], "timeout": 120} for name, title in (
                    ("info", "Motor instalado · identidad"), ("situate", "Identidad situada"),
                    ("life", "Vida integrada ECHO-4"), ("resume", "Continuidad entre procesos"))]
            self.say("motor", "ECHO CLI detectada. /devtest list muestra sus pruebas.")
        else:
            self.say("conexión", "Motor ECHO sin conectar. /backend MANIFEST.json carga sus pruebas.\n"
                     "/demo prueba la interfaz con una fixture; no produce resultados de ECHO.")
        self.update_status()
        self.set_interval(0.25, self.animate_stars)
        self.set_interval(0.3, self.poll_source)
        self.query_one(Input).focus()
        if self.start_connection:
            self.run_worker(self.execute("/connections use " + shlex.quote(self.start_connection)), exit_on_error=False)

    def say(self, source, message, color="#ba91ff"):
        if not len(self.query(RichLog)):
            return
        text = redact(str(message))
        line = Text("\n" + source.upper() + "  ", style=color)
        line.append(text, style="#eee8f5")
        self.query_one(RichLog).write(line)
        self.session.write(source.upper() + " | " + text)

    def update_status(self):
        if not len(self.query("#status")):
            return
        cortex = self.cortex.model if self.cortex else "OFF"
        active = "PRUEBA / SOLICITUD ACTIVA" if self.active_task else "LISTO"
        self.query_one("#status", Static).update(Text(f"Rx / {active}     MOTOR {'CONECTADO' if self.catalog else '—'}"
            f"     NEOCÓRTEX {cortex}     MCP {len(self.mcps)}"))
        self.query_one("#telemetry", Static).update(telemetry_tree(self.row, bool(self.cortex)))

    def animate_stars(self):
        if not len(self.query("#stars")):
            return
        self.star_tick += 1
        width = max(1, self.size.width - 2)
        if not self.stars_enabled:
            self.query_one("#stars", Static).update("")
            return
        row = [" "] * width
        for i in range(max(3, width // 9)):
            row[(i * 37 + 7) % width] = ("·", "✧", "⋆", "·")[(self.star_tick // 4 + i * 3) % 4]
        self.query_one("#stars", Static).update("".join(row))

    def on_resize(self):
        self.set_class(self.size.width < 95, "narrow")
        self.refresh_world()

    def refresh_world(self):
        if not self.is_mounted:
            return
        world = self.query_one("#world", Static)
        try:
            width, height = max(8, world.size.width - 4), max(4, world.size.height - 3)
            if self.image_path:
                world.update(image_text(self.image_path, width, height))
            elif self.grid is not None:
                world.update(grid_text(self.grid, width, height))
        except (OSError, ValueError) as e:
            world.update(Text(str(e)))

    def consume(self, event, source="LIVE / desarrollo"):
        kind = event.get("kind", "decision")
        origin = str(event.get("origin", source))
        self.query_one("#origin", Static).update(Text(origin))
        if "grid" in event:
            self.grid, self.image_path = event["grid"], None
            self.refresh_world()
        if any(k in event for k in ("wsp", "q", "q_row", "action", "lif_a", "beliefs")):
            self.row.update(event)
            self.query_one("#telemetry", Static).update(telemetry_tree(self.row, bool(self.cortex)))
        if kind == "frame":
            return
        if kind == "process_end":
            self.say("proceso", f"{event['test']} · exit {event['exit_code']}. "
                     "La salida del proceso no certifica un examen reservado.")
        elif kind == "telemetry":
            self.say("observación", f"Turno {event.get('turn')} · acción {event.get('action_name')} · "
                     f"recompensa {event.get('reward')} · gate {event.get('gate')}")
        else:
            self.say(kind, event.get("text", json.dumps(event, ensure_ascii=False)[:2500]))

    def poll_source(self):
        if self.tail and len(self.query("#origin")):
            try:
                for row in self.tail.read():
                    self.consume(row, "REGISTRO EXISTENTE / solo lectura")
            except (OSError, ValueError) as e:
                self.say("registro", str(e))
                self.tail = None

    def load_backend(self, path):
        manifest = read_manifest(path)
        self.catalog = manifest.get("tests", [])
        self.backend_path = str(Path(path).expanduser().resolve())
        self.say("backend", f"{manifest.get('name', 'ECHO')} · {len(self.catalog)} entradas disponibles")

    def on_input_changed(self, event: Input.Changed):
        options = matches(event.value) if event.value.startswith("/") else []
        self.query_one("#hints", Static).update(Text("\n".join(
            f"{name} {syntax}  —  {description}" for name, syntax, description in options[:3])
            if options else "Enter envía · Tab completa · F1 ayuda · F2 árbol/mundo · Ctrl+C detiene"))

    def action_complete(self):
        prompt = self.query_one(Input)
        value = prompt.value
        choices = sorted({c[0] for c in COMMANDS} | {"/connect api", "/connect anthropic", "/connect local",
            "/devtest list", "/devtest all", "/mcp connect", "/mcp tools", "/mcp call", "/mcp close",
            "/stars on", "/stars off", "/connections list", "/connections save", "/connections use",
            "/connections remove", "/connections default"} | {"/connections use " + n for n in self.config.get("connections", {})} | {"/devtest " + t["id"] for t in self.catalog})
        options = [c for c in choices if c.startswith(value)]
        if options:
            prompt.value = options[0] + " "
            prompt.cursor_position = len(prompt.value)

    def on_input_submitted(self, event: Input.Submitted):
        value = event.value.strip()
        event.input.value = ""
        if value:
            self.run_worker(self.execute(value), exit_on_error=False)

    def action_help(self):
        self.run_worker(self.execute("/help"), exit_on_error=False)

    def action_tree(self):
        self.toggle_class("expanded")
        self.refresh_world()

    async def action_cancel(self):
        await self.runner.stop()
        if self.active_task and self.active_task is not asyncio.current_task():
            self.active_task.cancel()
        self.say("detener", "Cancelada la operación local del arnés. Una API remota puede terminar su solicitud.")

    async def execute(self, line):
        command = line.split(" ", 1)[0] if line.startswith("/") else "chat"
        quick = command in ("/help", "/stop", "/tree", "/logs", "/agents", "/clear", "/stars", "/quit")
        quick = quick or line.strip() in ("/connections", "/connections list")
        if self.active_task and not quick:
            self.say("ocupado", "Espera a la operación activa o usa /stop.")
            return
        task = asyncio.current_task()
        if not quick:
            self.active_task = task
        self.update_status()
        try:
            if command == "chat":
                self.say("tú", line)
                if not self.cortex:
                    self.say("neocórtex", "Conecta un modelo con /connect api o /connect local.")
                else:
                    self.say("neocórtex · propuesta", await self.cortex.ask(line))
                return
            if command == "/mcp" and line.startswith("/mcp call "):
                parts = line.split(None, 4)
                if len(parts) != 5:
                    raise ValueError('Sintaxis: /mcp call NAME TOOL {"arg":"value"}')
                args = json.loads(parts[4])
                if not isinstance(args, dict):
                    raise ValueError("Los argumentos MCP deben ser un objeto JSON")
                result = await self.mcps[parts[2]].call(parts[3], args)
                self.say("MCP · resultado externo", json.dumps(result, ensure_ascii=False))
                return
            parts = shlex.split(line)
            args = parts[1:]
            if command == "/help":
                selected = COMMANDS if not args else [c for c in COMMANDS if c[0] == "/" + args[0].lstrip("/")]
                self.say("comandos", "\n".join(f"{n} {s}\n  {d}" for n, s, d in selected))
            elif command == "/backend":
                self.load_backend(args[0])
                self.config["backend"] = self.backend_path
                save_config(self.config)
            elif command in ("/devtest", "/demo"):
                selection = "demo" if command == "/demo" else args[0] if args else "default"
                if selection == "list":
                    self.say("catálogo", "\n".join(f"{t['id']} [{t['kind']}] — {t['title']}" for t in self.catalog)
                             or "Motor sin conectar. /backend MANIFEST.json · /demo")
                    return
                if selection == "demo":
                    tests = [demo_test()]
                elif selection in ("all", "default"):
                    tests = [t for t in self.catalog if t["kind"] == "development"
                             and (selection == "all" or t.get("default", False))]
                else:
                    tests = [t for t in self.catalog if t["id"] == selection]
                if not tests:
                    raise ValueError("No hay pruebas para esa selección. /devtest list · /backend MANIFEST.json")
                for test in tests:
                    if test["kind"] != "development":
                        path = test.get("report")
                        if path:
                            file = Path(path).expanduser()
                            with file.open() as f:
                                report = f.read(16000)
                            self.say("EVIDENCIA ARCHIVADA · " + test["id"], report)
                        else:
                            self.say("sellado", test.get("note", "Examen no ejecutable desde el arnés"))
                        continue
                    self.say("desarrollo", test["title"])
                    self.row, self.grid, self.image_path = {}, None, None
                    self.query_one("#world", Static).update("Esperando un frame de esta prueba")
                    self.update_status()
                    code = await self.runner.run(test, self.consume)
                    if code:
                        self.say("suite", "Secuencia detenida; revisa la salida de la prueba.")
                        break
            elif command == "/connect":
                await self.open_connection(parse(args))
            elif command == "/connections":
                operation = args[0] if args else "list"
                saved = self.config.setdefault("connections", {})
                if operation == "list":
                    self.say("conexiones", "\n".join(
                        f"{n}{' [activa]' if n == self.active_profile else ''}"
                        f"{' [inicio]' if n == self.config.get('default_connection') else ''} · {describe(p)}"
                        for n, p in saved.items()) or "Ninguna guardada. /connect … y /connections save NOMBRE")
                elif operation == "save":
                    n = connection_name(args[1])
                    if not self.connection:
                        raise ValueError("Conecta primero un modelo con /connect")
                    saved[n] = profile(self.connection)
                    self.active_profile = n
                    save_config(self.config)
                    self.say("conexiones", f"Guardada: {n}. Solo parámetros y referencias de credenciales.")
                elif operation == "use":
                    n = connection_name(args[1])
                    await self.open_connection(saved[n], n)
                elif operation == "remove":
                    n = connection_name(args[1])
                    del saved[n]
                    if self.config.get("default_connection") == n:
                        self.config.pop("default_connection")
                    if self.active_profile == n:
                        self.active_profile = None
                    save_config(self.config)
                    self.say("conexiones", f"Perfil eliminado: {n}. La conexión actual se conserva.")
                elif operation == "default":
                    n = args[1]
                    if n == "off":
                        self.config.pop("default_connection", None)
                    else:
                        connection_name(n)
                        if n not in saved:
                            raise ValueError("Ese perfil no existe")
                        self.config["default_connection"] = n
                    save_config(self.config)
                    self.say("conexiones", f"Conexión al iniciar: {n}")
                else:
                    raise ValueError("/connections list|save|use|remove|default [NOMBRE]")
            elif command == "/disconnect":
                await self.local_model.close()
                self.cortex = self.connection = self.active_profile = None
                self.say("neocórtex", "Desconectado")
            elif command == "/agents":
                self.say("detección", "\n".join(f"{d['name']}: {d['path'] or 'no instalado'} · {d['interface']}" for d in detect()))
            elif command == "/mcp":
                operation, name = args[:2]
                if operation == "connect":
                    if len(args) < 4 or args[2] != "--":
                        raise ValueError("/mcp connect NAME -- COMMAND [ARGS]")
                    if name in self.mcps:
                        raise ValueError("Ese servidor ya está conectado; ciérralo antes")
                    client = MCP()
                    await client.connect(args[3:])
                    self.mcps[name] = client
                    self.say("MCP", f"{name} conectado · {len(client.tools)} herramientas · /mcp tools {name}")
                elif operation == "tools":
                    self.say("MCP · " + name, "\n".join(json.dumps(t, ensure_ascii=False) for t in self.mcps[name].tools))
                elif operation == "close":
                    await self.mcps.pop(name).close()
                else:
                    raise ValueError("Operación MCP desconocida; /help mcp")
            elif command == "/watch":
                self.tail = None if args[0] == "off" else Tail(args[0])
                self.say("registro", "Seguimiento desactivado" if self.tail is None else "Solo lectura: " + str(self.tail.path))
            elif command == "/image":
                path = Path(args[0]).expanduser()
                image_text(path)
                self.image_path = path
                self.refresh_world()
                self.query_one("#origin", Static).update("IMAGEN LOCAL · " + path.name)
            elif command == "/tree":
                self.action_tree()
            elif command == "/logs":
                self.say("logs", f"Sesión: {self.session.path}\nGGUF: {getattr(self.local_model, 'log_path', 'sin arranque')}\nInstalación: {state_dir() / 'install'}\n"
                         "Los logs del arnés registran operaciones; los diarios del motor siguen siendo la fuente.")
            elif command == "/stop":
                await self.action_cancel()
            elif command == "/stars":
                if args[0] not in ("on", "off"):
                    raise ValueError("/stars on|off")
                self.stars_enabled = args[0] == "on"
            elif command == "/clear":
                self.query_one(RichLog).clear()
            elif command == "/quit":
                self.exit()
            else:
                raise ValueError("Comando desconocido. /help")
        except asyncio.CancelledError:
            self.say("operación", "Cancelada")
        except (OSError, ValueError, RuntimeError, IndexError, KeyError, TypeError, asyncio.TimeoutError) as e:
            self.say("error", str(e) or type(e).__name__, "#f0b783")
        finally:
            if self.active_task is task:
                self.active_task = None
            self.update_status()

    async def open_connection(self, value, name=None):
        value = profile(value)
        if value["mode"] == "local":
            self.cortex = self.connection = self.active_profile = None
            self.say("GGUF", "Cargando en CPU; /stop cancela. /logs muestra el registro de este intento.")
            cortex = await self.local_model.start(value["path"], server=value.get("server"),
                progress=lambda message: self.say("GGUF", message))
        else:
            cortex = Cortex(value["url"], value["model"], value.get("key_env"),
                "anthropic" if value["mode"] == "anthropic" else "openai", key_file=value.get("key_file"))
            await self.local_model.close()
        self.cortex, self.connection, self.active_profile = cortex, value, name
        self.say("neocórtex", f"{'Listo' if value['mode'] == 'local' else 'Configurado'}: {name or cortex.model}. "
                 + ("Escribe tu mensaje." if value["mode"] == "local" else "La API se comprueba al enviar texto."))

    async def on_unmount(self):
        await self.runner.stop()
        await self.local_model.close()
        for client in self.mcps.values():
            await client.close()
        self.session.close()
