"""
Agente Multimodal VLA (Vision-Language-Action) con Anthropic Claude.
Interpreta fotogramas de video, razona espacialmente y comanda movimientos
al Dobot Magician aprendiendo la correspondencia visual-motora paso a paso.
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
import anthropic
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Modelo por defecto
DEFAULT_CLAUDE_MODEL: str = "claude-sonnet-4-5-20250929"

# Modelos oficiales de Anthropic con capacidades multimodales (Visión + Tool Use) permitidos
ALLOWED_CLAUDE_MODELS: Dict[str, str] = {
    "claude-sonnet-4-5-20250929": "Claude Sonnet 4.5 (Recomendado: máxima fidelidad y trazos estilizados)",
    "claude-3-7-sonnet-20250219": "Claude 3.7 Sonnet (Razonamiento visual avanzado y síntesis espacial)",
    "claude-3-7-sonnet-latest": "Claude 3.7 Sonnet Latest",
    "claude-3-5-sonnet-20241022": "Claude 3.5 Sonnet v2 (Alta precisión visual y tool use)",
    "claude-3-5-sonnet-20240620": "Claude 3.5 Sonnet v1",
    "claude-3-5-sonnet-latest": "Claude 3.5 Sonnet Latest",
    "claude-3-5-haiku-20241022": "Claude 3.5 Haiku (Rápido y económico, trazos esquemáticos)",
    "claude-3-5-haiku-latest": "Claude 3.5 Haiku Latest",
    "claude-3-opus-20240229": "Claude 3 Opus (Alta complejidad semántica)",
    "claude-3-opus-latest": "Claude 3 Opus Latest",
}


def resolve_claude_model(requested_model: Optional[str] = None) -> str:
    """
    Resuelve el modelo de Claude a utilizar, priorizando:
    1. requested_model (si se especifica explícitamente y no está vacío)
    2. Variable de entorno ANTHROPIC_MODEL (definida en el sistema o en el archivo .env)
    3. Variable de entorno DOBOT_VISION_MODEL (alias alternativo)
    4. DEFAULT_CLAUDE_MODEL ("claude-sonnet-4-5-20250929")
    """
    load_dotenv(override=False)
    env_model = os.environ.get("ANTHROPIC_MODEL") or os.environ.get("DOBOT_VISION_MODEL")
    model = (requested_model or env_model or DEFAULT_CLAUDE_MODEL).strip()

    if model not in ALLOWED_CLAUDE_MODELS:
        logger.warning(
            f"El modelo '{model}' no está en la lista estándar de modelos testeados "
            f"({', '.join(ALLOWED_CLAUDE_MODELS.keys())}), pero se intentará utilizar con Anthropic API."
        )

    return model


# Definición de herramientas para Claude
ROBOT_TOOLS = [
    {
        "name": "move_relative",
        "description": "Mueve el efector del Dobot Magician de forma relativa en milímetros (dx, dy, dz). Usar pasos prudentes (típicamente entre 5 y 30 mm).",
        "input_schema": {
            "type": "object",
            "properties": {
                "dx": {
                    "type": "number",
                    "description": "Desplazamiento en eje X del robot en mm (+X avanza alejándose de la base, -X retrocede)."
                },
                "dy": {
                    "type": "number",
                    "description": "Desplazamiento en eje Y del robot en mm (+Y mueve hacia la izquierda, -Y hacia la derecha)."
                },
                "dz": {
                    "type": "number",
                    "description": "Desplazamiento en eje Z del robot en mm (+Z sube en altura, -Z desciende hacia la mesa)."
                },
                "reason": {
                    "type": "string",
                    "description": "Explicación del razonamiento visual para este movimiento (ej. 'El efector está 40px arriba del objetivo')."
                }
            },
            "required": ["dx", "dy", "dz", "reason"]
        }
    },
    {
        "name": "move_absolute",
        "description": "Mueve el Dobot a coordenadas cartesianas absolutas (x, y, z en mm).",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "number", "description": "Coordenada X absoluta (160 a 320 mm)."},
                "y": {"type": "number", "description": "Coordenada Y absoluta (-180 a 180 mm)."},
                "z": {"type": "number", "description": "Coordenada Z absoluta (-50 a 150 mm)."},
                "reason": {"type": "string", "description": "Motivo del movimiento."}
            },
            "required": ["x", "y", "z", "reason"]
        }
    },
    {
        "name": "set_suction",
        "description": "Activa o desactiva la ventosa neumática de succión.",
        "input_schema": {
            "type": "object",
            "properties": {
                "enable": {"type": "boolean", "description": "True para succionar, False para soltar y apagar."},
                "reason": {"type": "string", "description": "Motivo de la acción."}
            },
            "required": ["enable", "reason"]
        }
    },
    {
        "name": "set_gripper",
        "description": "Abre o cierra la pinza / gripper.",
        "input_schema": {
            "type": "object",
            "properties": {
                "enable": {"type": "boolean", "description": "True para cerrar pinza, False para abrir."},
                "reason": {"type": "string", "description": "Motivo de la acción."}
            },
            "required": ["enable", "reason"]
        }
    },
    {
        "name": "calibrate_axes",
        "description": "Solicita un micro-movimiento de prueba (ej. dx=+15mm o dy=+15mm) para aprender cómo se refleja en los ejes u,v de la cámara.",
        "input_schema": {
            "type": "object",
            "properties": {
                "axis": {"type": "string", "enum": ["X", "Y", "Z"], "description": "Eje a calibrar."},
                "distance_mm": {"type": "number", "description": "Distancia de prueba (ej. 15.0 mm)."}
            },
            "required": ["axis", "distance_mm"]
        }
    },
    {
        "name": "draw_trajectory",
        "description": "Genera y envía una secuencia completa de trazos continuos para dibujar sobre el papel sin interrupción. Cada trazo se ejecuta de forma fluida (levantar lápiz -> descender -> trazar linealmente todos los puntos -> levantar lápiz). Usar esta herramienta para dibujar, replicar un boceto o trazar formas a partir de lo que ve la cámara.",
        "input_schema": {
            "type": "object",
            "properties": {
                "drawing_description": {
                    "type": "string",
                    "description": "Descripción clara de lo observado en la cámara y lo que se va a dibujar."
                },
                "strokes": {
                    "type": "array",
                    "description": "Lista ordenada de trazos continuos. Cada trazo es un objeto con 'name' y una lista de puntos 2D.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Nombre identificador del trazo (ej. 'contorno', 'ojo_izq', 'linea_base')."},
                            "points": {
                                "type": "array",
                                "description": "Secuencia ordenada de puntos [x, y]. Pueden ser normalizados [-1.0, 1.0] respecto al centro del papel o en mm reales del robot.",
                                "items": {
                                    "type": "array",
                                    "items": {"type": "number"},
                                    "minItems": 2,
                                    "maxItems": 2
                                },
                                "minItems": 2
                            }
                        },
                        "required": ["name", "points"]
                    }
                },
                "normalized": {
                    "type": "boolean",
                    "description": "True si los puntos están en coordenadas normalizadas [-1.0, 1.0] dentro del lienzo. False si son coordenadas directas en mm del robot."
                }
            },
            "required": ["drawing_description", "strokes"]
        }
    },
    {
        "name": "finish_task",
        "description": "Declara que la tarea o interacción ha finalizado exitosamente o que no es posible continuar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean", "description": "True si se completó la meta, False si hubo impedimento."},
                "summary": {"type": "string", "description": "Resumen de lo logrado y observaciones finales."}
            },
            "required": ["success", "summary"]
        }
    }
]

SYSTEM_PROMPT = """Eres el sistema de control inteligente y visión robótica del brazo Dobot Magician acoplado a una cámara GoPro vía USB.
Tu función es actuar como un agente VLA (Vision-Language-Action) capaz de percibir el entorno a través de fotogramas de video, interactuar con el usuario, aprender a mover el brazo y trazar dibujos continuos.

