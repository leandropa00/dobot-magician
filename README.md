# Dobot Magician - Controlador en Python para Ubuntu / Linux

Este proyecto proporciona un entorno modular, seguro y listo para producción para controlar el brazo robótico **Dobot Magician** en **Ubuntu / Linux** usando Python 3.

Incluye tanto una potente **CLI en terminal** (`dobot`) como una **interfaz web interactiva** (`dobot web`) con visión artificial, integración de cámaras **GoPro HERO por USB** y modelos multimodales **Claude (Sonnet 5 / 4.6 / 3.7)** de Anthropic para síntesis artística de bocetos y servocontrol visual (VLA).

---

## 🚀 Características

- **Control Cartesiano y Articular:** Movimientos absolutos (`move_to`) y relativos (`move_rel`), calibración a home (`home`) y telemetría en tiempo real de coordenadas cartesianas ($X, Y, Z, R$) y articulaciones ($J_1, J_2, J_3, J_4$).
- **Modos PTP Configurables:** Soporte para interpolación lineal (`MOVL_XYZ`) y articular rápida (`MOVJ_XYZ`).
- **Dibujo con Marcador y Trayectorias Suaves:** Módulo de dibujo para trazos vectoriales sobre papel, generador geométrico (caritas felices, círculos, arcos), control estricto de cota de contacto (`z_draw`) y cota de tránsito en el aire (`z_hover`).
- **Asistente de Calibración de Marcador:** Comando interactivo (`dobot calibrate-pen`) para hallar la altura milimétrica exacta donde la punta del marcador toca el papel sin dañar la punta ni sobrecargar el robot.
- **Control de Efectores:** Soporte para ventosa de succión neumática (`suck`) y pinza/gripper neumático (`grip`).
- **Cámara GoPro por USB & Webcams:** Detección y streaming en tiempo real de GoPro HERO (8 a 13) por red USB (modo *GoPro Connect* CDC-NCM sobre HTTP/UDP) y cámaras web estándar (V4L2 y WebRTC en navegador).
- **Control de Lente FOV (Lineal vs Gran Angular):** Selector dinámico en la interfaz web y API para alternar el campo de visión de la cámara GoPro y cámaras simuladas.
- **Modelos Multimodales Claude (VLA):** Integración con **Claude Sonnet 5** (`claude-sonnet-5-20260630`), Claude Sonnet 4.6 y Claude 3.7 Sonnet para comprensión visual espacial, extracción de contornos y generación de trayectorias con Tool Calling forzado.
- **Estudio Web Interactivo (`dobot web`):** Servidor FastAPI con streaming de video en vivo, captura de imágenes, previsualización vectorial nativa en SVG, controles de jogging manual en los tres ejes y botón de persistencia de origen en disco (`.dobot_origin.json`).
- **Aprendizaje Visual-Motor (Visual Servoing):** Bucle cerrado autónomo donde el modelo aprende iterativamente la correspondencia entre desplazamientos cartesianos en milímetros ($dx, dy, dz$) y desplazamientos en píxeles $(\Delta u, \Delta v)$ en la imagen.
- **Sistema de Seguridad Integrado (`SafetyLimits`):** Validación automática que intercepta cualquier comando que exceda el radio físico de trabajo (160 mm a 330 mm) o descienda a cotas peligrosas para la mesa de trabajo.
- **Modo Simulación / Mock Completo:** Permite desarrollar, probar algoritmos y ejecutar la suite completa sin hardware conectado (`--mock`), incluyendo simulación visual sintética (`MockCamera`).
- **CLI Amigable con Rich & Typer:** Comandos estructurados con ayuda contextual, formateo en tablas y autocompletado de shell.
- **Permisos udev Automatizados:** Reglas udev para dispositivos USB serie (CP210x y CH340) para operar sin `sudo`.

---

## 📁 Estructura del Proyecto

