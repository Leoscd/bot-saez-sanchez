# Bot por WhatsApp (Cloud API de Meta)

El mismo asistente que en Telegram, por WhatsApp. El DT le escribe al número del bot y el bot responde:

- **Arma el reporte del día** con las fotos, audios y textos que manda el DT, según el formato estándar, y al
  confirmar devuelve el PDF.
- **Cuenta cómo viene la obra** cuando se lo piden, por ejemplo a un DT que hace un reemplazo: avance contra
  cronograma, atrasos, notas abiertas, materiales pendientes, últimos reportes y fotos.

El bot casi nunca escribe primero. La única excepción es el recordatorio de las 18 h para quien dejó un reporte
a medias. Como el DT ya le escribió ese día, entra en la ventana de 24 h y no necesita plantilla.

## Cómo funciona

```
DT ──► WhatsApp ──► Meta ──► webhook en el VPS (python main.py whatsapp) ──► modelo de IA + herramientas
                                                     │
DT ◄── WhatsApp ◄── Meta ◄── API de WhatsApp ◄───────┘   respuesta, botones, PDF y fotos
```

- Solo atiende a los números de `data/equipo.json`, y a cada uno en sus obras habilitadas. Un reemplazo se
  habilita con fecha de vencimiento.
- Comprueba la firma de cada mensaje con la clave secreta de la app: si no viene de Meta, lo descarta.
- Procesa los mensajes de cada persona de a uno, en orden, así varias fotos juntas no se pisan.

## 1. Meta: lo que se configura en developers.facebook.com

En la app, caso de uso "Conectar en WhatsApp":

1. **Paso 1 > Destinatario > Administrar lista de números de teléfono.** Cargar los teléfonos que van a probar
   (hasta 5 con el número de prueba). A cada uno le llega un código por WhatsApp.
2. **Paso 1 > Phone Number ID.** Va a `WHATSAPP_PHONE_NUMBER_ID`.
3. **Token.** Para la primera prueba alcanza el del botón "Generar token" (dura 24 h). Para dejarlo andando:
   Business Manager > Configuración del negocio > Usuarios del sistema > crear uno (rol administrador),
   asignarle la app y la cuenta de WhatsApp, y generar un token sin vencimiento con los permisos
   `whatsapp_business_messaging` y `whatsapp_business_management`. Va a `WHATSAPP_TOKEN`.
4. **Configuración de la app > Básica > Clave secreta de la app.** Va a `WHATSAPP_APP_SECRET`.
5. **Paso 2 > Configurar webhooks**, con el bot ya corriendo en el VPS (punto 2):
   - URL de devolución de llamada: `https://<tu-servidor>/whatsapp/webhook`
   - Token de verificación: el mismo texto que pusiste en `WHATSAPP_VERIFY_TOKEN`
   - "Verificar y guardar", y después suscribir el campo **messages**.

El token y la clave secreta no se mandan por chat ni se suben al repositorio: van solo en el `.env` del servidor.

## 2. VPS: instalar y dejar corriendo

```bash
adduser --system --group --home /opt/obra-bot obrabot
git clone https://github.com/Leoscd/bot-saez-sanchez.git /opt/obra-bot
cd /opt/obra-bot
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env        # OPENAI_API_KEY y las variables WHATSAPP_*
.venv/bin/python scripts/seed_demo.py --historial   # obras demo; para obras reales, data/obras.json
chown -R obrabot:obrabot /opt/obra-bot
cp deploy/obra-bot-whatsapp.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now obra-bot-whatsapp
journalctl -u obra-bot-whatsapp -f       # tiene que decir "Bot de WhatsApp en el puerto 8085"
```

El bot escucha solo en `127.0.0.1:8085`. Meta exige HTTPS, así que hace falta algo delante que lo publique:

- **Con Tailscale Funnel:** `tailscale funnel --bg --https=10000 http://127.0.0.1:8085`. La URL queda
  `https://<nombre-del-vps>.ts.net:10000/whatsapp/webhook`. Funnel solo permite los puertos 443, 8443 y 10000.
  Si el puerto ya publica otra cosa, el bot va en una ruta propia:
  `tailscale funnel --bg --https=10000 --set-path=/whatsapp http://127.0.0.1:8085`. Funnel le saca el
  `/whatsapp` antes de pasar el pedido, así que en el `.env` va `WHATSAPP_RUTA=/webhook`. La URL para Meta
  sigue siendo `https://<nombre-del-vps>.ts.net:10000/whatsapp/webhook`.
- **Con Caddy y un dominio:** `bot.dominio.com { reverse_proxy 127.0.0.1:8085 }`. La URL queda
  `https://bot.dominio.com/whatsapp/webhook`.

Comprobar desde afuera: `curl https://<tu-servidor>/salud` tiene que responder `ok`.

## 3. Quién puede usarlo

```bash
cd /opt/obra-bot
sudo -u obrabot .venv/bin/python scripts/equipo.py alta "+54 9 381 555-0000" "Martín Gómez"
sudo -u obrabot .venv/bin/python scripts/equipo.py asignar "+54 9 381 555-0000" casa-lomas
# Reemplazo por una semana:
sudo -u obrabot .venv/bin/python scripts/equipo.py asignar "+54 9 381 555-0000" local-mate-de-luna --hasta 2026-11-20
sudo -u obrabot .venv/bin/python scripts/equipo.py listar
```

El bot relee el archivo solo, sin reiniciar. Si alguien no habilitado escribe, le contesta que pida el alta a la oficina.

## 4. Probar

Desde un teléfono habilitado, escribirle al número del bot:

1. "hola": si tiene más de una obra, aparece la lista para elegir.
2. Mandar 3 fotos y un audio contando el día.
3. "cerrar": el bot pide lo que falta y muestra los botones **Confirmar y enviar** / **Corregir algo**.
4. Confirmar: llega el PDF.
5. Con otro número habilitado como reemplazo: "estoy haciendo un reemplazo, contame cómo viene la obra".

Otras palabras: "obra" cambia de obra y "ayuda" muestra qué puede hacer.

## Recordatorio fuera de las 24 h (opcional)

Si un DT deja un reporte abierto y pasaron más de 24 h desde su último mensaje, WhatsApp solo deja mandar una
plantilla aprobada. Crear en el Administrador de WhatsApp una plantilla de categoría **Utilidad**, idioma
español (Argentina):

> Hola, el reporte de hoy de {{1}} sigue abierto. Escribí "cerrar" cuando quieras y te digo qué falta.

Cuando esté aprobada, poner su nombre en `WHATSAPP_PLANTILLA_RECORDATORIO`.

## Con el número de prueba

- Solo llega a los 5 teléfonos de la lista.
- Con los celulares argentinos, WhatsApp informa el número con el 9 (549…), pero la lista de prueba a veces
  lo guarda con el 15. El bot prueba las variantes solo y recuerda la que funcionó.
- Para usarlo con todos los DT hace falta el número propio del estudio y la verificación del negocio en Meta.

## Pruebas automáticas

```bash
.venv/bin/pip install pytest
.venv/bin/python -m pytest tests
```

Simulan Meta, el modelo de IA y el clima. No gastan créditos ni mandan mensajes reales.
