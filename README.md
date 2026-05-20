# SomnoStop — Sistema Inteligente de Detección de Somnolencia

**Integrantes:** Cruz Valadez Montserrat · Gómez Juárez Alan Fabricio  
**Materia:** Sistemas Programables — TecNM / Instituto Tecnológico de León  
**Proyecto:** SomnoStop

---

## Objetivo General

Desarrollar un sistema IoT de seguridad vial que detecte señales de somnolencia en conductores en tiempo real. La ESP32 recopila datos de sensores y la ESP32-CAM captura imágenes del rostro del conductor; toda la información viaja por MQTT hacia un servidor Python que ejecuta un modelo de IA (MediaPipe FaceMesh) para clasificar el estado del conductor y activar alertas físicas y sonoras de forma inmediata.

---

## Arquitectura del Sistema

```
ESP32 / ESP32-CAM              Broker MQTT              Servidor Python (IA)
──────────────────             ───────────              ────────────────────
Sensores (distancia,     →     somnostop/         →     procesador_ia.py
 botón, inclinación)           sensores/datos            lógica de decisión
Cámara (frame JPEG)      →     camara/frame       →     ia_processor.py
                                                         MediaPipe FaceMesh

Actuadores               ←     actuadores/        ←     comandos de alerta
(buzzer, LEDs,                  alarma
 solenoide)                     estado
                                solenoide
                                ia/resultado
```

---

## Estructura del Repositorio

```
SomnoStop/
├── esp32/
│   ├── dispositivos.py       # HAL — SensorBox y ActuatorBox (E1)
│   ├── main.py               # Programa principal del microcontrolador
│   └── camara_mqtt.py        # Captura y publicación de frames por MQTT (E3)
├── servidor/
│   ├── procesador_ia.py      # Suscriptor MQTT + lógica de decisión (E2)
│   ├── ia_processor.py       # Pipeline de IA con MediaPipe FaceMesh (E3)
│   ├── prueba_estatica.py    # Validación estática del modelo sin MQTT (E3)
│   └── firebase_logger.py    # Registro de eventos en Firebase (E4)
├── interfaz/
│   └── index.html            # Dashboard web con control remoto (E4)
├── .gitignore                # Excluye firebase_cred.json del repositorio
└── README.md
```

---

## Arquitectura de Software — HAL (E1)

Se implementó una Capa de Abstracción de Hardware en `dispositivos.py` con las clases `SensorBox` y `ActuatorBox`. El `main.py` interactúa con el hardware **exclusivamente** a través de estos métodos, sin usar primitivas de MicroPython directamente (`machine.Pin`, `machine.PWM`, etc.).

---

## Matriz de Tópicos MQTT (E2 + E3)

| Tópico | Dirección | Contenido |
|:---|:---|:---|
| `somnostop/sensores/datos` | ESP32 → PC | JSON con distancia, botón, inclinación |
| `somnostop/camara/frame` | ESP32-CAM → PC | Imagen JPEG codificada en base64 |
| `somnostop/ia/resultado` | PC → ESP32 | JSON con estado, EAR y MAR |
| `somnostop/actuadores/solenoide` | PC → ESP32 | `"ON"` / `"OFF"` |
| `somnostop/actuadores/estado` | PC → ESP32 | `"OK"` / `"PELIGRO"` |
| `somnostop/actuadores/alarma` | PC → ESP32 | Frecuencia del buzzer en Hz |

---

## Modelo de Inteligencia Artificial (E3)

| Campo | Detalle |
|:---|:---|
| **Librería** | MediaPipe FaceMesh (Google) |
| **Tipo de modelo** | Detección de landmarks faciales (478 puntos) |
| **Tipo de predicción** | Clasificación del estado del conductor |
| **Clases posibles** | `NORMAL` · `SOMNOLIENTO` · `PELIGRO` · `SIN_ROSTRO` |
| **Precisión (buena iluminación)** | ~92% |
| **Precisión (luz baja / interior auto)** | ~78% |
| **Latencia por frame** | ~80–120 ms en CPU sin GPU |
| **Resolución de entrada** | 320×240 px (QVGA desde ESP32-CAM) |