```text
dobot-magician/
├── .env                            # Clave de API de Anthropic y modelo (IGNORADO POR GIT)
├── .env.example                    # Plantilla de variables de entorno
├── .dobot_origin.json              # Coordenadas calibradas de inicio y dibujo persistidas
├── .dobot_ai_session.json          # Memoria persistente de sesiones de servocontrol IA
├── .venv/                          # Entorno virtual de Python
├── examples/                       # Scripts de demostración prácticos
│   ├── 01_scan_ports.py            # Diagnóstico y detección de puertos USB
│   ├── 02_basic_movement.py        # Movimientos cartesianos básicos y relativos
│   ├── 03_pick_and_place.py        # Rutina de agarre y depósito con succión
│   ├── 04_mock_simulation.py       # Simulación y validación de límites de seguridad
│   ├── 05_draw_smiley.py           # Trazado de carita feliz con marcador
│   └── 06_gopro_llm_visual_servoing.py # Servocontrol visual y aprendizaje con GoPro + Claude
├── src/
│   └── dobot_controller/
│       ├── __init__.py
│       ├── cli.py                  # CLI principal (Typer + Rich)
│       ├── connection.py           # Detección y filtrado de puertos serie / permisos
│       ├── controller.py           # DobotController de alto nivel con Context Manager
│       ├── drawing.py              # Generador de trayectorias y rutinas de dibujo
│       ├── mock.py                 # Simulador en memoria del robot
│       ├── safety.py               # Validaciones de límites geométricos
│       ├── vision/                 # Módulo de Visión y Agente Multimodal
│       │   ├── __init__.py
│       │   ├── agent.py            # Agente Claude VLA con herramientas de control robótico
│       │   ├── camera.py           # Captura de video GoPro USB + Lector con hilo + MockCamera
│       │   ├── gopro_setup.py      # Diagnóstico y activación de GoPro Connect en Linux
│       │   ├── visual_drawer.py    # Pipeline de síntesis de bocetos y previsualización
│       │   └── visual_servo.py     # Bucle cerrado de percepción-razonamiento-acción
│       └── web/                    # Servidor Web y UI
│           ├── __init__.py
│           ├── app.py              # Aplicación FastAPI y endpoints REST/WebSockets
│           ├── camera_manager.py   # Gestor de streaming de video (GoPro, Webcams, Mock)
│           ├── robot_manager.py    # Coordinador de estado del robot y cola de dibujo
│           └── static/             # Frontend HTML5, CSS y JavaScript
│               ├── app.js
│               ├── index.html
│               └── style.css
├── tests/                          # 40 Pruebas Unitarias Automatizadas
│   ├── test_dobot_controller.py    # 14 pruebas: cinemática, límites, efectores y mock
│   ├── test_vision.py              # 16 pruebas: cámaras, GoPro, servoing y agente Claude
│   └── test_web.py                 # 10 pruebas: endpoints web, telemetría y gestores
├── udev/
│   └── 99-dobot.rules              # Reglas udev para puertos serie CP210x y CH340
├── pyproject.toml                  # Configuración moderna del paquete (PEP 517 / PEP 660)
├── setup.py                        # Shim de compatibilidad para herramientas legadas
├── pytest.ini                      # Configuración de pruebas
├── requirements.txt                # Dependencias fijadas del proyecto
├── run_tests.sh                    # Script ejecutor de pruebas unitarias aisladas
└── setup_udev.sh                   # Instalador de reglas udev en Ubuntu
```

---

## 🛠️ Instalación y Configuración

### 1. Activar el entorno virtual

El proyecto utiliza un entorno virtual en `.venv`:

```bash
cd ~/master-projects/dobot-magician
source .venv/bin/activate
```

Si necesitas crear el entorno desde cero:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

> [!NOTE]
> La instalación en modo editable (`pip install -e .`) registra el comando `dobot` en tu entorno virtual (`.venv/bin/dobot`). Recuerda siempre tener el entorno activo (`source .venv/bin/activate`) para que el comando esté en tu `$PATH`.

### 2. Configurar Variables de Entorno (`.env`)

Copia la plantilla y configura tu clave de Anthropic:

```bash
cp .env.example .env
```

Edita `.env`:
```ini
ANTHROPIC_API_KEY=sk-ant-api03-...
ANTHROPIC_MODEL=claude-sonnet-5
```

Modelos compatibles recomendados:
- `claude-sonnet-5` (por defecto): razonamiento agéntico y síntesis espacial de máxima fidelidad.
- `claude-sonnet-4-6`: alta precisión visual y trazos continuos.
- `claude-3-7-sonnet-20250219`: razonamiento híbrido multimodal.

### 3. Permisos en Ubuntu (Grupo `dialout`)

