"""Base de datos SQLite: usuarios, reportes, fotos, avances, stock, pedidos y notas."""
import json
import sqlite3
from contextlib import contextmanager

from . import config

# usuarios.usuario_id, reportes.dt_id y reportes.chat_id guardan el id del usuario en su canal:
# el número de Telegram o "wa:<teléfono>" para WhatsApp.
ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    usuario_id TEXT PRIMARY KEY,
    nombre TEXT,
    chat_id INTEGER,
    obra_id TEXT,
    obra_fecha TEXT
);
CREATE TABLE IF NOT EXISTS reportes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    obra_id TEXT NOT NULL,
    fecha TEXT NOT NULL,
    dt_id INTEGER NOT NULL,
    dt_nombre TEXT,
    chat_id INTEGER,
    estado TEXT NOT NULL DEFAULT 'borrador',
    numero INTEGER,
    datos TEXT NOT NULL,
    historial TEXT NOT NULL,
    UNIQUE (obra_id, fecha, dt_id)
);
CREATE TABLE IF NOT EXISTS fotos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reporte_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    hora TEXT,
    descripcion TEXT,
    id_tarea TEXT
);
CREATE TABLE IF NOT EXISTS avance_tareas (
    obra_id TEXT, id_tarea TEXT, fecha TEXT, pct REAL,
    PRIMARY KEY (obra_id, id_tarea, fecha)
);
CREATE TABLE IF NOT EXISTS stock (
    obra_id TEXT, material TEXT, fecha TEXT, cantidad REAL, unidad TEXT,
    PRIMARY KEY (obra_id, material, fecha)
);
CREATE TABLE IF NOT EXISTS pedidos (
    obra_id TEXT, id_tarea TEXT, material TEXT, estado TEXT,
    fecha TEXT, fecha_entrega TEXT,
    PRIMARY KEY (obra_id, id_tarea, material)
);
CREATE TABLE IF NOT EXISTS notas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    obra_id TEXT, tipo TEXT, numero INTEGER, fecha TEXT,
    emisor TEXT, destinatario TEXT, asunto TEXT, texto TEXT,
    plazo TEXT, estado TEXT DEFAULT 'pendiente',
    impacto_materiales INTEGER DEFAULT 0,
    reporte_id INTEGER
);
"""


@contextmanager
def conexion():
    con = sqlite3.connect(config.DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def inicializar():
    with conexion() as con:
        columnas = [c["name"] for c in con.execute("PRAGMA table_info(usuarios)")]
        if "telegram_id" in columnas:
            # Bases anteriores a WhatsApp: la clave era un entero y no admite "wa:<teléfono>"
            con.executescript(
                "ALTER TABLE usuarios RENAME TO usuarios_telegram;"
                "CREATE TABLE usuarios (usuario_id TEXT PRIMARY KEY, nombre TEXT, chat_id INTEGER,"
                " obra_id TEXT, obra_fecha TEXT);"
                "INSERT INTO usuarios SELECT telegram_id, nombre, chat_id, obra_id, obra_fecha FROM usuarios_telegram;"
                "DROP TABLE usuarios_telegram;"
            )
        con.executescript(ESQUEMA)


# --- usuarios -------------------------------------------------------------

def guardar_usuario(usuario_id, nombre: str, chat_id):
    with conexion() as con:
        con.execute(
            "INSERT INTO usuarios (usuario_id, nombre, chat_id) VALUES (?, ?, ?) "
            "ON CONFLICT(usuario_id) DO UPDATE SET nombre = excluded.nombre, chat_id = excluded.chat_id",
            (str(usuario_id), nombre, chat_id),
        )


def obtener_usuario(usuario_id):
    with conexion() as con:
        return con.execute("SELECT * FROM usuarios WHERE usuario_id = ?", (str(usuario_id),)).fetchone()


def fijar_obra(usuario_id, obra_id: str, fecha: str):
    with conexion() as con:
        con.execute(
            "UPDATE usuarios SET obra_id = ?, obra_fecha = ? WHERE usuario_id = ?",
            (obra_id, fecha, str(usuario_id)),
        )


# --- reportes -------------------------------------------------------------

def obtener_reporte(obra_id: str, fecha: str, dt_id: int):
    with conexion() as con:
        return con.execute(
            "SELECT * FROM reportes WHERE obra_id = ? AND fecha = ? AND dt_id = ?",
            (obra_id, fecha, dt_id),
        ).fetchone()


def obtener_reporte_por_id(reporte_id: int):
    with conexion() as con:
        return con.execute("SELECT * FROM reportes WHERE id = ?", (reporte_id,)).fetchone()


def crear_reporte(obra_id, fecha, dt_id, dt_nombre, chat_id, datos) -> int:
    with conexion() as con:
        cur = con.execute(
            "INSERT INTO reportes (obra_id, fecha, dt_id, dt_nombre, chat_id, datos, historial) "
            "VALUES (?, ?, ?, ?, ?, ?, '[]')",
            (obra_id, fecha, dt_id, dt_nombre, chat_id, json.dumps(datos, ensure_ascii=False)),
        )
        return cur.lastrowid


def actualizar_reporte(reporte_id, estado, numero, datos, historial):
    with conexion() as con:
        con.execute(
            "UPDATE reportes SET estado = ?, numero = ?, datos = ?, historial = ? WHERE id = ?",
            (estado, numero, json.dumps(datos, ensure_ascii=False),
             json.dumps(historial, ensure_ascii=False), reporte_id),
        )


def borradores_abiertos(fecha: str):
    with conexion() as con:
        return con.execute(
            "SELECT * FROM reportes WHERE fecha = ? AND estado = 'borrador'", (fecha,)
        ).fetchall()


def reportes_de_obra(obra_id: str, hasta_fecha: str, limite: int):
    """Reportes de la obra hasta una fecha, del más nuevo al más viejo."""
    with conexion() as con:
        return con.execute(
            "SELECT * FROM reportes WHERE obra_id = ? AND fecha <= ? ORDER BY fecha DESC, id DESC LIMIT ?",
            (obra_id, hasta_fecha, limite),
        ).fetchall()


def siguiente_numero(obra_id: str) -> int:
    with conexion() as con:
        fila = con.execute(
            "SELECT COALESCE(MAX(numero), 0) + 1 AS n FROM reportes WHERE obra_id = ?", (obra_id,)
        ).fetchone()
        return fila["n"]


# --- fotos ----------------------------------------------------------------

def agregar_foto(reporte_id, path, hora, descripcion) -> int:
    with conexion() as con:
        cur = con.execute(
            "INSERT INTO fotos (reporte_id, path, hora, descripcion) VALUES (?, ?, ?, ?)",
            (reporte_id, path, hora, descripcion),
        )
        return cur.lastrowid


def vincular_foto(foto_id, reporte_id, id_tarea, descripcion) -> bool:
    with conexion() as con:
        cur = con.execute(
            "UPDATE fotos SET id_tarea = ?, descripcion = ? WHERE id = ? AND reporte_id = ?",
            (id_tarea, descripcion, foto_id, reporte_id),
        )
        return cur.rowcount > 0


def fotos_de_reporte(reporte_id):
    with conexion() as con:
        return con.execute(
            "SELECT * FROM fotos WHERE reporte_id = ? ORDER BY id", (reporte_id,)
        ).fetchall()


def fotos_de_obra(obra_id: str, id_tarea: str | None, limite: int):
    """Últimas fotos de la obra (opcionalmente de una tarea), con la fecha del reporte."""
    filtro, params = ("AND f.id_tarea = ?", [id_tarea]) if id_tarea else ("", [])
    with conexion() as con:
        return con.execute(
            "SELECT f.*, r.fecha, r.dt_nombre FROM fotos f JOIN reportes r ON r.id = f.reporte_id "
            f"WHERE r.obra_id = ? {filtro} ORDER BY r.fecha DESC, f.id DESC LIMIT ?",
            [obra_id, *params, limite],
        ).fetchall()


def foto_de_obra(foto_id: int, obra_id: str):
    with conexion() as con:
        return con.execute(
            "SELECT f.* FROM fotos f JOIN reportes r ON r.id = f.reporte_id WHERE f.id = ? AND r.obra_id = ?",
            (foto_id, obra_id),
        ).fetchone()


# --- avances, stock y pedidos ---------------------------------------------

def guardar_avance(obra_id, id_tarea, fecha, pct):
    with conexion() as con:
        con.execute(
            "INSERT OR REPLACE INTO avance_tareas VALUES (?, ?, ?, ?)", (obra_id, id_tarea, fecha, pct)
        )


def ultimos_avances(obra_id, hasta_fecha) -> dict:
    with conexion() as con:
        filas = con.execute(
            "SELECT id_tarea, pct FROM avance_tareas a WHERE obra_id = ? AND fecha = ("
            " SELECT MAX(fecha) FROM avance_tareas b"
            " WHERE b.obra_id = a.obra_id AND b.id_tarea = a.id_tarea AND b.fecha <= ?)",
            (obra_id, hasta_fecha),
        ).fetchall()
        return {f["id_tarea"]: f["pct"] for f in filas}


def guardar_stock(obra_id, material, fecha, cantidad, unidad):
    with conexion() as con:
        con.execute(
            "INSERT OR REPLACE INTO stock VALUES (?, ?, ?, ?, ?)",
            (obra_id, material.lower(), fecha, cantidad, unidad),
        )


def ultimo_stock(obra_id, material):
    with conexion() as con:
        return con.execute(
            "SELECT * FROM stock WHERE obra_id = ? AND material = ? ORDER BY fecha DESC LIMIT 1",
            (obra_id, material.lower()),
        ).fetchone()


def guardar_pedido(obra_id, id_tarea, material, estado, fecha, fecha_entrega):
    with conexion() as con:
        con.execute(
            "INSERT OR REPLACE INTO pedidos VALUES (?, ?, ?, ?, ?, ?)",
            (obra_id, id_tarea, material.lower(), estado, fecha, fecha_entrega),
        )


def obtener_pedido(obra_id, id_tarea, material):
    with conexion() as con:
        return con.execute(
            "SELECT * FROM pedidos WHERE obra_id = ? AND id_tarea = ? AND material = ?",
            (obra_id, id_tarea, material.lower()),
        ).fetchone()


def pedidos_de_obra(obra_id: str, estados: tuple[str, ...]):
    marcas = ", ".join("?" * len(estados))
    with conexion() as con:
        return con.execute(
            f"SELECT * FROM pedidos WHERE obra_id = ? AND estado IN ({marcas}) ORDER BY fecha",
            (obra_id, *estados),
        ).fetchall()


# --- notas de obra --------------------------------------------------------

def crear_nota(obra_id, tipo, fecha, emisor, destinatario, asunto, texto, plazo,
               impacto_materiales, reporte_id) -> tuple[int, int]:
    with conexion() as con:
        numero = con.execute(
            "SELECT COALESCE(MAX(numero), 0) + 1 FROM notas WHERE obra_id = ? AND tipo = ?",
            (obra_id, tipo),
        ).fetchone()[0]
        cur = con.execute(
            "INSERT INTO notas (obra_id, tipo, numero, fecha, emisor, destinatario, asunto, texto,"
            " plazo, impacto_materiales, reporte_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (obra_id, tipo, numero, fecha, emisor, destinatario, asunto, texto, plazo,
             int(impacto_materiales), reporte_id),
        )
        return cur.lastrowid, numero


def notas_abiertas(obra_id):
    with conexion() as con:
        return con.execute(
            "SELECT * FROM notas WHERE obra_id = ? AND estado = 'pendiente' ORDER BY fecha, id",
            (obra_id,),
        ).fetchall()


def notas_de_obra(obra_id):
    with conexion() as con:
        return con.execute("SELECT * FROM notas WHERE obra_id = ? ORDER BY fecha, id", (obra_id,)).fetchall()


def notas_de_reporte(reporte_id):
    with conexion() as con:
        return con.execute(
            "SELECT * FROM notas WHERE reporte_id = ? ORDER BY id", (reporte_id,)
        ).fetchall()
