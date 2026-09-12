# Dobot Magician - Controlador en Python para Ubuntu / Linux

Este proyecto proporciona un entorno modular, seguro y listo para producción para controlar el brazo robótico **Dobot Magician** en **Ubuntu** usando Python 3.

---

## 🚀 Características

- **Control Cartesiano y Articular:** Movimientos absolutos (`move_to`) y relativos (`move_rel`), homing (`home`) y lectura en tiempo real de coordenadas y articulaciones (`get_pose`).
- **Modos PTP Configurables:** Soporte para movimiento lineal (`MOVL_XYZ`) y articular (`MOVJ_XYZ`).
- **Dibujo con Marcador y Trayectorias Suaves:** Módulo de dibujo para trazos vectoriales sobre papel, generador geométrico (caritas felices, círculos, arcos), control de cota de contacto (`z_draw`) y cota de tránsito en el aire (`z_hover`).
- **Asistente de Calibración de Marcador:** Comando interactivo para hallar la altura milimétrica exacta donde la punta toca el papel sin dañar el marcador ni el robot.
- **Control de Efectores:** Soporte para ventosa de succión neumática (`suck`) y pinza/gripper (`grip`).
- **Visión con GoPro USB & VLA Multimodal:** Captura de video en tiempo real desde GoPro conectada por USB (modo *GoPro Connect* o V4L2) integrado con modelos multimodales **Claude 3.5/3.7 Sonnet** vía Anthropic API.
- **Aprendizaje Visual-Motor (Visual Servoing):** El modelo aprende de forma iterativa la correspondencia entre sus movimientos cartesianos en milímetros ($dx, dy, dz$) y los desplazamientos en píxeles $(\Delta u, \Delta v)$ en la imagen para interactuar y alcanzar objetivos visuales.
- **Sistema de Seguridad Integrado (`SafetyLimits`):** Verifica automáticamente que las coordenadas solicitadas no excedan el radio físico de trabajo (160 mm a 330 mm) ni bajen de cotas peligrosas para la mesa (evita colisiones mecánicas).
- **Modo Simulación / Mock Completo:** Permite desarrollar, probar algoritmos y ejecutar scripts sin necesidad de tener el robot físico ni la cámara conectados (`mock=True` o flags `--mock`), incluyendo simulación visual sintética (`MockCamera`).
- **CLI Amigable con Rich:** Comandos de consola `dobot scan`, `dobot status`, `dobot move`, `dobot suction`, `dobot demo`, `dobot draw-face`, `dobot calibrate-pen`, `dobot gopro-scan`, `dobot snapshot`, `dobot ai-agent`.
- **Reglas udev para Ubuntu:** Configuración automática de permisos de acceso serie sin requerir `sudo`.

---

## 📁 Estructura del Proyecto

```text
dobot-magician/
├── .env                        # Clave de API de Anthropic (IGNORADO POR GIT)
├── .venv/                      # Entorno virtual de Python
├── examples/                   # Scripts de demostración prácticos
│   ├── 01_scan_ports.py        # Diagnóstico y detección de puertos USB
│   ├── 02_basic_movement.py    # Movimientos cartesianos básicos y relativos
│   ├── 03_pick_and_place.py    # Rutina completa de agarre y depósito
│   ├── 04_mock_simulation.py   # Simulación y validación de límites de seguridad
│   ├── 05_draw_smiley.py       # Trazado de carita feliz con marcador
│   └── 06_gopro_llm_visual_servoing.py # Servocontrol visual y aprendizaje con GoPro + Claude
├── src/
│   └── dobot_controller/
│       ├── __init__.py
│       ├── cli.py              # Línea de comandos (Typer + Rich)
│       ├── connection.py       # Detección y filtrado de puertos serie / permisos
│       ├── controller.py       # DobotController de alto nivel con Context Manager
│       ├── drawing.py          # Generador de trayectorias y rutinas de dibujo
│       ├── mock.py             # Simulador en memoria del robot
│       ├── safety.py           # Validaciones de límites geométricos
│       └── vision/             # Módulo de Visión y Agente Multimodal
│           ├── __init__.py
│           ├── camera.py       # Captura de video GoPro USB + Lector con hilo + MockCamera
│           ├── agent.py        # Agente Claude VLA con herramientas de control robótico
│           ├── visual_servo.py # Bucle cerrado de percepción-razonamiento-acción
│           └── gopro_setup.py  # Diagnóstico y activación de GoPro Connect en Linux
├── tests/
│   ├── test_dobot_controller.py# Suite de 14 pruebas de cinemática y control
│   └── test_vision.py          # Suite de 6 pruebas de visión y bucle visual
├── udev/
│   └── 99-dobot.rules          # Reglas udev para CP210x y CH340
├── pyproject.toml              # Definición del paquete e instalador pip
├── pytest.ini                  # Configuración de pruebas aisladas
├── requirements.txt            # Dependencias del proyecto
├── run_tests.sh                # Script para ejecutar pruebas
└── setup_udev.sh               # Script para instalar permisos udev en Ubuntu
```

