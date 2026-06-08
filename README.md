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
├── requirements.txt          # Dependencias del proyecto
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
pip install -r requirements.txt
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
mosquitto -v -c mosquitto.conf

# Terminal 2 — Servidor de IA
python servidor/ia_processor.py

# Terminal 3 — Firebase Logger
python servidor/firebase_logger.py

# Terminal 4 — Dashboard web
cd interfaz
python -m http.server 8080
# Abrir en Chrome: http://localhost:8080

# Terminal 5 — Monitor (opcional)
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

**Solución:** Se redujo la resolución de SVGA a QVGA y se aumentó la compresión JPEG, reduciendo el tamaño del frame y la latencia a menos de 500 ms.

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

---

## Análisis Individual — E5 (Prototipado Físico)

### Montserrat Cruz Valadez — E5

**Problema:** Durante las pruebas del prototipo físico, la IP del broker MQTT cambiaba dinámicamente cada vez que se reiniciaba la sesión WiFi de la PC, ya que el router asignaba una nueva dirección al equipo. Esto provocaba que los ESP32 no pudieran conectarse al servidor y el sistema fallara al inicio de cada sesión de pruebas.

**Solución:** Se estableció un procedimiento de verificación previo a cada sesión: ejecutar `ipconfig` en la PC para confirmar la IP actual del adaptador WiFi, y actualizar los archivos `main.py`, `camara_mqtt.py` e `ia_processor.py` con la IP correcta antes de encender los dispositivos. Se documentó este proceso para garantizar la reproducibilidad de las demos.

**Conclusión:** La integración de un sistema IoT en un entorno real expone vulnerabilidades que no aparecen durante el desarrollo aislado, como la asignación dinámica de IPs. Para un producto final se debería configurar una IP estática en el router o migrar a un broker MQTT en la nube (HiveMQ, AWS IoT Core) para eliminar esta dependencia. La etapa de prueba física requiere tanta preparación y verificación como la etapa de desarrollo de software.

---

### Alan Fabricio Gómez Juárez — E5

**Problema:** Al conectar el solenoide de 12V con el MOSFET IRFZ44N en la protoboard, el solenoide no se activaba a pesar de que el GPIO27 enviaba la señal correcta. El diagnóstico reveló que el GND de la batería 12V y el GND del ESP32 (alimentado por USB a 5V) no estaban unidos en un punto común, rompiendo el circuito de retorno del MOSFET y dejando la señal de Gate sin referencia de tierra válida.

**Solución:** Se unieron ambos GND en el mismo riel de la protoboard, estableciendo la referencia de voltaje común entre las dos fuentes de alimentación. Se verificó también la orientación correcta del diodo 1N4007 de protección (cátodo al +12V, ánodo al Drain del MOSFET) para prevenir daños por la corriente inversa generada cuando el solenoide se desactiva.

**Conclusión:** La gestión de múltiples fuentes de alimentación en un mismo circuito es uno de los errores más frecuentes en proyectos con actuadores de potencia. El GND común es un requisito fundamental, no opcional. Un circuito correcto en software pero con un error de referencia de tierra en hardware resulta completamente inoperante. Esta experiencia refuerza la importancia de revisar el esquema eléctrico completo antes de realizar la primera prueba con componentes de potencia.

---

## Análisis Individual — E6 (Entrega Final)

### Montserrat Cruz Valadez — E6

**Problema:** Al realizar la demostración final del sistema completo, el modelo de IA presentaba falsos positivos frecuentes — clasificando al conductor como SOMNOLIENTO o PELIGRO incluso con los ojos abiertos — cuando la iluminación del entorno era baja o lateral. Esto generaba activaciones innecesarias del buzzer y el solenoide durante la demo.

**Solución:** Se ajustaron los umbrales de detección (UMBRAL_EAR de 0.25 a 0.22 y FRAMES_PELIGRO de 3 a 4 frames consecutivos) para reducir la sensibilidad en condiciones de iluminación variable, manteniendo la funcionalidad de detección real sin comprometer la demostración.

**Conclusión Final:** SomnoStop logró demostrar de forma exitosa que la combinación de IoT, MQTT e IA open source permite construir sistemas de seguridad vial funcionales con hardware accesible. El proyecto integró conocimientos de redes, programación embebida, visión por computadora y bases de datos en la nube en un producto cohesivo. El mayor aprendizaje fue que en sistemas IoT, la robustez de la comunicación y la correcta gestión del entorno son tan importantes como la precisión del modelo de IA.

---

### Alan Fabricio Gómez Juárez — E6

**Problema:** Al preparar el prototipo para la entrega final, el circuito en protoboard presentaba inestabilidad en las conexiones del MPU6050 (sensor de cabeceo) y el HC-SR04 (sensor de distancia) debido al movimiento de los cables durante el transporte y montaje. Los jumpers se desconectaban fácilmente, causando errores en la lectura de sensores durante las pruebas.

**Solución:** Se aseguró cada jumper crítico con cinta aislante en los puntos de conexión más propensos a desconectarse, y se reorganizó el cableado de la protoboard agrupando los cables por función (alimentación, señal, GND) para reducir el desorden y facilitar la identificación de conexiones durante la demo.

**Conclusión Final:** Este proyecto demostró que el diseño de software bien estructurado (HAL, MQTT, arquitectura por capas) puede sobrevivir incluso a las limitaciones del hardware temporal en protoboard. Sin embargo, la experiencia confirmó que para un producto comercial confiable, la transición a PCB soldada es indispensable — no como requisito estético sino como necesidad de ingeniería para garantizar la integridad de las conexiones en condiciones de uso real. SomnoStop cumplió su objetivo: detectar somnolencia en tiempo real y activar alertas físicas de forma automática, cerrando el ciclo completo Sensor → IA → Actuador → Nube.
