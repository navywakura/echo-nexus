"""One source for command help, completion, and the documentation."""
COMMANDS = [
    ("/devtest", "[list|all|ID]", "Ejecutar desarrollo; list muestra también informes sellados"),
    ("/backend", "MANIFEST.json", "Conectar el catálogo local de pruebas ECHO"),
    ("/connect", "api URL MODEL [KEY_ENV|@KEY_FILE]", "Conectar neocórtex con API compatible con chat completions"),
    ("/connect", "anthropic URL MODEL KEY_ENV", "Conectar neocórtex con la API Messages"),
    ("/connect", "local /ruta/modelo.gguf [--server EXE]", "Cargar GGUF con llama-server en localhost"),
    ("/connections", "[list]", "Listar conexiones guardadas sin leer claves"),
    ("/connections", "save NOMBRE", "Guardar la conexión actual sin copiar su clave"),
    ("/connections", "use NOMBRE", "Conectar un perfil guardado"),
    ("/connections", "remove NOMBRE", "Eliminar un perfil guardado"),
    ("/connections", "default NOMBRE|off", "Elegir conexión automática al iniciar"),
    ("/disconnect", "", "Desconectar el neocórtex y descargar el GGUF lanzado"),
    ("/agents", "", "Detectar agentes instalados sin iniciarlos"),
    ("/mcp", "connect NAME -- COMMAND [ARGS]", "Conectar un servidor MCP por stdio"),
    ("/mcp", "tools NAME", "Ver herramientas y sintaxis JSON"),
    ("/mcp", "call NAME TOOL {\"arg\":\"value\"}", "Invocar explícitamente una herramienta MCP"),
    ("/mcp", "close NAME", "Cerrar un servidor MCP iniciado por el arnés"),
    ("/watch", "PATH.jsonl|off", "Seguir decisiones existentes, en solo lectura"),
    ("/image", "PATH.png", "Mostrar una imagen en la terminal"),
    ("/tree", "", "Expandir o restaurar el panel de telemetría"),
    ("/demo", "", "Probar el visor con una animación sintética etiquetada"),
    ("/stop", "", "Cancelar la prueba o solicitud iniciada en esta TUI"),
    ("/logs", "", "Mostrar ubicación de los logs de sesión e instalación"),
    ("/stars", "on|off", "Activar o desactivar la animación decorativa"),
    ("/clear", "", "Limpiar el panel de conversación"),
    ("/help", "[COMMAND]", "Consultar comandos, descripciones y sintaxis"),
    ("/quit", "", "Salir y cerrar los procesos propiedad del arnés"),
]


def matches(prefix):
    return [c for c in COMMANDS if (c[0] + " " + c[1]).startswith(prefix) or c[0].startswith(prefix)]