---

## 🛠️ Instalación y Configuración

### 1. Activar el entorno virtual

El proyecto ya cuenta con su entorno configurado en `.venv`:

```bash
cd master-projects/dobot-magician
source .venv/bin/activate
```

O si necesitas recrearlo:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### 2. Configurar la API Key de Anthropic

Crea o verifica el archivo `.env` en la raíz del proyecto (este archivo está protegido en `.gitignore` para no subir secretos):

```bash
echo "ANTHROPIC_API_KEY=tu_clave_aqui" > .env
```

### 3. Permisos en Ubuntu (Grupo `dialout`)

Para que tu usuario pueda comunicarse con el puerto serie USB sin `sudo`:

```bash
# 1. Asignar usuario al grupo dialout (si aún no lo está)
sudo usermod -a -G dialout $USER

# 2. (Opcional) Instalar reglas udev persistentes
sudo ./setup_udev.sh
```

---

## 📷 Conexión de GoPro por USB en Ubuntu / Linux

Las cámaras GoPro (HERO 8, 9, 10, 11, 12, 13) funcionan en Linux a través de dos mecanismos:

1. **Modo GoPro Connect (Webcam USB sobre Red CDC-NCM):**
   - En la pantalla táctil de tu GoPro, ve a **Preferencias > Conexiones > Conexión USB** y selecciona **GoPro Connect** (no MTP).
   - Al conectar el cable USB-C al PC, Linux detecta una interfaz de red USB (ej. `usb0` o `enx...`).
   - El sistema le solicita el inicio de streaming a la cámara mediante HTTP (`/gopro/webcam/start`) y recibe el flujo de video en tiempo real vía UDP (`udp://@0.0.0.0:8554`).
2. **Modo V4L2 estándar (`/dev/video*`):**
   - Si utilizas una capturadora HDMI-USB (Cam Link), o el demonio `gopro-webcam` con `v4l2loopback`, la cámara aparece como un nodo de video estándar.
   - El capturador `GoProCapture` lo detecta de forma automática.

### Diagnosticar cámaras conectadas:
```bash
dobot gopro-scan
```

### Tomar una captura de prueba:
```bash
# Con cámara física:
dobot snapshot -o foto.jpg

# En simulación (MockCamera con mesa de trabajo virtual):
dobot snapshot --mock -o test_mesa.jpg
```

---

## 🤖 Agente Multimodal con Claude y Dobot (Visual Servoing)

El sistema implementa un ciclo continuo de **Percepción $\rightarrow$ Razonamiento Espacial $\rightarrow$ Acción $\rightarrow$ Verificación**:

```mermaid
flowchart LR
    A["GoPro USB\n(Video Real o Mock)"] --> B["Captura en tiempo real\n(GoProCapture)"]
    B --> C["Claude 3.5/3.7 Sonnet\n(Vision-Language-Action)"]
    C --> D["Herramientas / Acciones\n(move_rel, move_to, suck)"]
    D --> E["SafetyLimits\n(Límites mecánicos)"]
    E --> F["Dobot Magician\n(Hardware o Mock)"]
    F --> A
```

### Ejecutar desde la CLI:

```bash
# Modo interactivo en Simulación:
dobot ai-agent --mock --steps 6 --goal "Aprende los ejes de la cámara y acércate al cubo rojo"

# Con confirmación manual en cada movimiento antes de mover el robot:
dobot ai-agent --mock --confirm --goal "Inspecciona la mesa y céntrate en el objetivo"

# Con hardware real (Dobot y GoPro conectados):
dobot ai-agent --goal "Aprende la relación de ejes y posiciona la ventosa sobre el bloque"

# Reanudar una sesión previa conservando la memoria y los aprendizajes de ejes:
dobot ai-agent --resume --goal "Continúa acercándote al objetivo y activa la succión"
```

