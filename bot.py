#!/usr/bin/env python3
# Asistente TSF — seguimiento automático de alumnos en Discord.
# Tareas: replycheck (cada ~30 min) y followups (diaria 09:00 España).
# Reglas duras: el bot NUNCA responde a un alumno; solo publica el follow-up
# programado y avisa a @Mentor en #mentores cuando un alumno escribe.
import argparse, json, os, re, sys, time, unicodedata, urllib.error, urllib.request
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
API = "https://discord.com/api/v10"
GUILD = "1527224533122023456"
ROLE_MENTOR = "1527228554776150036"
CH_MENTORES = "1527228594604998779"
BOT_ID = "1527224967177961542"

TOKEN = os.environ["DISCORD_TOKEN"]
GKEY = os.environ.get("GEMINI_API_KEY", "")
MODE = os.environ.get("MODE", "draft")            # draft | live
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
DAILY_CAP = 3
INT_STUDENT = 15   # días si el último en hablar fue el alumno
INT_US = 7         # días si el último fuimos nosotros

# ---------- utilidades ----------

def jload(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return json.load(f)

def jsave(name, obj):
    with open(os.path.join(ROOT, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)

def now():
    return datetime.now(timezone.utc)

def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")

def disc(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    for _ in range(4):
        req = urllib.request.Request(API + path, data=data, method=method, headers={
            "Authorization": f"Bot {TOKEN}", "User-Agent": "AsistenteTSF/1.0",
            "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                txt = r.read().decode()
                return r.status, (json.loads(txt) if txt else {})
        except urllib.error.HTTPError as e:
            if e.code == 429:
                try:
                    wait = json.loads(e.read().decode()).get("retry_after", 2)
                except Exception:
                    wait = 2
                time.sleep(float(wait) + 0.5)
                continue
            return e.code, e.read().decode()[:300]
    return 429, "rate limited"

def post(channel_id, content):
    for chunk in split_chunks(content):
        st, r = disc("POST", f"/channels/{channel_id}/messages", {"content": chunk})
        if st != 200:
            print(f"POST_FAIL {channel_id} {st} {r}")
        time.sleep(0.6)

def split_chunks(text, limit=1900):
    if len(text) <= limit:
        return [text]
    out, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > limit:
            out.append(cur); cur = line
        else:
            cur = cur + "\n" + line if cur else line
    if cur:
        out.append(cur)
    return out

def fetch_after(channel_id, after_id):
    msgs = []
    cursor = after_id
    while True:
        st, batch = disc("GET", f"/channels/{channel_id}/messages?after={cursor}&limit=100")
        if st != 200 or not batch:
            break
        batch.sort(key=lambda m: int(m["id"]))
        msgs.extend(batch)
        cursor = batch[-1]["id"]
        if len(batch) < 100:
            break
    return msgs

def latest_id(channel_id):
    st, batch = disc("GET", f"/channels/{channel_id}/messages?limit=1")
    if st == 200 and batch:
        return batch[0]["id"]
    return "0"

def guild_people():
    """Devuelve (mentor_ids, member_ids)."""
    st, members = disc("GET", f"/guilds/{GUILD}/members?limit=1000")
    mentors, all_ids = set(), set()
    if st == 200:
        for m in members:
            uid = m.get("user", {}).get("id")
            if not uid:
                continue
            all_ids.add(uid)
            if ROLE_MENTOR in m.get("roles", []):
                mentors.add(uid)
    return mentors, all_ids

# ---------- generación ----------

RULES = (
    "Eres el Asistente TSF, el asistente del equipo de mentores de TikTok Shop "
    "Formula (Alex, Víctor y Ángel). Escribes UN mensaje de seguimiento a un "
    "alumno en su canal privado de Discord.\n"
    "REGLAS DURAS:\n"
    "- Español de España, tuteo, tono natural y cercano, cero corporativo.\n"
    "- Nada de exclamaciones dobles ni saludos tipo '¡Buenas!'. Casi sin "
    "exclamaciones; puedes alargar el saludo para sonar cercano (ej. 'Holaaa').\n"
    "- 4 a 8 líneas. Los puntos pendientes con guiones.\n"
    "- Es una revisión automática periódica: SOLO repasas lo que los mentores ya "
    "le dijeron (ficha e historial). PROHIBIDO dar consejo técnico nuevo, "
    "prometer nada, hablar de dinero, precios, pagos o plazos, o mencionar a "
    "otros alumnos por nombre.\n"
    "- Cierra preguntando en qué punto está con cada punto, dejando abierta la "
    "opción de que al final haya decidido hacer otra cosa, y ofreciendo ayuda: "
    "si necesita cualquier cosa extra que lo cuente y avisarás a Alex, Víctor "
    "y Ángel.\n"
    "- No inventes datos. Si no hay historial, usa solo la ficha.\n"
    "- Devuelve SOLO el texto del mensaje, sin comillas ni explicaciones."
)

INTRO = ("Holaaa {nombre}, estamos trabajando para que en ningún momento "
         "estéis sin seguimiento. Por eso hemos creado un sistema de revisión "
         "automática que te irá escribiendo por aquí de vez en cuando.\n\n"
         "Eso sí, tu respuesta no la va a contestar el asistente: cuando "
         "escribas, les llega el aviso a Alex, Víctor y Ángel y te responden "
         "ellos personalmente. Simplemente así podemos llevar el seguimiento "
         "de manera más sencilla.\n\n")

def gemini(prompt):
    if not GKEY:
        return None
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.6, "maxOutputTokens": 600},
    }).encode()
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        data=body, method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": GKEY})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            d = json.loads(r.read().decode())
            return d["candidates"][0]["content"]["parts"][0]["text"].strip()
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode()[:400]
        except Exception:
            detail = ""
        print(f"GEMINI_FAIL: {e} {detail}")
        return None
    except Exception as e:
        print(f"GEMINI_FAIL: {e}")
        return None

def render_history(channel_id, entry, mentor_ids, limit=30):
    st, batch = disc("GET", f"/channels/{channel_id}/messages?limit={limit}")
    if st != 200 or not batch:
        return ""
    lines = []
    for m in sorted(batch, key=lambda x: int(x["id"])):
        a = m["author"]
        c = (m.get("content") or "").strip()
        if not c:
            continue
        if a.get("bot"):
            who = "Asistente"
        elif a["id"] == entry.get("user_id"):
            who = "Alumno"
        elif a["id"] in mentor_ids:
            who = "Mentor"
        else:
            who = "Alumno"
        lines.append(f"{who}: {c[:400]}")
    return "\n".join(lines[-40:])

def validate(text):
    if not text or len(text) > 1400:
        return False
    banned = ["€", "precio", "pagar", "cuota", "factur", "mentor\u00eda a", "oferta"]
    low = norm(text)
    if any(norm(b) in low for b in banned):
        return False
    return True

def template_message(nombre, ficha):
    pts = ficha.get("pendientes", [])
    body = f"Holaaa {nombre}, paso a hacerte la revisión por aquí.\n\n"
    body += "De la última revisión con los mentores hablamos de:\n"
    for p in pts[:4]:
        body += f"– {p}\n"
    body += ("\n¿En qué punto estás con cada uno? Si al final has decidido "
             "hacer otra cosa o necesitas cualquier cosa extra, cuéntamelo "
             "también. En cuanto respondas les aviso a Alex, Víctor y Ángel "
             "para que le echen un ojo a lo nuevo. Y dime si tienes alguna duda.")
    return body

def build_message(key, entry, ficha, state_s, mentor_ids):
    nombre = entry["nombre"]
    first = not state_s.get("intro_sent")
    history = render_history(entry["channel_id"], entry, mentor_ids) if entry.get("channel_id") else ""
    prompt = (RULES + "\n\nFICHA DEL ALUMNO (" + nombre + "):\n"
              + json.dumps(ficha, ensure_ascii=False)
              + "\n\nHISTORIAL RECIENTE DEL CANAL (puede estar vacío):\n"
              + (history or "(vacío)")
              + "\n\nEscribe ahora el mensaje de seguimiento para " + nombre + ".")
    text = gemini(prompt)
    if not validate(text):
        text = template_message(nombre, ficha)
        text = "⚠️ _(plantilla — Gemini no disponible)_\n" + text if MODE == "draft" else text
    if first:
        core = re.sub(r"^hola[^\n]*\n+", "", text, flags=re.I)
        text = INTRO.format(nombre=nombre) + core
    return text

# ---------- tareas ----------

def task_replycheck(roster, state, fichas):
    mentor_ids, member_ids = guild_people()
    pendientes = []
    for key, entry in roster["students"].items():
        ch = entry.get("channel_id")
        if not ch:
            continue
        s = state["students"].setdefault(key, {})
        cur = s.get("cursor")
        if cur is None:
            s["cursor"] = latest_id(ch)
            continue
        msgs = fetch_after(ch, cur)
        if not msgs:
            continue
        student_wrote, last_human = False, None
        for m in msgs:
            a = m["author"]
            s["cursor"] = m["id"]
            if a.get("bot"):
                continue
            s["last_human_ts"] = m["timestamp"]
            if a["id"] in mentor_ids:
                s["last_speaker"] = "mentor"
                last_human = "mentor"
            else:
                s["last_speaker"] = "student"
                s["unanswered"] = 0
                s["alerted"] = False
                student_wrote = True
                last_human = "student"
        if student_wrote and last_human == "student":
            pendientes.append((entry["nombre"], ch))
    # Un solo aviso combinado por pasada; si nadie ha escrito, no se envía nada.
    if len(pendientes) == 1:
        n, ch = pendientes[0]
        post(CH_MENTORES, f"🔔 <@&{ROLE_MENTOR}> — {n} ha escrito en su canal (<#{ch}>)")
    elif pendientes:
        lineas = "\n".join(f"• {n} (<#{c}>)" for n, c in pendientes)
        post(CH_MENTORES, f"🔔 <@&{ROLE_MENTOR}> — han escrito en su canal:\n{lineas}")
    handle_commands(roster, state)

def handle_commands(roster, state):
    cur = state.get("cmd_cursor")
    if cur is None:
        state["cmd_cursor"] = latest_id(CH_MENTORES)
        return
    for m in fetch_after(CH_MENTORES, cur):
        state["cmd_cursor"] = m["id"]
        if m["author"].get("bot"):
            continue
        c = (m.get("content") or "").strip()
        if not c.startswith("!"):
            continue
        parts = c.split(None, 1)
        cmd = parts[0].lower()
        arg = norm(parts[1]) if len(parts) > 1 else ""
        if cmd in ("!pausa", "!activa") and arg:
            hit = None
            for key, entry in roster["students"].items():
                if arg in norm(entry["nombre"]) or arg in norm(key):
                    hit = key; break
            if hit:
                s = state["students"].setdefault(hit, {})
                s["paused"] = (cmd == "!pausa")
                s["pause_reason"] = "manual"
                post(CH_MENTORES, f"✅ {roster['students'][hit]['nombre']} "
                     f"{'pausado/a' if cmd == '!pausa' else 'activado/a'}.")
            else:
                post(CH_MENTORES, f"❓ No encuentro a \"{parts[1]}\" en el roster.")
        elif cmd == "!estado":
            post(CH_MENTORES, estado_report(roster, state))

def next_due(s):
    base = ts(s.get("last_human_ts", "2026-06-26T00:00:00+00:00"))
    interval = INT_STUDENT if s.get("last_speaker") == "student" else INT_US
    last_action = s.get("last_draft") if MODE == "draft" else s.get("last_sent")
    eff = max(base, ts(last_action)) if last_action else base
    return eff + timedelta(days=interval)

def estado_report(roster, state):
    _, member_ids = guild_people()
    act, paus, sin = [], [], []
    for key, e in sorted(roster["students"].items()):
        s = state["students"].get(key, {})
        if not e.get("channel_id") or (e.get("user_id") and e["user_id"] not in member_ids) or not e.get("user_id"):
            if not e.get("channel_id") or not e.get("user_id"):
                sin.append(e["nombre"]); continue
        if s.get("paused"):
            paus.append(f"{e['nombre']} ({s.get('pause_reason','')})"); continue
        act.append(f"{e['nombre']}: próximo toque {next_due(s).date()}")
    return ("📋 **Estado del seguimiento** (modo " + MODE + ")\n"
            + "\n".join("• " + a for a in act)
            + "\n\n⏸️ Pausados: " + (", ".join(paus) or "—")
            + "\n🚪 Sin canal o sin entrar al servidor: " + (", ".join(sin) or "—"))

def task_followups(roster, state, fichas):
    task_replycheck(roster, state, fichas)
    mentor_ids, member_ids = guild_people()
    due = []
    for key, e in roster["students"].items():
        s = state["students"].setdefault(key, {})
        if not e.get("channel_id") or not e.get("user_id"):
            continue
        if e["user_id"] not in member_ids:
            continue
        if s.get("paused") or s.get("alerted"):
            continue
        nd = next_due(s)
        if now() >= nd:
            due.append(((now() - nd).total_seconds(), key, e))
    due.sort(reverse=True)
    sent = 0
    for _, key, e in due:
        if sent >= DAILY_CAP:
            break
        s = state["students"][key]
        if MODE == "live" and s.get("unanswered", 0) >= 2:
            post(CH_MENTORES, f"🔴 <@&{ROLE_MENTOR}> — {e['nombre']} lleva 2 mensajes "
                 f"del asistente sin responder (<#{e['channel_id']}>). Toque humano.")
            s["alerted"] = True
            continue
        text = build_message(key, e, fichas.get(key, {}), s, mentor_ids)
        stamp = now().isoformat()
        if MODE == "draft":
            post(CH_MENTORES, f"📝 **BORRADOR → {e.get('channel_name', key)}** "
                 f"_(no enviado — modo borrador)_\n\n{text}")
            s["last_draft"] = stamp
        else:
            s["unanswered"] = (s.get("unanswered", 0) + 1
                               if s.get("last_sent") and s.get("last_speaker") != "student"
                               else 1)
            post(e["channel_id"], text)
            s["last_sent"] = stamp
            s["intro_sent"] = True
            s["last_speaker"] = "mentor"
            s["last_human_ts"] = stamp
        sent += 1
        time.sleep(1)
    print(f"followups {MODE}: {sent} enviados/borradores")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", choices=["replycheck", "followups"], required=True)
    args = ap.parse_args()
    roster, state, fichas = jload("roster.json"), jload("state.json"), jload("fichas.json")
    if args.task == "replycheck":
        task_replycheck(roster, state, fichas)
    else:
        task_followups(roster, state, fichas)
    jsave("state.json", state)
    print("done", args.task)

if __name__ == "__main__":
    main()