### Espacio de Trabajo y Sistema de Coordenadas del Dobot:
- Eje X: Hacia adelante respecto a la base (+X aleja, -X acerca). Rango seguro: 160 mm a 320 mm.
- Eje Y: Hacia los lados (+Y izquierda, -Y derecha). Rango seguro: -180 mm a +180 mm.
- Eje Z: Altura vertical (+Z sube en el aire, -Z baja hacia la mesa). Nivel de tránsito seguro: Z > 20 mm.
- Radio físico: sqrt(X^2 + Y^2) debe estar entre 160 mm y 330 mm.

### Modos de Operación:
1. DIBUJO CONTINUO (draw_trajectory):
   - Cuando el objetivo involucre dibujar, copiar un boceto o trazar figuras observadas en la cámara, NO debes moverte milímetro a milímetro capturando imágenes intermedias.
   - Analiza el fotograma de la cámara, extrae la geometría completa del objeto o boceto a reproducir, genera el mapa de coordenadas con todos sus trazos continuos ('strokes') y envía la secuencia completa con la herramienta `draw_trajectory`.
   - El robot ejecutará toda la secuencia de trazos de forma fluida e ininterrumpida.
2. MANIPULACIÓN Y SERVOCONTROL PASO A PASO (move_relative, move_absolute):
   - Se utiliza para posicionamiento fino, aproximación visual y agarre con ventosa/pinza.

