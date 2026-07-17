#!/usr/bin/env python3
# Ops TSF — acciones puntuales lanzadas a mano o por Claude Code
# vía workflow_dispatch (workflow "Ops TSF").
#
# Acciones:
#   create_cuentas_channel        crea/actualiza el canal 📋┃cuentas-de-alumnos
#                                 y fija el mensaje con las cuentas (cuentas.md)
#   send_followups  args=a,b,c    genera y ENVÍA el follow-up a esos alumnos
#                                 (claves del roster separadas por comas)
#   draft_followups args=a,b,c    igual pero publica el borrador en #mentores
#   post_mentores   args=texto    publica un mensaje en #mentores
#   find_member     args=q1,q2    busca miembros del servidor por nombre
#   create_student_channel        args="clave:Nombre[:user_id];clave2:..."
#                                 crea el canal privado 🔒┃nombre (permisos
#                                 copiados de un canal 1:1 existente) y
#                                 actualiza roster.json y state.json
import argparse, time
from urllib.parse import quote

from bot import (disc, post, jload, jsave, build_message, guild_people, now,
                 GUILD, CH_MENTORES, ROLE_MENTOR)

CUENTAS_CHANNEL_NAME = "cuentas-de-alumnos"
CATEGORY_MENTORIA = "1527228588687101982"
TEMPLATE_CHANNEL = "1527343966716952586"   # 🔒┃antonio, referencia de permisos


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
                # @everyone puede leer pero no escribir; mentores sí escriben
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
                             "draft_followups", "post_mentores",
                             "find_member", "create_student_channel"])
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
    elif a.action == "find_member":
        find_member(a.args)
    elif a.action == "create_student_channel":
        create_student_channel(a.args)
    print("done", a.action)


if __name__ == "__main__":
    main()