### Métricas de detección

**EAR — Eye Aspect Ratio:** mide la apertura de los ojos.
```
EAR = (dist_vertical_1 + dist_vertical_2) / (2 × dist_horizontal)
EAR < 0.25  →  ojo cerrado (alerta)
EAR ≈ 0.30  →  ojo abierto (normal)
```

**MAR — Mouth Aspect Ratio:** mide la apertura de la boca.
```
MAR = distancia_vertical / distancia_horizontal
MAR > 0.55  →  bostezo detectado
```

Si cualquiera de las dos condiciones se mantiene durante **3 frames consecutivos**, el sistema emite la alerta de PELIGRO.

---

## Instalación de Dependencias

```bash
pip install mediapipe opencv-python paho-mqtt numpy
```

---

## Ejecución

### 1. Prueba estática del modelo (sin ESP32 ni MQTT)
```bash
python servidor/prueba_estatica.py
```
Usa la webcam de la PC para validar que MediaPipe detecta correctamente el rostro y las métricas EAR/MAR. Genera `resultados_prueba.json` como evidencia.

### 2. Pipeline completo con MQTT
```bash
# Terminal 1 — Broker
mosquitto -v

# Terminal 2 — Servidor de IA
python servidor/ia_processor.py

# Terminal 3 — Monitor (opcional)
mosquitto_sub -t "somnostop/#" -v
```

---

## Análisis Individual

### Montserrat Cruz Valadez — E2

**Problema:** Inestabilidad en la conexión Wi-Fi de la ESP32 al publicar en 4 tópicos simultáneamente, provocando cierres de socket inesperados.

**Solución:** Se empaquetó toda la telemetría en un único JSON y se configuró un delay no bloqueante de 1 segundo para estabilizar el tráfico hacia el broker.

**Conclusión:** La implementación de MQTT permitió desacoplar la lógica de procesamiento pesado (Python) del control en tiempo real (ESP32). El manejo de payloads JSON es fundamental para optimizar el ancho de banda en sistemas de seguridad vial.

---

### Montserrat Cruz Valadez — E3

**Problema:** La latencia entre la captura del frame en la ESP32-CAM y el procesamiento en el servidor superaba los 4 segundos, haciendo que el modelo analizara imágenes desactualizadas del conductor y que las alertas llegaran con retraso crítico.

**Solución:** Se redujo la resolución de SVGA a QVGA y se aumentó la compresión JPEG , reduciendo el tamaño del frame y la latencia a menos de 500 ms.

**Conclusión:** La arquitectura correcta para IoT queda demostrada: el microcontrolador actúa como sensor/actuador y el servidor como cerebro. La ESP32 no puede correr MediaPipe debido a sus limitaciones de RAM (~520 KB) y ausencia de FPU eficiente.

---

### Alan Fabricio Gómez Juárez — E2

**Problema:** Los actuadores no reaccionaban a los comandos de Python porque los mensajes llegaban como cadenas de texto (`"ON"`) y la HAL esperaba valores booleanos, generando errores de tipo silenciosos.

**Solución:** Se robusteció el callback en la ESP32 para hacer parseo y validación de tipos antes de invocar los métodos de la HAL, garantizando que el hardware reciba los parámetros correctos.

**Conclusión:** El uso de una HAL fue crítico; permitió realizar pruebas de comunicación sin riesgo de dañar los actuadores físicos. Una arquitectura por capas es la mejor defensa contra errores de integración en sistemas complejos.

---

### Alan Fabricio Gómez Juárez — E3

**Problema:** Los valores de EAR y MAR llegaban como cadenas dentro del JSON, causando que las comparaciones con los umbrales fallaran silenciosamente sin activar alertas.

**Solución:** Se añadió conversión explícita de tipos con `float()` al extraer valores del JSON en la ESP32, y se validó que el servidor Python siempre publique valores numéricos nativos mediante `round()` antes de serializar.

