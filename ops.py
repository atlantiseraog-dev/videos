#!/usr/bin/env python3
# Ops TSF — acciones puntuales lanzadas a mano o por Claude Code
# vía workflow_dispatch (workflow "Ops TSF").
#
# Acciones:
#   create_cuentas_channel        crea/actualiza el canal 📋┃cuentas-de-alumnos
#   send_followups  args=a,b,c    genera y ENVÍA el follow-up a esos alumnos
#   draft_followups args=a,b,c    igual pero publica el borrador en #mentores
#   post_mentores   args=texto    publica un mensaje en #mentores
#   post_general    args=texto    publica un mensaje en #chat-general
#   find_member     args=q1,q2    busca miembros del servidor por nombre
#   create_student_channel        args="clave:Nombre[:user_id];..." crea canal 1:1
#   audit_members                 comprueba servidor + rol VIP por alumno
#   assign_vip      args=a,b|""   da el rol VIP (vacío = a todos los que falte)
#   toggle_pause    args=clave:on|off[:razón];clave2:...  (varios con ';')
#   test_gemini                   llamada de prueba a la API de Gemini
#   list_mentors                  lista quién tiene el rol @Mentor
#   list_unknown                  miembros del servidor que NO están en el roster
#   send_outbox                   envía cada mensaje de outbox.json a su alumno
import argparse, time
from urllib.parse import quote

from bot import (disc, post, jload, jsave, build_message, guild_people, now,
                 GUILD, CH_MENTORES, ROLE_MENTOR)

CUENTAS_CHANNEL_NAME = "cuentas-de-alumnos"
CATEGORY_MENTORIA = "1527228588687101982"
TEMPLATE_CHANNEL = "1527343966716952586"   # 🔒┃antonio, referencia de permisos
ROLE_VIP = "1527228556260937849"           # rol Alumno VIP (acceso a canales generales)
CH_GENERAL = "1527228575546347612"         # canal chat-general


def find_channel(name_contains):
    st, chans = disc("GET", f"/guilds/{GUILD}/channels")
    if st != 200:
        return None
    for c in chans:
        if name_contains in c.get("name", ""):
            return c
    return None


def create_cuentas_channel(_args):
    ch = find_channel(CUENTAS_CHANNEL_NAME)
    if ch:
        ch_id = ch["id"]
        print(f"canal ya existe: {ch_id}")
    else:
        st, c = disc("POST", f"/guilds/{GUILD}/channels", {
            "name": f"📋┃{CUENTAS_CHANNEL_NAME}",
            "type": 0,
            "permission_overwrites": [
                {"id": GUILD, "type": 0, "deny": "2048"},
                {"id": ROLE_MENTOR, "type": 0, "allow": "2048"},
            ]})
        if st not in (200, 201):
            print(f"FAIL crear canal {st} {c}")
            return
        ch_id = c["id"]
        print(f"canal creado: {ch_id}")
    with open("cuentas.md", encoding="utf-8") as f:
        text = f.read().strip()
    st, msg = disc("POST", f"/channels/{ch_id}/messages", {"content": text})
    if st == 200:
        disc("PUT", f"/channels/{ch_id}/pins/{msg['id']}")
        print("mensaje de cuentas publicado y fijado")
    else:
        print(f"FAIL publicar cuentas {st} {msg}")


def find_member(args):
    for q in [x.strip() for x in args.split(",") if x.strip()]:
        st, res = disc("GET", f"/guilds/{GUILD}/members/search?query={quote(q)}&limit=10")
        if st != 200:
            print(f"FAIL busqueda '{q}': {st} {res}")
            continue
        print(f"— resultados para '{q}': {len(res)}")
        for m in res:
            u = m.get("user", {})
            print(f"   id={u.get('id')} username={u.get('username')} "
                  f"global_name={u.get('global_name')} nick={m.get('nick')}")


def list_unknown(_args):
    """Miembros del servidor que NO son bots, NO son mentores y NO están en el
    roster (por user_id). Sirve para detectar altas nuevas sin fichar."""
    roster = jload("roster.json")
    known = {e.get("user_id") for e in roster["students"].values() if e.get("user_id")}
    st, members = disc("GET", f"/guilds/{GUILD}/members?limit=1000")
    if st != 200:
        print(f"FAIL listar miembros {st} {members}")
        return
    n = 0
    for m in members:
        u = m.get("user", {})
        uid = u.get("id")
        if not uid or u.get("bot"):
            continue
        if ROLE_MENTOR in m.get("roles", []) or uid in known:
            continue
        n += 1
        vip = "VIP:si" if ROLE_VIP in m.get("roles", []) else "VIP:NO"
        print(f"NUEVO/DESCONOCIDO: id={uid} username={u.get('username')} "
              f"global_name={u.get('global_name')} nick={m.get('nick')} {vip}")
    print(f"total desconocidos: {n}")