Para comunicarte con el puerto serie USB del Dobot sin requerir `sudo`:

```bash
# 1. Añadir usuario al grupo dialout
sudo usermod -a -G dialout $USER

# 2. Instalar reglas udev de reconocimiento de hardware
sudo ./setup_udev.sh
```
*(Es necesario cerrar sesión y volver a iniciarla para que el cambio de grupo surta efecto).*

---

## 🌐 Interfaz Web Interactiva (`dobot web`)

La interfaz web ofrece una estación de trabajo completa para dibujo robótico y control manual:

```bash
# Iniciar en modo hardware real (abre http://localhost:8000 automáticamente):
dobot web

# Iniciar en modo simulación (sin conectar robot ni cámara):
dobot web --mock

# Especificar puerto o dirección de red:
dobot web --host 0.0.0.0 --port 8000
```

### Funcionalidades de la Interfaz Web:

1. **Selector de Fuente de Video y Lente FOV:**
   - Permite alternar entre la cámara del navegador (WebRTC), la GoPro HERO conectada por red USB, o la cámara simulada (Mock).
   - Botón selector de lente: alterna al instante entre campo visual **Lineal** y **Gran Angular**.
2. **Captura Fotográfica Instantánea:**
   - Botón `📸 Capturar Foto` para congelar el encuadre del objeto a ilustrar.
3. **Síntesis Vectorial con Claude VLA:**
   - Botón `✨ Enviar al Modelo`: Claude analiza la fotografía y sintetiza los trazos de dibujo continuo utilizando tool calling estructurado (`generate_drawing_trajectory`).
4. **Previsualización Vectorial SVG:**
   - Renderizado vectorial nativo sobre el área útil del cuaderno de dibujo (25 × 17 cm) con indicador de escala y progreso.
5. **Controles de Movimiento Manual (Jogging):**
   - Panel de control para desplazar el brazo en $X, Y, Z$ con pasos seleccionables (1 mm, 5 mm, 10 mm, 20 mm, 50 mm) o mediante flechas del teclado.
6. **Persistencia Directa de Posición Inicial:**
   - Mueve el efector hasta la posición y altura de contacto deseadas y presiona `💾 Persistir como Posición Inicial` dentro del panel de posición actual. La cota $Z$ y el centro se guardan en disco (`.dobot_origin.json`) y se conservan de forma permanente.
7. **Ejecución y Parada Segura:**
   - Botón `✍️ Confirmar y Comenzar a Dibujar` para iniciar la ejecución física y botón de parada de emergencia.

---

## 📷 Conexión de GoPro por USB en Ubuntu / Linux

Las cámaras GoPro HERO (8, 9, 10, 11, 12, 13) se comunican con Linux mediante **GoPro Connect** (red USB CDC-NCM):

1. En la pantalla de la GoPro, ve a **Preferencias > Conexiones > Conexión USB** y selecciona **GoPro Connect**.
2. Conecta la cámara por USB-C. Linux configurará una interfaz de red (ej. `usb0` o `enx...`).
3. El módulo `dobot_controller.vision.camera` envía los comandos de inicio por HTTP (`/gopro/webcam/start`) y recibe el flujo MJPEG/UDP.

### Diagnosticar cámaras conectadas:
```bash
dobot gopro-scan
```

### Tomar una captura de prueba:
```bash
# Con cámara física conectada:
dobot snapshot -o foto_prueba.jpg

# En modo simulación (genera una escena de prueba con una taza de café):
dobot snapshot --mock -o test_mesa.jpg
```

---

## 🤖 Agente Multimodal y Dibujo Robótico por IA

### 1. Dibujo Autónomo de Objetos Reales (`dobot ai-draw`)

El comando `ai-draw` convierte al Dobot Magician en un ilustrador robótico de objetos reales:

```bash
# Flujo completo con cámara y robot físico:
dobot ai-draw

# Modo simulación completo (Mock Robot + Mock Camera):
dobot ai-draw --mock

# Dibujar a partir de una fotografía existente:
dobot ai-draw --image mi_objeto.jpg
```

