# Asistente TSF — guía de operación para Claude Code

Bot de seguimiento de la mentoría TikTok Shop Formula (Discord). El dueño (Alex)
opera el bot HABLANDO con Claude Code; Claude ejecuta las acciones lanzando
workflows de GitHub Actions de este repo. La red de las sesiones de Claude
bloquea discord.com, así que TODA acción de Discord se ejecuta vía Actions.

## Regla de oro
El bot NUNCA responde a un alumno. Solo publica follow-ups programados y avisa
a los mentores en #mentores. No dar consejo técnico nuevo, no hablar de dinero,
no mencionar a otros alumnos.

## Cómo ejecutar acciones (Claude: usa mcp github actions_run_trigger)
- Workflow `asistente.yml` ("Asistente TSF"): tareas programadas.
  - replycheck cada 30 min: aviso COMBINADO en #mentores si algún alumno
    escribió (un solo mensaje; si nadie escribió, no envía nada) + comandos
    !pausa/!activa/!estado.
  - followups diarios SIEMPRE a las 09:00 hora de España (dos crons 7/8 UTC
    con guardia TZ Europe/Madrid): hasta 3 alumnos más atrasados.
- Workflow `ops.yml` ("Ops TSF"), inputs action/args:
  - create_cuentas_channel — crea el canal 📋┃cuentas-de-alumnos y fija cuentas.md
  - draft_followups, args="antonio,maxys" — borradores a #mentores
  - send_followups,  args="antonio,maxys" — ENVÍO REAL a esos alumnos
  - post_mentores,   args="texto" — mensaje a #mentores

## Estilo de los mensajes (fijado por Alex, 2026-07-17)
- Tono natural y cercano, español de España, tuteo. Casi sin exclamaciones,
  NUNCA "¡...!" dobles ni "¡Buenas!". Saludo tipo "Holaaa Antonio,".
- Sin faltas de ortografía. Sin emojis en los mensajes a alumnos.
- La explicación del sistema (revisión automática, responden Alex/Víctor/Ángel
  en persona) va SOLO en el PRIMER mensaje a cada alumno (INTRO en bot.py).
  Los siguientes son follow-up directo.
- Cierre siempre con: en qué punto está cada punto + opción "si al final has
  decidido hacer otra cosa" + "si necesitas cualquier cosa extra" + se avisará
  a Alex, Víctor y Ángel.

## Flujo acordado con Alex
1. Los primeros envíos reales requieren su OK previo sobre el borrador.
2. Tras su OK: lanzar send_followups y cambiar MODE a "live" en asistente.yml.
3. MODE está en asistente.yml (draft = solo #mentores, live = envío real).

## Datos
- roster.json (alumnos/canales), fichas.json (situación y pendientes),
  state.json (cursores y tiempos; lo escribe el propio bot), cuentas.md
  (lista de cuentas TikTok para el canal fijo).
- IDs del servidor dentro de bot.py. Secrets del repo: DISCORD_TOKEN,
  GEMINI_API_KEY (Actions). NUNCA escribir tokens en el repo: es público.

## Pendiente conocido
- Gemini API desactivada en el proyecto de Google del dueño; hasta activarla,
  los mensajes usan la plantilla de bot.py (template_message).