def create_student_channel(args):
    st, tpl = disc("GET", f"/channels/{TEMPLATE_CHANNEL}")
    role_overwrites, member_tpl = [], None
    if st == 200:
        for o in tpl.get("permission_overwrites", []):
            if int(o.get("type", 0)) == 0:
                role_overwrites.append({"id": o["id"], "type": 0,
                                        "allow": o.get("allow", "0"),
                                        "deny": o.get("deny", "0")})
            elif member_tpl is None:
                member_tpl = o
    roster, state = jload("roster.json"), jload("state.json")
    for spec in [s.strip() for s in args.split(";") if s.strip()]:
        parts = spec.split(":")
        if len(parts) < 2:
            print(f"skip '{spec}': formato clave:Nombre[:user_id]")
            continue
        key, nombre = parts[0].strip(), parts[1].strip()
        uid = parts[2].strip() if len(parts) > 2 and parts[2].strip() else None
        existing = roster["students"].get(key, {})
        if existing.get("channel_id"):
            print(f"skip {key}: ya tiene canal {existing['channel_id']}")
            continue
        overwrites = list(role_overwrites)
        if uid:
            if member_tpl:
                overwrites.append({"id": uid, "type": 1,
                                   "allow": member_tpl.get("allow", "3072"),
                                   "deny": member_tpl.get("deny", "0")})
            else:
                overwrites.append({"id": uid, "type": 1, "allow": "3072", "deny": "0"})
        name = f"🔒┃{nombre.split()[0].lower()}"
        st, c = disc("POST", f"/guilds/{GUILD}/channels", {
            "name": name, "type": 0, "parent_id": CATEGORY_MENTORIA,
            "permission_overwrites": overwrites})
        if st not in (200, 201):
            print(f"FAIL crear canal {key}: {st} {c}")
            continue
        roster["students"][key] = {
            "nombre": existing.get("nombre", nombre),
            "channel_id": c["id"], "channel_name": name,
            "user_id": uid or existing.get("user_id")}
        s = state["students"].setdefault(key, {})
        s.setdefault("last_human_ts", now().isoformat())
        s.setdefault("last_speaker", "mentor")
        s.setdefault("intro_sent", False)
        s.setdefault("unanswered", 0)
        s.setdefault("paused", False)
        print(f"canal creado para {nombre}: {c['id']} (user_id={uid or '—'})")
        time.sleep(1)
    jsave("roster.json", roster)
    jsave("state.json", state)


def audit_members(_args):
    roster = jload("roster.json")
    st, members = disc("GET", f"/guilds/{GUILD}/members?limit=1000")
    if st != 200:
        print(f"FAIL listar miembros {st} {members}")
        return
    by_id = {m["user"]["id"]: m for m in members if m.get("user")}
    for key, e in sorted(roster["students"].items()):
        uid = e.get("user_id")
        if not uid:
            print(f"{key}: SIN user_id vinculado (no se puede comprobar)")
            continue
        m = by_id.get(uid)
        if not m:
            print(f"{key}: NO está en el servidor (user_id {uid})")
            continue
        roles = m.get("roles", [])
        vip = "VIP:si" if ROLE_VIP in roles else "VIP:NO"
        canal = e.get("channel_id") or "SIN-CANAL"
        print(f"{key}: {m['user'].get('username')} {vip} canal={canal} roles={roles}")


def assign_vip(args):
    roster = jload("roster.json")
    keys = [k.strip() for k in args.split(",") if k.strip()] or list(roster["students"].keys())
    st, members = disc("GET", f"/guilds/{GUILD}/members?limit=1000")
    by_id = {m["user"]["id"]: m for m in members if m.get("user")} if st == 200 else {}
    for key in keys:
        e = roster["students"].get(key)
        uid = e.get("user_id") if e else None
        if not uid or uid not in by_id:
            continue
        if ROLE_VIP in by_id[uid].get("roles", []):
            print(f"{key}: ya tenía VIP")
            continue
        st2, r = disc("PUT", f"/guilds/{GUILD}/members/{uid}/roles/{ROLE_VIP}")
        ok = st2 in (200, 204)
        print(f"{key}: rol VIP {'ASIGNADO' if ok else f'FAIL {st2} {r}'}")
        time.sleep(0.5)


def toggle_pause(args):
    """args = "clave:on[:razón]" o "clave:off". Varios separados por ';'."""
    state = jload("state.json")
    for spec in [x.strip() for x in args.split(";") if x.strip()]:
        parts = spec.split(":")
        key = parts[0].strip()
        mode = (parts[1] if len(parts) > 1 else "off").strip()
        s = state["students"].setdefault(key, {})
        s["paused"] = (mode == "on")
        if mode == "on":
            s["pause_reason"] = parts[2].strip() if len(parts) > 2 else "manual"
        else:
            s.pop("pause_reason", None)
        print(f"{key}: paused={s['paused']}")
    jsave("state.json", state)