### Aprendizaje Visual-Motor (Visual Servoing):
1. La cámara GoPro puede estar en cualquier orientación (cenital, inclinada, invertida).
2. Debes aprender la correspondencia entre los movimientos en milímetros del robot (dx, dy) y los desplazamientos en píxeles (du, dv) en la imagen:
   - Al ejecutar un movimiento, compara el fotograma previo con el nuevo fotograma.
   - Observa en qué dirección se desplazó el efector en la imagen tras aplicar un `dx` o `dy`.
   - Utiliza esa relación aprendida para corregir tus siguientes pasos hacia el objetivo.
3. Avanza de forma iterativa y prudente:
   - Realiza pasos de 10 a 25 mm al inicio para aproximarte.
   - Reduce a 3 a 10 mm cuando estés cerca para centrado fino.
   - Mantén Z a cota segura mientras te trasladas horizontalmente; solo baja en Z una vez estés alineado sobre el objetivo.
4. Explica siempre tu razonamiento visual brevemente antes de invocar la herramienta.

### Control de Finalización Autónomo:
- La sesión se ejecuta de manera continua y autónoma sin un número fijo de pasos.
- TÚ eres responsable de evaluar visualmente en cada fotograma si el objetivo ha sido alcanzado.
- Cuando compruebes en la imagen que el efector cumplió la meta encomendada (por ejemplo, alineado sobre el objeto, altura alcanzada o succión completada), DEBES invocar la herramienta `finish_task(success=True, summary="...")` para cerrar el ciclo.
- Si determinas que la meta es físicamente inalcanzable (obstáculo, fuera de rango o error insuperable), llama a `finish_task(success=False, summary="...")` explicando el motivo.
"""


class VisionAgent:
    """
    Agente de IA basado en Anthropic Claude que gestiona la interacción
    multimodal (imagen + texto) y decide las acciones del robot.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.2
    ):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY no encontrada en entorno ni argumento.")

        self.model = resolve_claude_model(model)
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.messages: List[Dict[str, Any]] = []
        self.step_counter = 0

    def reset_conversation(self):
        """Reinicia el historial de conversación del agente."""
        self.messages = []
        self.step_counter = 0
        logger.info("Historial del agente reiniciado.")

    def step(
        self,
        user_text: str,
        image_base64: Optional[str] = None,
        robot_pose: Optional[Dict[str, Any]] = None,
        last_action_result: Optional[str] = None
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Ejecuta un ciclo de razonamiento del agente.
        
        Args:
            user_text: Mensaje, instrucción u objetivo del usuario.
            image_base64: Fotograma actual codificado en JPEG base64.
            robot_pose: Posición actual del Dobot {'x', 'y', 'z', 'r'}.
            last_action_result: Resultado textual de la última acción ejecutada.
            
        Returns:
            Tuple (texto_respuesta, herramienta_invocada_o_None)
        """
        self.step_counter += 1
        content_parts: List[Dict[str, Any]] = []

        # Agregar imagen si se proporciona
        if image_base64:
            content_parts.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": image_base64
                }
            })

        # Construir contexto de estado del robot
        state_info = f"[Paso {self.step_counter}]\n"
        if robot_pose:
            state_info += (
                f"Estado actual Dobot: X={robot_pose.get('x', 0):.1f} mm, "
                f"Y={robot_pose.get('y', 0):.1f} mm, Z={robot_pose.get('z', 0):.1f} mm, "
                f"R={robot_pose.get('r', 0):.1f}°\n"
            )
        if last_action_result:
            state_info += f"Resultado acción previa: {last_action_result}\n"

        full_prompt = f"{state_info}\nInstrucción / Contexto: {user_text}"
        content_parts.append({"type": "text", "text": full_prompt})

        self.messages.append({"role": "user", "content": content_parts})

        # Mantener historial acotado para evitar desborde de contexto visual
        # Guardamos las últimas 6 interacciones manteniendo la última imagen
        if len(self.messages) > 8:
            # Mantener el primer mensaje y los últimos 6
            self.messages = [self.messages[0]] + self.messages[-6:]

        logger.info(f"Enviando solicitud a Claude ({self.model})...")
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT,
            messages=self.messages,
            tools=ROBOT_TOOLS
        )

        response_text = ""
        tool_call = None

        # Procesar contenido de la respuesta
        assistant_content = []
        for block in response.content:
            if block.type == "text":
                response_text += block.text + "\n"
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                tool_call = {
                    "id": block.id,
                    "name": block.name,
                    "input": block.input
                }
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input
                })

        self.messages.append({"role": "assistant", "content": assistant_content})
        return response_text.strip(), tool_call

    def send_tool_result(self, tool_id: str, output: str):
        """Notifica al modelo el resultado de la herramienta invocada."""
        self.messages.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": output
                }
            ]
        })

    def save_session(self, filepath: str = ".dobot_ai_session.json") -> bool:
        """Guarda el historial de conversación y los aprendizajes del agente en disco."""
        import json
        try:
            serializable_messages = []
            for msg in self.messages:
                clean_content = []
                content = msg.get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "image":
                            clean_content.append({"type": "text", "text": "[Fotograma visual capturado en este paso]"})
                        else:
                            clean_content.append(item)
                else:
                    clean_content = content
                serializable_messages.append({
                    "role": msg.get("role"),
                    "content": clean_content
                })

            data = {
                "step_counter": self.step_counter,
                "model": self.model,
                "messages": serializable_messages
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Sesión guardada exitosamente en {filepath}")
            return True
        except Exception as e:
            logger.error(f"Error guardando sesión: {e}")
            return False

    def load_session(self, filepath: str = ".dobot_ai_session.json") -> bool:
        """Carga el historial y estado de una sesión previa."""
        import json
        if not os.path.exists(filepath):
            return False
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.step_counter = data.get("step_counter", 0)
            self.messages = data.get("messages", [])
            logger.info(f"Sesión reanudada desde {filepath} ({len(self.messages)} mensajes, paso {self.step_counter})")
            return True
        except Exception as e:
            logger.error(f"Error cargando sesión: {e}")
            return False