> **Persistencia de Sesión:** Al finalizar cada ejecución, el agente guarda automáticamente sus aprendizajes de ejes, historial de razonamiento y estado en `.dobot_ai_session.json`. Al usar el flag `--resume` (o `-r`), el modelo continúa en el mismo hilo de memoria sin tener que calibrar los ejes desde cero.

### Ejecutar script de ejemplo:

```bash
python examples/06_gopro_llm_visual_servoing.py --mock --steps 4
```

---

## 🧪 Pruebas Unitarias

Ejecuta el script de pruebas automatizado:

```bash
./run_tests.sh
```

Las 20 pruebas unitarias validan:
- Cinemática de trabajo y límites de seguridad (`SafetyLimits`).
- Intercepción de posiciones fuera de alcance o peligrosas para la mesa.
- Simulador en memoria (`MockDobot`) y efectores (succión y pinza).
- Generación de trayectorias geométricas de dibujo (`draw_smiley_face`).
- Captura de video real y sintética (`MockCamera`, `GoProCapture`, base64).
- Despacho seguro de herramientas robóticas para Claude (`VisualServoLoop`).
- Comandos CLI (`scan`, `status`, `move`, `demo`, `draw-face`, `gopro-scan`, `snapshot`).

```bash
# 1. Asignar usuario al grupo dialout (si aún no lo está)
sudo usermod -a -G dialout $USER

# 2. (Opcional) Instalar reglas udev persistentes
sudo ./setup_udev.sh
```

---

## 💻 Uso desde la Línea de Comandos (CLI)

El paquete incluye el comando `dobot` instalado en el entorno:

### 1. Escanear puertos y diagnosticar hardware
```bash
dobot scan
```

### 2. Consultar posición actual y articulaciones
Con el robot conectado físicamente:
```bash
dobot status
```
O en modo simulado:
```bash
dobot status --mock
```

### 3. Mover a una coordenada cartesiana
```bash
dobot move --x 230 --y 0 --z 40 --r 0
```

### 4. Controlar la ventosa de succión
```bash
dobot suction on
dobot suction off
```

### 5. Calibración a Home
```bash
dobot home
```

### 6. Ejecutar rutina de demostración (Pick & Place)
```bash
dobot demo
# O en simulación:
dobot demo --mock
```

### 7. Calibrar la altura de contacto del marcador
Si no conoces la altura exacta $Z$ donde el marcador toca la hoja de papel, ejecuta el asistente interactivo:
```bash
dobot calibrate-pen
```
Te permite descender milimétricamente el marcador (`-5`, `-1`, `-0.2`) hasta hacer contacto ligero, e imprime la altura óptima.

### 8. Dibujar la Carita Feliz
```bash
# Prueba segura en el aire (a 35 mm sobre la mesa, sin tocar papel):
dobot draw-face --air-draw

# Dibujar sobre papel con la altura Z calibrada (ej. Z = 0 mm):
dobot draw-face --z-draw 0.0 --z-hover 15.0

# O en modo simulación (sin conectar hardware):
dobot draw-face --mock
```

### 9. Dibujo Visual Continuo de Objetos Reales (GoPro + Claude VLA)
El sistema funciona como un **ilustrador robótico de objetos reales**:
1. **Captura de cualquier objeto real:** La cámara (GoPro o webcam USB) enfoca **cualquier objeto** del mundo real (una taza de café, una manzana u otra fruta, herramientas, tijeras, zapatillas, juguetes, etc.), **NO el cuaderno**. También puedes suministrar una fotografía local mediante `--image mi_foto.jpg`.
2. **Síntesis artística con Claude:** Claude analiza la fotografía del objeto, extrae su silueta y características más reconocibles, y sintetiza un boceto de líneas vectoriales continuas (line-art).
3. **Lienzo: Cuaderno de 25x17 cm:** El dibujo se escala y proyecta sobre las dimensiones del cuaderno físico ($250 \times 170\text{ mm}$), con el efector final iniciando en su posición física exacta calibrada:
   $$\mathbf{P}_{\text{inicial}} = (X=235.50\text{ mm},\, Y=-10.45\text{ mm},\, Z=-38.59\text{ mm},\, R=5.67^\circ)$$
   *(correspondiente a los ángulos articulares: $J_1=-2.54^\circ, J_2=49.09^\circ, J_3=59.77^\circ, J_4=8.21^\circ$)*.
