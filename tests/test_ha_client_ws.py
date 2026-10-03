"""HA-Client gegen einen nachgebauten HA-WebSocket-Server (aiohttp): Anmeldung,
subscribe_entities, Erstbestand, Aenderung, Abbruch -> Werte ungueltig, Wiederverbinden."""
import asyncio

from aiohttp import web

import ha_client
from ha_client import HAClient, Verbindungsdaten


async def _server(verbindungen: list):
    async def ws_handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_json({"type": "auth_required", "ha_version": "2026.10.0"})
        auth = await ws.receive_json()
        if auth.get("access_token") != "richtig":
            await ws.send_json({"type": "auth_invalid", "message": "falsch"})
            await ws.close()
            return ws
        await ws.send_json({"type": "auth_ok", "ha_version": "2026.10.0"})
        abo = await ws.receive_json()
        assert abo["type"] == "subscribe_entities"
        await ws.send_json({"id": abo["id"], "type": "result", "success": True, "result": None})
        await ws.send_json({"id": abo["id"], "type": "event", "event": {"a": {
            "sensor.netz": {"s": "100", "a": {"unit_of_measurement": "W"}, "lc": 1.0}}}})
        # HA buendelt manchmal mehrere Nachrichten in einer Liste
        await ws.send_json([{"id": abo["id"], "type": "event",
                             "event": {"c": {"sensor.netz": {"+": {"s": "250", "lc": 2.0}}}}}])
        verbindungen.append(abo["entity_ids"])
        await asyncio.sleep(0.2)
        await ws.close()   # Abbruch simulieren
        return ws

    app = web.Application()
    app.router.add_get("/api/websocket", ws_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, port


def test_verbinden_empfangen_abbruch_wiederverbinden(monkeypatch):
    monkeypatch.setattr(ha_client, "WARTEN_MIN_S", 0.05)

    async def ablauf():
        verbindungen, empfangen = [], []
        runner, port = await _server(verbindungen)
        client = HAClient(Verbindungsdaten(f"ws://127.0.0.1:{port}/api/websocket", "richtig"),
                          ["sensor.netz"], lambda eid, z, t: empfangen.append(None if z is None else z["s"]))
        task = asyncio.create_task(client.laufen())
        for _ in range(100):
            if len(verbindungen) >= 2:
                break
            await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await runner.cleanup()
        return verbindungen, empfangen

    verbindungen, empfangen = asyncio.run(ablauf())
    assert verbindungen[0] == ["sensor.netz"]
    assert len(verbindungen) >= 2, "nach Abbruch neu verbunden"
    # Erstbestand, Aenderung, dann None beim Abbruch, danach wieder Werte
    assert empfangen[:3] == ["100", "250", None]
    assert "100" in empfangen[3:]


def test_falscher_token():
    async def ablauf():
        runner, port = await _server([])
        client = HAClient(Verbindungsdaten(f"ws://127.0.0.1:{port}/api/websocket", "falsch"),
                          ["sensor.netz"], lambda *a: None)
        task = asyncio.create_task(client.laufen())
        await asyncio.sleep(0.3)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await runner.cleanup()
        return client

    client = asyncio.run(ablauf())
    assert client.verbunden is False
    assert "Anmeldung abgelehnt" in (client.letzter_fehler or "")
