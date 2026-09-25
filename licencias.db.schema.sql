-- Schema de Base de Datos para Sistema de Licencias
-- Ejecutar esto al inicializar el servidor

CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    nombre TEXT,
    telefono TEXT,
    fecha_registro TEXT NOT NULL,
    activo BOOLEAN DEFAULT 1
);

CREATE TABLE IF NOT EXISTS licencias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT UNIQUE NOT NULL,
    usuario_id INTEGER,
    email TEXT,
    device_id TEXT,
    fecha_inicio TEXT NOT NULL,
    fecha_expiracion TEXT NOT NULL,
    tipo_duracion INTEGER DEFAULT 30, -- 30, 90, 365 días
    activa BOOLEAN DEFAULT 1,
    fecha_creacion TEXT NOT NULL,
    fecha_validacion_ultima TEXT,
    usos INTEGER DEFAULT 0,
    FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
);

CREATE TABLE IF NOT EXISTS compras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER,
    email TEXT NOT NULL,
    licencia_id INTEGER,
    monto REAL NOT NULL,
    metodo_pago TEXT DEFAULT 'mercadopago',
    transaccion_id TEXT UNIQUE,
    estado TEXT DEFAULT 'pendiente', -- pendiente, completado, rechazado
    fecha_compra TEXT NOT NULL,
    fecha_procesamiento TEXT,
    FOREIGN KEY (usuario_id) REFERENCES usuarios (id),
    FOREIGN KEY (licencia_id) REFERENCES licencias (id)
);

CREATE TABLE IF NOT EXISTS validaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    licencia_codigo TEXT NOT NULL,
    dispositivo TEXT,
    fecha_validacion TEXT NOT NULL,
    resultado TEXT, -- valida, expirada, invalida
    ip_cliente TEXT,
    FOREIGN KEY (licencia_codigo) REFERENCES licencias (codigo)
);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL, -- generar_licencia, validar_licencia, pago_recibido, error
    detalles TEXT,
    fecha TEXT NOT NULL,
    ip TEXT
);

CREATE INDEX IF NOT EXISTS idx_licencia_codigo ON licencias(codigo);
CREATE INDEX IF NOT EXISTS idx_licencia_email ON licencias(email);
CREATE INDEX IF NOT EXISTS idx_licencia_expiracion ON licencias(fecha_expiracion);
CREATE INDEX IF NOT EXISTS idx_compra_email ON compras(email);
CREATE INDEX IF NOT EXISTS idx_compra_estado ON compras(estado);
