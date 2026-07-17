# Asistente TSF — bot de seguimiento (Discord)

Bot de seguimiento automático para los canales 1:1 de la mentoría TikTok Shop Formula.
Corre gratis en GitHub Actions. **No responde nunca a ningún alumno**: solo publica
follow-ups programados y avisa a @Mentor en #mentores cuando un alumno escribe.

## Qué hace

- **Cada ~30 min (replycheck):** revisa los canales 1:1. Si un alumno ha escrito y
  ningún mentor le ha contestado después, publica en #mentores:
  `🔔 @Mentor — Nombre ha escrito en su canal`. También lee los comandos de #mentores.
- **Cada día a las 09:00 España (followups):** elige hasta 3 alumnos (los más
  atrasados) y genera su mensaje de seguimiento con Gemini (ficha + historial del
  canal). Regla de tiempos: **7 días** si el último en hablar fuimos nosotros sin
  respuesta, **15 días** si el último fue el alumno. Cualquier mensaje humano en el
  canal resetea el reloj; los mensajes del bot no.
- **Modo borrador (actual):** los mensajes se publican SOLO en #mentores. Nadie
  recibe nada hasta cambiar a `live`.
- Si un alumno acumula 2 mensajes sin responder (en modo live), en vez de insistir
  publica alerta roja en #mentores pidiendo toque humano.

## Comandos (escribir en #mentores)

- `!pausa nombre` — pausa el seguimiento de ese alumno
- `!activa nombre` — lo reactiva
- `!estado` — lista próximos toques, pausados y quién está sin canal/sin entrar

## Puesta en marcha (5 minutos, una sola vez)

1. Descomprime esta carpeta en tu Mac.
2. Abre **Claude Code** dentro de la carpeta y pégale esto:

   > En esta carpeta está el Asistente TSF. Haz esto: 1) Comprueba que gh CLI está
   > autenticado con `gh auth status`; si no, guíame con `gh auth login`. 2) Crea un
   > repo PRIVADO llamado `tsf-asistente` y sube TODO el contenido de esta carpeta,
   > incluida la carpeta `.github`. 3) Configura dos Actions secrets con
   > `gh secret set DISCORD_TOKEN` y `gh secret set GEMINI_API_KEY`, pidiéndome
   > pegar cada valor sin mostrarlo en pantalla. 4) Lanza una prueba:
   > `gh workflow run "Asistente TSF" -f task=replycheck` y verifica con
   > `gh run watch` que termina en verde. 5) Dame la URL del repo.

3. Cuando Claude Code te pida los valores, pega el token del bot de Discord y la
   API key de Gemini.

## ⚠️ Habilitar la API de Gemini (30 segundos, pendiente)

Tu key es válida pero su proyecto de Google tiene la API de Gemini desactivada.
Entra aquí con tu cuenta de Google y pulsa **Habilitar**:

https://console.developers.google.com/apis/api/generativelanguage.googleapis.com/overview?project=615954707798

Espera 1-2 minutos y listo. Mientras no esté habilitada, el bot funciona igual con
mensajes de plantilla (marcados con ⚠️ en los borradores).

## Pasar de borrador a envío real

Edita `.github/workflows/asistente.yml` desde la web de GitHub (icono del lápiz) y
cambia la línea `MODE: draft` por `MODE: live`. Desde ese momento los follow-ups van
directos al canal de cada alumno. Para volver al modo borrador, deshaz el cambio.

## Notas de operación

- **Cambio de hora:** el cron va en UTC. En invierno (a partir de finales de
  octubre) cambia `0 7 * * *` por `0 8 * * *` para mantener las 09:00 España.
- **Cuota GitHub Actions:** el plan gratis da 2.000 min/mes en repos privados; este
  bot consume ~1.500. No añadas más workflows al repo.
- **Token de Discord:** si lo reseteas en el portal de desarrolladores, actualiza el
  secret `DISCORD_TOKEN` en GitHub (Settings → Secrets and variables → Actions).
- **Altas nuevas:** añade al alumno en `roster.json` (channel_id + user_id),
  su ficha en `fichas.json` y una entrada en `state.json`. O pídeselo a Claude.
- Los retrasos de 5-15 min en los crons de GitHub son normales.
