/**
 * Dobot Magician Web Studio — Control del brazo, cámara del usuario y bocetos IA
 */

document.addEventListener('DOMContentLoaded', () => {
  // Estado de la aplicación
  const state = {
    currentStep: 10.0, // mm por paso
    webcamStream: null,
    capturedImageBase64: null,
    isDrawing: false,
    hasActiveSketch: false,
    currentPose: { x: 0, y: 0, z: 0, r: 0 },
    origin: { x: 235.5, y: -10.45, z_draw: -38.59, z_hover: -23.59 }
  };

  // Referencias a elementos del DOM
  const webcamVideo = document.getElementById('webcamVideo');
  const cameraSelect = document.getElementById('cameraSelect');
  const cameraStatus = document.getElementById('cameraStatus');
  const btnCapturePhoto = document.getElementById('btnCapturePhoto');
  const btnRetakePhoto = document.getElementById('btnRetakePhoto');
  const snapshotSection = document.getElementById('snapshotSection');
  const snapshotCanvas = document.getElementById('snapshotCanvas');
  const snapshotImg = document.getElementById('snapshotImg');
  const promptInput = document.getElementById('promptInput');
  const btnSendToModel = document.getElementById('btnSendToModel');
  const modelLoadingBox = document.getElementById('modelLoadingBox');
  const loadingMessage = document.getElementById('loadingMessage');

  // Sección Boceto
  const sketchSection = document.getElementById('sketchSection');
  const sketchSubjectBadge = document.getElementById('sketchSubjectBadge');
  const sketchPreviewImg = document.getElementById('sketchPreviewImg');
  const metaStrokeCount = document.getElementById('metaStrokeCount');
  const metaTotalPoints = document.getElementById('metaTotalPoints');
  const metaOriginPos = document.getElementById('metaOriginPos');
  const btnConfirmAndDraw = document.getElementById('btnConfirmAndDraw');
  const btnStopDrawing = document.getElementById('btnStopDrawing');
  const drawingProgressContainer = document.getElementById('drawingProgressContainer');
  const drawingProgressBar = document.getElementById('drawingProgressBar');
  const drawingProgressText = document.getElementById('drawingProgressText');
  const drawingProgressPercent = document.getElementById('drawingProgressPercent');

  // Estado del Robot
  const robotStatusBadge = document.getElementById('robotStatusBadge');
  const robotStatusText = document.getElementById('robotStatusText');
  const mockModeSwitch = document.getElementById('mockModeSwitch');
  const btnReconnect = document.getElementById('btnReconnect');
  const dobotPortInfo = document.getElementById('dobotPortInfo');
  const poseX = document.getElementById('poseX');
  const poseY = document.getElementById('poseY');
  const poseZ = document.getElementById('poseZ');
  const poseR = document.getElementById('poseR');

  // Punto de Inicio Indicado
  const originX = document.getElementById('originX');
  const originY = document.getElementById('originY');
  const originZDraw = document.getElementById('originZDraw');
  const originZHover = document.getElementById('originZHover');
  const btnSetOriginFromCurrent = document.getElementById('btnSetOriginFromCurrent');
  const btnMoveToOrigin = document.getElementById('btnMoveToOrigin');
  const btnUpdateOriginManual = document.getElementById('btnUpdateOriginManual');

  // Presets y Z
  const btnPresetHover = document.getElementById('btnPresetHover');
  const btnPresetPaper = document.getElementById('btnPresetPaper');

  // =========================================================================
  // 1. INICIALIZACIÓN DE LA CÁMARA DEL USUARIO
  // =========================================================================

  async function initWebcam(deviceId = null) {
    if (state.webcamStream) {
      state.webcamStream.getTracks().forEach(track => track.stop());
    }

    cameraStatus.textContent = 'Solicitando acceso...';
    cameraStatus.className = 'badge badge-info';

    try {
      const constraints = {
        video: deviceId 
          ? { deviceId: { exact: deviceId }, width: { ideal: 1280 }, height: { ideal: 720 } }
          : { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' },
        audio: false
      };

      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      state.webcamStream = stream;
      webcamVideo.srcObject = stream;
      cameraStatus.textContent = 'Cámara Activa';
      cameraStatus.className = 'badge badge-success';

      await enumerateCameras();
    } catch (err) {
      console.warn('Error al acceder a la cámara del usuario:', err);
      cameraStatus.textContent = 'Cámara no disponible';
      cameraStatus.className = 'badge badge-danger';
    }
  }

  async function enumerateCameras() {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const videoDevices = devices.filter(d => d.kind === 'videoinput');
      
      const currentSelected = cameraSelect.value;
      cameraSelect.innerHTML = '';
      
      videoDevices.forEach((dev, idx) => {
        const opt = document.createElement('option');
        opt.value = dev.deviceId;
        opt.textContent = dev.label || `Cámara ${idx + 1}`;
        cameraSelect.appendChild(opt);
      });

      if (currentSelected && videoDevices.some(d => d.deviceId === currentSelected)) {
        cameraSelect.value = currentSelected;
      }
    } catch (e) {
      console.warn('Error enumerando cámaras:', e);
    }
  }

  cameraSelect.addEventListener('change', () => {
    initWebcam(cameraSelect.value);
  });

  // =========================================================================
  // 2. CAPTURAR FOTO CON EL BOTÓN
  // =========================================================================

  btnCapturePhoto.addEventListener('click', () => {
    if (!state.webcamStream || webcamVideo.videoWidth === 0) {
      alert('La cámara no está lista o no tiene señal activa.');
      return;
    }

    const vw = webcamVideo.videoWidth;
    const vh = webcamVideo.videoHeight;
    snapshotCanvas.width = vw;
    snapshotCanvas.height = vh;

    const ctx = snapshotCanvas.getContext('2d');
    ctx.drawImage(webcamVideo, 0, 0, vw, vh);

    state.capturedImageBase64 = snapshotCanvas.toDataURL('image/jpeg', 0.90);
    snapshotImg.src = state.capturedImageBase64;

    snapshotSection.style.display = 'flex';
    snapshotSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  });

  btnRetakePhoto.addEventListener('click', () => {
    snapshotSection.style.display = 'none';
    state.capturedImageBase64 = null;
    webcamVideo.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  });

  // =========================================================================
  // 3. ENVIAR AL MODELO Y MOSTRAR BOCETO ABAJO
  // =========================================================================

  btnSendToModel.addEventListener('click', async () => {
    if (!state.capturedImageBase64) {
      alert('Primero debes capturar una fotografía con la cámara.');
      return;
    }

    modelLoadingBox.style.display = 'flex';
    sketchSection.style.display = 'none';
    btnSendToModel.disabled = true;
    loadingMessage.textContent = 'Enviando imagen a Claude para sintetizar boceto y trayectoria continua...';

    try {
      const response = await fetch('/api/generate-sketch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image: state.capturedImageBase64,
          instruction: promptInput.value.trim()
        })
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Error en el servidor al generar boceto');
      }

      const data = await response.json();

      // Mostrar sección del boceto abajo
      sketchSubjectBadge.textContent = data.subject || 'Objeto detectado';
      sketchPreviewImg.src = data.preview_image;
      metaStrokeCount.textContent = `${data.stroke_count} trazos`;
      metaTotalPoints.textContent = `${data.total_points} puntos`;
      metaOriginPos.textContent = `X=${state.origin.x.toFixed(1)}, Y=${state.origin.y.toFixed(1)}`;

      state.hasActiveSketch = true;
      sketchSection.style.display = 'flex';
      btnConfirmAndDraw.style.display = 'inline-flex';
      btnStopDrawing.style.display = 'none';
      drawingProgressContainer.style.display = 'none';

      // Desplazar suavemente a la sección de confirmación
      sketchSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

    } catch (err) {
      alert(`Error al generar boceto: ${err.message}`);
    } finally {
      modelLoadingBox.style.display = 'none';
      btnSendToModel.disabled = false;
    }
  });

  // =========================================================================
  // 4. CONFIRMAR BOCETO Y COMENZAR A DIBUJAR
  // =========================================================================

  btnConfirmAndDraw.addEventListener('click', async () => {
    if (!state.hasActiveSketch) {
      alert('No hay un boceto listo para dibujar.');
      return;
    }

    if (!confirm(`¿Iniciar dibujo robótico a partir del punto indicado (X=${state.origin.x}, Y=${state.origin.y})?`)) {
      return;
    }

    try {
      btnConfirmAndDraw.style.display = 'none';
      btnStopDrawing.style.display = 'inline-flex';
      drawingProgressContainer.style.display = 'flex';
      drawingProgressBar.style.width = '0%';
      drawingProgressPercent.textContent = '0%';
      drawingProgressText.textContent = 'Elevando brazo y preparando trazos...';

      const res = await fetch('/api/start-drawing', { method: 'POST' });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Error al iniciar dibujo');
      }

      state.isDrawing = true;
      startProgressPolling();

    } catch (err) {
      alert(`Error al iniciar dibujo: ${err.message}`);
      btnConfirmAndDraw.style.display = 'inline-flex';
      btnStopDrawing.style.display = 'none';
      drawingProgressContainer.style.display = 'none';
    }
  });

  btnStopDrawing.addEventListener('click', async () => {
    if (confirm('¿Deseas interrumpir el dibujo inmediatamente?')) {
      try {
        await fetch('/api/stop-drawing', { method: 'POST' });
      } catch (e) {
        console.error('Error al detener dibujo:', e);
      }
    }
  });

  let progressInterval = null;
  function startProgressPolling() {
    if (progressInterval) clearInterval(progressInterval);

    progressInterval = setInterval(async () => {
      try {
        const res = await fetch('/api/drawing/progress');
        const prog = await res.json();

        drawingProgressBar.style.width = `${prog.percent}%`;
        drawingProgressPercent.textContent = `${Math.round(prog.percent)}%`;
        drawingProgressText.textContent = prog.message;

        if (!prog.is_drawing) {
          clearInterval(progressInterval);
          progressInterval = null;
          state.isDrawing = false;
          btnConfirmAndDraw.style.display = 'inline-flex';
          btnStopDrawing.style.display = 'none';

          if (prog.error) {
            alert(`Dibujo detenido con error: ${prog.error}`);
          } else if (prog.percent >= 100) {
            drawingProgressText.textContent = '✅ ¡Dibujo completado con éxito en el cuaderno!';
          }
        }
      } catch (err) {
        console.warn('Error consultando progreso:', err);
      }
    }, 400);
  }

  // =========================================================================
  // 5. FLECHAS PARA CONTROLAR EL MOVIMIENTO DEL BRAZO (JOGGING)
  // =========================================================================

  // Selector de tamaño de paso
  document.querySelectorAll('.btn-step').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.btn-step').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.currentStep = parseFloat(btn.dataset.step);
    });
  });

  async function jog(dx = 0, dy = 0, dz = 0, dr = 0) {
    if (state.isDrawing) {
      console.warn('No se permite mover durante el dibujo activo.');
      return;
    }

    try {
      const res = await fetch('/api/robot/move-rel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dx, dy, dz, dr })
      });

      if (!res.ok) {
        const err = await res.json();
        console.warn('Error jog:', err.detail);
      } else {
        const data = await res.json();
        updatePoseDisplay(data.pose);
      }
    } catch (e) {
      console.error('Fallo en petición jog:', e);
    }
  }

  // Flechas Plano XY
  document.getElementById('btnJogXUp').addEventListener('click', () => jog(+state.currentStep, 0, 0));
  document.getElementById('btnJogXDown').addEventListener('click', () => jog(-state.currentStep, 0, 0));
  document.getElementById('btnJogYLeft').addEventListener('click', () => jog(0, +state.currentStep, 0));
  document.getElementById('btnJogYRight').addEventListener('click', () => jog(0, -state.currentStep, 0));

  // Diagonales
  document.getElementById('btnJogDiagUL').addEventListener('click', () => jog(+state.currentStep, +state.currentStep, 0));
  document.getElementById('btnJogDiagUR').addEventListener('click', () => jog(+state.currentStep, -state.currentStep, 0));
  document.getElementById('btnJogDiagDL').addEventListener('click', () => jog(-state.currentStep, +state.currentStep, 0));
  document.getElementById('btnJogDiagDR').addEventListener('click', () => jog(-state.currentStep, -state.currentStep, 0));

  // Home
  document.getElementById('btnJogHome').addEventListener('click', async () => {
    if (confirm('¿Ejecutar rutina de calibración / Homing del Dobot?')) {
      try {
        const res = await fetch('/api/robot/home', { method: 'POST' });
        const data = await res.json();
        updatePoseDisplay(data.pose);
      } catch (e) {
        alert('Error ejecutando homing: ' + e);
      }
    }
  });

  // Flechas Eje Z
  document.getElementById('btnJogZUp').addEventListener('click', () => jog(0, 0, +state.currentStep));
  document.getElementById('btnJogZDown').addEventListener('click', () => jog(0, 0, -state.currentStep));

  // Presets Rápidos
  btnPresetHover.addEventListener('click', async () => {
    // Subir a Z_hover
    try {
      await fetch('/api/robot/move-abs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ z: state.origin.z_hover })
      });
    } catch (e) {
      console.error(e);
    }
  });

  btnPresetPaper.addEventListener('click', async () => {
    // Bajar a Z_draw
    try {
      await fetch('/api/robot/move-abs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ z: state.origin.z_draw })
      });
    } catch (e) {
      console.error(e);
    }
  });

  // Control por Teclado
  window.addEventListener('keydown', (e) => {
    // Ignorar si el foco está en un input de texto
    if (['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;

    const step = e.shiftKey ? state.currentStep * 2.0 : state.currentStep;

    switch (e.key) {
      case 'ArrowUp':
        e.preventDefault();
        jog(+step, 0, 0);
        break;
      case 'ArrowDown':
        e.preventDefault();
        jog(-step, 0, 0);
        break;
      case 'ArrowLeft':
        e.preventDefault();
        jog(0, +step, 0);
        break;
      case 'ArrowRight':
        e.preventDefault();
        jog(0, -step, 0);
        break;
      case 'PageUp':
        e.preventDefault();
        jog(0, 0, +step);
        break;
      case 'PageDown':
        e.preventDefault();
        jog(0, 0, -step);
        break;
    }
  });

  // =========================================================================
  // 6. PUNTO DE INICIO INDICADO ("Que comience a dibujar desde ese punto que se indique")
  // =========================================================================

  btnSetOriginFromCurrent.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/robot/set-origin-from-current', { method: 'POST' });
      const data = await res.json();
      if (data.status === 'ok') {
        updateOriginDisplay(data.origin);

        // Si ya hay boceto, actualizar vista previa con la nueva ubicación
        if (data.sketch_updated) {
          refreshPreview();
        }

        // Efecto visual de confirmación en el botón
        const originalText = btnSetOriginFromCurrent.textContent;
        btnSetOriginFromCurrent.textContent = '✔ ¡Punto de Inicio Establecido!';
        btnSetOriginFromCurrent.classList.add('btn-success');
        setTimeout(() => {
          btnSetOriginFromCurrent.textContent = originalText;
          btnSetOriginFromCurrent.classList.remove('btn-success');
        }, 1500);
      }
    } catch (e) {
      alert('Error fijando punto de inicio: ' + e);
    }
  });

  btnMoveToOrigin.addEventListener('click', async () => {
    try {
      await fetch('/api/robot/move-to-origin?hover=true', { method: 'POST' });
    } catch (e) {
      console.error(e);
    }
  });

  btnUpdateOriginManual.addEventListener('click', async () => {
    try {
      const x = parseFloat(originX.value);
      const y = parseFloat(originY.value);
      const z_draw = parseFloat(originZDraw.value);
      const z_hover = parseFloat(originZHover.value);

      const res = await fetch('/api/robot/set-origin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ x, y, z_draw, z_hover })
      });

      const data = await res.json();
      if (data.status === 'ok') {
        updateOriginDisplay(data.origin);
        if (data.sketch_updated) {
          refreshPreview();
        }
      }
    } catch (e) {
      alert('Error guardando valores de origen: ' + e);
    }
  });

  async function refreshPreview() {
    try {
      const res = await fetch('/api/update-preview', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        sketchPreviewImg.src = data.preview_image;
        metaOriginPos.textContent = `X=${data.origin.x.toFixed(1)}, Y=${data.origin.y.toFixed(1)}`;
      }
    } catch (e) {
      console.warn('Error refrescando preview:', e);
    }
  }

  // =========================================================================
  // 7. MONITORIZACIÓN DE ESTADO Y COORDENADAS
  // =========================================================================

  function updatePoseDisplay(pose) {
    if (!pose) return;
    state.currentPose = pose;
    poseX.textContent = Number(pose.x).toFixed(2);
    poseY.textContent = Number(pose.y).toFixed(2);
    poseZ.textContent = Number(pose.z).toFixed(2);
    poseR.textContent = Number(pose.r).toFixed(2);
  }

  function updateOriginDisplay(orig) {
    if (!orig) return;
    state.origin = orig;
    originX.value = Number(orig.x).toFixed(2);
    originY.value = Number(orig.y).toFixed(2);
    originZDraw.value = Number(orig.z_draw).toFixed(2);
    originZHover.value = Number(orig.z_hover).toFixed(2);
  }

  async function pollStatus() {
    try {
      const res = await fetch('/api/status');
      if (!res.ok) return;
      const data = await res.json();

      updatePoseDisplay(data.pose);
      if (data.origin) updateOriginDisplay(data.origin);

      // Estado de conexión
      robotStatusBadge.className = 'status-badge';
      if (data.mock) {
        robotStatusBadge.classList.add('mock');
        robotStatusText.textContent = 'Simulación (Mock)';
        mockModeSwitch.checked = true;
      } else if (data.connected) {
        robotStatusBadge.classList.add('connected');
        robotStatusText.textContent = 'Hardware Conectado';
        mockModeSwitch.checked = false;
      } else {
        robotStatusBadge.classList.add('disconnected');
        robotStatusText.textContent = 'Desconectado';
      }

      dobotPortInfo.textContent = data.port ? `Puerto: ${data.port}` : 'Sin puerto serie';

    } catch (e) {
      console.warn('Error en sondeo de estado:', e);
    }
  }

  // Conmutador de modo simulación / hardware
  mockModeSwitch.addEventListener('change', async () => {
    const wantMock = mockModeSwitch.checked;
    try {
      await fetch('/api/robot/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mock: wantMock })
      });
      pollStatus();
    } catch (e) {
      console.error('Error conmutando modo:', e);
    }
  });

  btnReconnect.addEventListener('click', async () => {
    try {
      await fetch('/api/robot/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mock: mockModeSwitch.checked })
      });
      pollStatus();
    } catch (e) {
      console.error(e);
    }
  });

  // Iniciar sondeo continuo
  setInterval(pollStatus, 500);
  pollStatus();

  // Iniciar cámara
  initWebcam();
});