**Conclusión:** La comunicación JSON entre MicroPython y CPython requiere validación estricta de tipos en ambos extremos. Probar el modelo con imágenes estáticas antes de conectar la ESP32 aceleró enormemente la detección de errores sin depender del hardware físico.

---

## Firebase Realtime Database (E4)

### Tipos de eventos registrados

| Tipo | Nodo en Firebase | Campos |
|:---|:---|:---|
| Telemetría | `/eventos/telemetria/` | distancia, boton, inclinacion, timestamp |
| Alerta IA | `/eventos/alertas_ia/` | estado, ear, mar, timestamp |
| Actuador | `/eventos/actuadores/` | actuador, valor, origen, timestamp |
| Estado actual | `/estado_actual/` | online, estado_conductor, sensores, timestamp |

Cada registro incluye timestamp en formato `YYYY-MM-DD HH:MM:SS`. Las imágenes de la ESP32-CAM **no se almacenan** — solo las métricas procesadas (EAR, MAR, estado), garantizando la privacidad del conductor.

### Dashboard Web (interfaz/index.html)

| Funcionalidad | Descripción |
|:---|:---|
| Estado del conductor | NORMAL / SOMNOLIENTO / PELIGRO con color y animación |
| Métricas EAR y MAR | Valores en tiempo real con barras de progreso |
| Sensores | Distancia, botón hombre muerto e inclinación |
| Historial de alertas | Últimas 5 alertas con severidad y hora |
| Control remoto | Toggle para LEDs, Solenoide y Buzzer desde la interfaz |
| Indicador Online | Estado de conexión del sistema en tiempo real |

---

## Instalación de Dependencias (E4)

```bash
pip install firebase-admin
```

Colocar el archivo `firebase_cred.json` (credenciales de Firebase) en la raíz del proyecto. Este archivo está en `.gitignore` y **no se sube al repositorio**.

---

## Ejecución completa del sistema

```bash
# Terminal 1 — Broker MQTT
mosquitto -v

# Terminal 2 — Servidor de IA
python servidor/ia_processor.py

# Terminal 3 — Firebase Logger
python servidor/firebase_logger.py

# Terminal 4 — Dashboard web
cd interfaz
python -m http.server 8080
# Abrir en Chrome: http://localhost:8080
```

---

## Análisis Individual — E4

### Montserrat Cruz Valadez — E4

**Problema:** Al abrir el `index.html` directamente desde el explorador de archivos (protocolo `file://`), Firebase bloqueaba la conexión por restricciones de CORS, mostrando "Conectando..." aunque las reglas de la base de datos eran correctas.

**Solución:** Se identificó que Firebase requiere que el archivo se sirva desde un servidor HTTP. Se usó el servidor integrado de Python para servir la interfaz desde `localhost`, resolviendo el problema sin instalar software adicional.

**Conclusión:** Firebase Realtime Database permite crear interfaces reactivas con muy poco código, ya que el SDK maneja automáticamente la sincronización. Sin embargo, es fundamental configurar correctamente el entorno de desarrollo y las reglas de seguridad desde el inicio.

---

### Alan Fabricio Gómez Juárez — E4

**Problema:** Al intentar subir `firebase_cred.json` a GitHub, el push fue bloqueado automáticamente por el sistema Secret Scanning de GitHub, ya que el archivo contiene credenciales reales de Google Cloud Service Account.

**Solución:** Se eliminó el archivo del historial de Git con `git rm --cached firebase_cred.json` y se creó `.gitignore` para ignorarlo permanentemente. El archivo permanece local para que Python pueda usarlo, pero no se expone en el repositorio público.

**Conclusión:** La gestión de credenciales es crítica en proyectos IoT con servicios en la nube. Nunca deben subirse archivos de credenciales a repositorios públicos. El uso de `.gitignore` es la práctica correcta para mantener seguridad sin afectar la funcionalidad.
