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
import argparse, time

from bot import (disc, post, jload, jsave, build_message, guild_people, now,
                 GUILD, CH_MENTORES, ROLE_MENTOR)

CUENTAS_CHANNEL_NAME = "cuentas-de-alumnos"


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
                             "draft_followups", "post_mentores"])
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
    print("done", a.action)


if __name__ == "__main__":
    main()