**Flujo de Ejecución:**
1. **Captura del objeto:** La cámara enfoca cualquier objeto del entorno real (frutas, herramientas, tazas, calzado, etc.).
2. **Síntesis con Claude:** El modelo extrae contornos y sintetiza una trayectoria vectorial continua.
3. **Lienzo: Cuaderno de 25 × 17 cm:** La trayectoria se proyecta sobre el área calibrada del cuaderno.
4. **Seguridad y contacto inicial:** El efector desciende a la posición de reposo calibrada ($Z = z_{\text{draw}}$) para alinear el cuaderno.
5. **Confirmación obligatoria:** Muestra la vista previa gráfica (`drawing_preview.png`) y solicita confirmación interactiva (`[A]probar`, `[R]echazar`, `[O] abrir`) antes de iniciar.
6. **Trazado y retorno:** Solo al aprobar, el brazo sube a $z_{\text{hover}}$, dibuja los trazos sobre el papel y regresa a descansar en contacto con la hoja.

### 2. Servocontrol Visual Continuo (`dobot ai-agent`)

Bucle cerrado de percepción-razonamiento-acción guiado por objetivos:

```bash
# Ejecutar en simulación con objetivo visual:
dobot ai-agent --mock --steps 6 --goal "Aprende los ejes de la cámara y acércate al cubo rojo"

# Modo con confirmación paso a paso:
dobot ai-agent --mock --confirm --goal "Inspecciona la mesa y céntrate en el objetivo"

# Reanudar una sesión previa conservando la matriz de ejes aprendida:
dobot ai-agent --resume --goal "Continúa acercándote al objetivo y activa la succión"
```

---

## 💻 Uso desde la Línea de Comandos (CLI)

```bash
# Diagnóstico de puertos USB y conectividad
dobot scan

# Estado actual (coordenadas cartesianas, ángulos y alarmas)
dobot status
dobot status --mock

# Mover a una coordenada absoluta (en mm)
dobot move --x 230 --y 0 --z 40 --r 0

# Control de la ventosa de succión
dobot suction on
dobot suction off

# Calibración a Home
dobot home

# Demostración de Pick & Place
dobot demo
dobot demo --mock

# Asistente interactivo para calibrar la altura Z del marcador
dobot calibrate-pen

# Dibujar carita feliz geométrica
dobot draw-face --air-draw               # Prueba en el aire sin tocar papel
dobot draw-face --z-draw -38.5 --z-hover -25.0
dobot draw-face --mock                   # En simulación

# Iniciar servidor Web Studio
dobot web
dobot web --mock
```

---

## 🐍 Uso desde Python (API)

### Movimiento Básico con Context Manager

```python
from dobot_controller import DobotController

# Conexión automática al puerto serie detectado
with DobotController() as bot:
    pose = bot.get_pose()
    print(f"Posición actual: X={pose['x']:.2f}, Y={pose['y']:.2f}, Z={pose['z']:.2f}")

    # Movimiento absoluto
    bot.move_to(x=220.0, y=0.0, z=50.0, wait=True)

    # Desplazamiento relativo (+30 mm en eje Y)
    bot.move_rel(dy=30.0, wait=True)
```

### Rutina de Dibujo de Carita Feliz

```python
from dobot_controller import DobotController
from dobot_controller.drawing import draw_smiley_face

with DobotController() as bot:
    draw_smiley_face(
        bot=bot,
        center_x=220.0,
        center_y=0.0,
        radius=30.0,
        z_draw=-38.5,     # Cota de contacto sobre papel
        z_hover=-25.0,    # Cota de elevación para tránsito
        velocity=35.0     # mm/s
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

El proyecto cuenta con una suite completa de **40 pruebas automatizadas** que validan cinemática, límites mecánicos de seguridad, efectores, visión, bucles de IA y la API web:

```bash
# Ejecutar todas las pruebas con el script aislado:
./run_tests.sh
```

O directamente con pytest:
```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest
```

### Cobertura de Pruebas:
- **`tests/test_dobot_controller.py` (14 pruebas):** Cinemática, límites de seguridad (`SafetyLimits`), simulador `MockDobot`, ventosa, gripper y generación de trayectorias geométricas.
- **`tests/test_vision.py` (16 pruebas):** Captura de video real y sintética (`MockCamera`, `GoProCapture`), herramientas de visión para Claude, serialización y bucle visual de servocontrol.
- **`tests/test_web.py` (10 pruebas):** Endpoints REST de FastAPI, streaming de cámara, telemetría del robot, persistencia de coordenadas y cola de comandos de dibujo.