4. **Aprobación obligatoria previa:** Se genera `drawing_preview.png` y se solicita tu confirmación (`[A]probar`, `[R]echazar`, `[O] abrir previsualización`) antes de tocar el papel.
5. **Comportamiento de posicionamiento y seguridad:**
- **Siempre inicia en contacto con el papel:** El efector desciende a la posición de calibración inicial ($X=235.50, Y=-10.45, Z=-38.59\text{ mm}, R=5.67^\circ$) para que puedas alinear física y visualmente el cuaderno de 25x17 cm bajo la punta del marcador.
- **Sin movimientos verticales previos:** Durante la captura del objeto, el análisis de IA y la espera de tu aprobación, el brazo permanece inmóvil en contacto con el papel en dicha posición inicial.
- **Elevación al aprobar:** Únicamente al confirmar la aprobación (`A` / Enter), el brazo se eleva verticalmente a altura de tránsito ($Z=z\_hover=-23.59\text{ mm}$) para trasladarse al inicio del dibujo sin rayar la hoja.
- **Retorno final:** Al culminar la ilustración, regresa al centro inicial y vuelve a descansar en contacto con el papel ($Z=-38.59\text{ mm}$).

```bash
# Modo normal con hardware real (¡sin argumentos ni -i necesario!):
dobot ai-draw

# Modo simulación (Mock Dobot + Cámara virtual con taza de café de prueba):
dobot ai-draw --mock

# O a partir de una foto local de cualquier objeto:
dobot ai-draw --image foto_objeto.jpg
```

Archivos generados automáticamente:
- `captured_subject.jpg`: Fotograma de alta resolución capturado por la cámara.
- `drawing_preview.png`: Previsualización gráfica del cuaderno de 25x17 cm con el centro marcado y los trazos vectoriales listos para aprobación.

### 10. Agente Inteligente VLA y Servocontrol Visual
```bash
# Agente interactivo continuo autónomo:
dobot ai-agent --goal "Aprende los ejes y posiciónate sobre el objetivo rojo"

# Reanudar sesión previa con memoria de ejes calibrados:
dobot ai-agent --resume
```

---

## 🐍 Uso desde Python (API)

### Ejemplo Básico con Context Manager

```python
from dobot_controller import DobotController

# Conexión automática al puerto detectado (ej. /dev/ttyUSB0)
with DobotController() as bot:
    # Obtener pose actual
    pose = bot.get_pose()
    print(f"X={pose['x']} mm, Y={pose['y']} mm, Z={pose['z']} mm")

    # Mover a posición segura
    bot.move_to(x=220.0, y=0.0, z=50.0, wait=True)

    # Desplazamiento relativo (+30 mm en eje Y)
    bot.move_rel(dy=30.0, wait=True)
```

### Dibujar una Carita Feliz con el Marcador

```python
from dobot_controller import DobotController
from dobot_controller.drawing import draw_smiley_face

with DobotController() as bot:
    draw_smiley_face(
        bot=bot,
        center_x=220.0,       # Centro en X (mm)
        center_y=0.0,         # Centro en Y (mm)
        radius=30.0,          # Radio de la cara (mm)
        z_draw=0.0,           # Altura de contacto sobre papel
        z_hover=15.0,         # Altura para levantar el marcador en el aire
        velocity=35.0         # Velocidad lineal de dibujo (mm/s)
    )
```

O ejecutando directamente el script de ejemplo:
```bash
python examples/05_draw_smiley.py --air-draw
python examples/05_draw_smiley.py --z-draw 0.0
```

### Rutina de Pick & Place

```python
from dobot_controller import DobotController

with DobotController() as bot:
    bot.pick_and_place(
        pick_pos=(220.0, -80.0, 10.0),   # Punto A
        place_pos=(220.0, 80.0, 10.0),   # Punto B
        safe_z=60.0,                      # Altura de viaje
        dwell_seconds=0.5,
        use_gripper=False                 # Usa succión por defecto
    )
```

### Modo Simulación (Sin Hardware)

```python
from dobot_controller import DobotController

with DobotController(mock=True) as bot:
    bot.move_to(x=250.0, y=30.0, z=40.0)
    print("Pose simulada:", bot.get_pose())
```

---

## 🧪 Pruebas Unitarias

Ejecuta el script de pruebas automatizado:

```bash
./run_tests.sh
```

Las 14 pruebas unitarias validan:
- Geometría de trabajo y límites de seguridad (`SafetyLimits`).
- Intercepción de posiciones fuera de alcance o peligrosas para la mesa.
- Simulador en memoria (`MockDobot`) y control de efectores (succión y gripper).
- Generación de trayectorias geométricas de dibujo (cabeza, ojos, sonrisa).
- Comandos CLI (`scan`, `status`, `move`, `demo`, `draw-face`).
