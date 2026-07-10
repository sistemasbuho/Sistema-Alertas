# Spike OpenWA — fallback de mensajería WhatsApp

**Objetivo:** validar que [OpenWA](https://github.com/rmyndharis/OpenWA) (gateway
self-hosted, NestJS + whatsapp-web.js/Baileys, MIT) puede reemplazar/respaldar a
WHAPI. Si pasa, se habilita como fallback (`WHATSAPP_PROVIDERS=whapi,openwa`) y
más adelante puede invertirse la cadena sin cambios de código.

## Estado

- [x] Provider `apps/whatsapp/providers/openwa.py` implementado (deshabilitado
      sin `OPENWA_BASE_URL`; nunca participa en producción).
- [x] Servicio compose bajo `profiles: ["spike"]` (no arranca con `docker compose up`).
- [ ] Checklist de validación (abajo).

## Cómo levantar

```bash
docker compose --profile spike up openwa
# UI/API en http://localhost:3300
```

## Checklist de validación (timebox 0.5–1 día)

1. **Sesión**: crear sesión y vincular un **número dedicado de pruebas**
   escaneando el QR (nunca el número de producción: la automatización de
   WhatsApp Web viola ToS y hay riesgo de baneo — igual que con WHAPI).
2. **Grupos**: enumerar grupos vía la API REST y verificar el formato de JID
   (`...@g.us`). ⚠️ Una cuenta WA distinta ve ids de grupo distintos a los
   guardados en `Proyecto.codigo_acceso` (obtenidos con la cuenta WHAPI). Si el
   spike pasa, decidir: campo `codigo_acceso_openwa` en Proyecto o mapping en
   settings.
3. **Envío**: mandar mensajes de prueba a un grupo sandbox con
   `OPENWA_BASE_URL=http://localhost:3300 OPENWA_SEND_PATH=<ruta real>`.
   Ajustar `send_path`/payload del provider según la API real de la versión
   desplegada (el provider asume `{chatId, text, session}` estilo WAHA; validar).
4. **Formato**: confirmar que el markdown de WhatsApp (`*bold*`, `_italic_`) y
   emojis llegan igual que por WHAPI.
5. **Métricas**: latencia por mensaje, estabilidad de la sesión tras reinicio
   del contenedor (volumen `openwa_sessions`), comportamiento con 20+ mensajes
   seguidos (rate limit).

## Criterio go/no-go

- GO: envío estable a grupo sandbox + sesión persistente + latencia < 5s.
  → habilitar `WHATSAPP_PROVIDERS=whapi,openwa` en staging.
- NO-GO: sesiones caídas frecuentes o baneo del número de prueba.
  → queda WHAPI único; reevaluar más adelante.