def list_mentors(_args):
    st, members = disc("GET", f"/guilds/{GUILD}/members?limit=1000")
    if st != 200:
        print(f"FAIL listar miembros {st} {members}")
        return
    n = 0
    for m in members:
        if ROLE_MENTOR in m.get("roles", []):
            u = m.get("user", {})
            n += 1
            print(f"MENTOR: {u.get('username')} (nombre visible: {u.get('global_name')}) id={u.get('id')}")
    print(f"total con rol Mentor: {n}")


def test_gemini(_args):
    from bot import gemini
    r = gemini("Responde únicamente con la palabra: hola")
    if r:
        print(f"GEMINI OK: {r[:200]}")
    else:
        print("GEMINI NO DISPONIBLE (el error GEMINI_FAIL sale justo encima)")


def send_outbox(_args):
    """Envía cada mensaje de outbox.json (dict clave->texto) al canal del alumno,
    marca el estado como enviado y VACÍA el buzón para no reenviar."""
    roster, state = jload("roster.json"), jload("state.json")
    try:
        outbox = jload("outbox.json")
    except Exception:
        outbox = {}
    if not isinstance(outbox, dict) or not outbox:
        print("outbox vacío, nada que enviar")
        return
    sent = []
    for key, text in outbox.items():
        e = roster["students"].get(key)
        if not e or not e.get("channel_id"):
            print(f"skip {key}: sin canal")
            continue
        if not text or not str(text).strip():
            print(f"skip {key}: mensaje vacío")
            continue
        post(e["channel_id"], text)
        s = state["students"].setdefault(key, {})
        stamp = now().isoformat()
        s["last_sent"] = stamp
        s["intro_sent"] = True
        s["last_speaker"] = "mentor"
        s["last_human_ts"] = stamp
        s["unanswered"] = 1
        s["paused"] = False
        print(f"ENVIADO a {e['nombre']} ({key})")
        sent.append(key)
        time.sleep(1)
    jsave("state.json", state)
    jsave("outbox.json", {})
    print(f"outbox enviado: {len(sent)} -> {sent}")


def _followups(args, live):
    keys = [k.strip() for k in args.split(",") if k.strip()]
    roster, state, fichas = jload("roster.json"), jload("state.json"), jload("fichas.json")
    mentor_ids, _ = guild_people()
    for key in keys:
        e = roster["students"].get(key)
        if not e or not e.get("channel_id"):
            print(f"skip {key}: no está en el roster o no tiene canal")
            continue
        s = state["students"].setdefault(key, {})
        text = build_message(key, e, fichas.get(key, {}), s, mentor_ids)
        stamp = now().isoformat()
        if live:
            post(e["channel_id"], text)
            s["last_sent"] = stamp
            s["intro_sent"] = True
            s["last_speaker"] = "mentor"
            s["last_human_ts"] = stamp
            s["unanswered"] = max(1, s.get("unanswered", 0) + 1) if s.get("last_sent") else 1
            print(f"ENVIADO a {e['nombre']}")
        else:
            post(CH_MENTORES, f"📝 **BORRADOR → {e.get('channel_name', key)}** "
                 f"_(no enviado)_\n\n{text}")
            s["last_draft"] = stamp
            print(f"borrador publicado en #mentores: {e['nombre']}")
        time.sleep(1)
    jsave("state.json", state)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--action", required=True,
                    choices=["create_cuentas_channel", "send_followups",
                             "draft_followups", "post_mentores", "post_general",
                             "find_member", "create_student_channel",
                             "audit_members", "assign_vip", "toggle_pause",
                             "test_gemini", "list_mentors", "list_unknown",
                             "send_outbox"])
    ap.add_argument("--args", default="")
    a = ap.parse_args()
    if a.action == "create_cuentas_channel":
        create_cuentas_channel(a.args)
    elif a.action == "send_followups":
        _followups(a.args, live=True)
    elif a.action == "draft_followups":
        _followups(a.args, live=False)
    elif a.action == "post_mentores":
        post(CH_MENTORES, a.args)
    elif a.action == "post_general":
        post(CH_GENERAL, a.args)
    elif a.action == "find_member":
        find_member(a.args)
    elif a.action == "create_student_channel":
        create_student_channel(a.args)
    elif a.action == "audit_members":
        audit_members(a.args)
    elif a.action == "assign_vip":
        assign_vip(a.args)
    elif a.action == "toggle_pause":
        toggle_pause(a.args)
    elif a.action == "test_gemini":
        test_gemini(a.args)
    elif a.action == "list_mentors":
        list_mentors(a.args)
    elif a.action == "list_unknown":
        list_unknown(a.args)
    elif a.action == "send_outbox":
        send_outbox(a.args)
    print("done", a.action)


if __name__ == "__main__":
    main()
