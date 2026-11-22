import io
import re
import json
import time
import ctypes
import threading
import mss
import pygame
import pyautogui
from pytweening import easeOutQuad, easeInOutQuad
from PIL import Image
from google.genai import types
from core.logger import obter_logger
log = obter_logger("reigns")  # ou "cerebro", "memoria", "modo_livre", "voz"

MODELO_REIGNS = "gemini-3.5-flash"

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.04


def _esc_pressionado() -> bool:
    """Detecta se a tecla ESC está pressionada no Windows."""
    return (ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000) != 0


def _limpar_json_bruto(texto: str) -> str:
    txt = (texto or "").strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```(?:json)?\s*", "", txt)
        txt = re.sub(r"\s*```$", "", txt)
    return txt.strip()


def _capturar_tela_reigns(largura_max: int = 1024, qualidade: int = 80) -> tuple[bytes, int, int]:
    """Captura o monitor principal em RAM e retorna (jpeg_bytes, largura_real, altura_real)."""
    with mss.mss() as sct:
        mon = sct.monitors[1]
        larg_real, alt_real = mon["width"], mon["height"]
        raw = sct.grab(mon)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    if img.width > largura_max:
        prop = largura_max / float(img.width)
        img = img.resize((largura_max, int(img.height * prop)), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=qualidade, optimize=True)
    return buf.getvalue(), larg_real, alt_real


class AgenteReigns:
    """Agente visual autônomo para a Capri jogar Reigns aprendendo a cada reinado."""

    def __init__(self, hud, estado_compartilhado: dict, lock: threading.Lock, funcao_falar, memoria=None):
        self.hud = hud
        self.estado = estado_compartilhado
        self.lock = lock
        self.funcao_falar = funcao_falar
        self.memoria = memoria

        self.ativo = False
        self.thread = None
        self.intervalo_segundos = 3.0
        self.turnos_jogados = 0
        self.run_id = 1
        self.morte_registrada_na_run = False
        self.historico_turnos = []

    def iniciar(self):
        if self.ativo:
            return
        self.ativo = True
        self.turnos_jogados = 0
        self.morte_registrada_na_run = False
        self.historico_turnos.clear()
        self.run_id = self.memoria.iniciar_nova_run_reigns() if self.memoria else 1
        self.thread = threading.Thread(target=self._loop_jogo, daemon=True)
        self.thread.start()
        print(f"  [Agente Reigns]: ATIVADO (Run #{self.run_id})! Segure ESC ou mova o mouse pro canto (0,0) para parar.")

    def parar(self):
        if not self.ativo:
            return
        self.ativo = False
        try:
            pyautogui.mouseUp(button="left")
        except Exception:
            pass
        print("  [Agente Reigns]: DESATIVADO.")

    def _falar_assincrono(self, texto: str):
        if not texto:
            return
        if hasattr(self.hud, "mostrar_balao_fala"):
            self.hud.mostrar_balao_fala(f"[REIGNS // Run #{self.run_id} - Turno {self.turnos_jogados}]\n{texto}")

        def _falar_thread():
            try:
                if pygame.mixer.music.get_busy():
                    return
            except Exception:
                pass
            if self.lock.acquire(blocking=False):
                try:
                    self.funcao_falar(self.hud, texto, usar_cache=False)
                finally:
                    self.lock.release()

        threading.Thread(target=_falar_thread, daemon=True).start()

    def _obter_area_janela_ativa(self) -> tuple[int, int, int, int]:
        """Calcula o centro exato da carta (cx, cy) e o tamanho da janela do Reigns."""
        class _RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        larg_mon, alt_mon = pyautogui.size()
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        rect = _RECT()

        if hwnd and ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            larg_j = rect.right - rect.left
            alt_j = rect.bottom - rect.top
            if larg_j >= 400 and alt_j >= 300:
                cx = rect.left + (larg_j // 2)
                cy = rect.top + int(alt_j * 0.56)
                return cx, cy, larg_j, alt_j

        return larg_mon // 2, int(alt_mon * 0.56), larg_mon, alt_mon

    def _espiar_opcoes(self) -> tuple[bytes, bytes, int, int]:
        """
        Arrasta a carta com amplitude suficiente para revelar o texto e os pontos brancos
        de ambos os lados, voltando ao centro antes de soltar o botão.
        """
        cx, cy, larg_j, alt_j = self._obter_area_janela_ativa()
        self._alvo_janela = (cx, cy, larg_j, alt_j)

        # 16% da largura da janela (mínimo 180px) revela o texto inteiro sem precisar soltar
        offset_espiar = max(180, int(larg_j * 0.16))

        try:
            pyautogui.moveTo(cx, cy, duration=0.12)
            pyautogui.mouseDown(button="left")
            time.sleep(0.12)

            # 1. Espia ESQUERDA (movimento mais suave para o Unity registrar o drag)
            pyautogui.moveTo(cx - offset_espiar, cy, duration=0.30, tween=easeOutQuad)
            time.sleep(0.35)
            img_esq, _, _ = _capturar_tela_reigns()

            # 2. Desliza para espiar DIREITA (ainda segurando o clique)
            pyautogui.moveTo(cx + offset_espiar, cy, duration=0.42, tween=easeInOutQuad)
            time.sleep(0.35)
            img_dir, _, _ = _capturar_tela_reigns()

            # 3. Volta ao centro e aguarda a carta estabilizar antes de soltar
            pyautogui.moveTo(cx, cy, duration=0.25, tween=easeOutQuad)
            time.sleep(0.18)
        finally:
            pyautogui.mouseUp(button="left")

        return img_esq, img_dir, larg_j, alt_j

    def _executar_jogada(self, escolha: str, larg: int, alt: int):
        """Executa o swipe completo na direção decidida pelo Gemini."""
        if escolha == "ESPERAR":
            return

        alvo = getattr(self, "_alvo_janela", None)
        if alvo:
            cx, cy, larg_j, _ = alvo
        else:
            cx, cy, larg_j, _ = self._obter_area_janela_ativa()

        # 30% da largura da janela (mínimo 300px) garante que o jogo aceite a decisão
        offset_confirmar = max(300, int(larg_j * 0.30))

        try:
            pyautogui.moveTo(cx, cy, duration=0.10)
            pyautogui.mouseDown(button="left")
            time.sleep(0.10)

            if escolha == "ESQUERDA":
                pyautogui.moveTo(cx - offset_confirmar, cy, duration=0.28, tween=easeOutQuad)
            else:
                pyautogui.moveTo(cx + offset_confirmar, cy, duration=0.28, tween=easeOutQuad)

            time.sleep(0.12)
        finally:
            pyautogui.mouseUp(button="left")

        pyautogui.moveTo(cx, cy, duration=0.10)
        
    def _decidir_com_gemini(self, client, img_esq: bytes, img_dir: bytes) -> dict:
        p_esq = types.Part.from_bytes(data=img_esq, mime_type="image/jpeg")
        p_dir = types.Part.from_bytes(data=img_dir, mime_type="image/jpeg")

        memoria_reigns = (
            self.memoria.obter_resumo_aprendizado_reigns(self.run_id)
            if self.memoria
            else ("\n".join(self.historico_turnos[-4:]) or "Nenhuma jogada anterior.")
        )

        prompt = (
            "Você é a Capri, uma IA cyberpunk jogando 'Reigns' ao vivo para sobreviver o MÁXIMO de anos possível.\n"
            "Você recebeu 2 imagens da MESMA carta:\n"
            "- IMAGEM 1: carta inclinada para a ESQUERDA (texto da opção esquerda e pontos brancos sobre os 4 ícones do topo).\n"
            "- IMAGEM 2: carta inclinada para a DIREITA (texto da opção direita e pontos brancos sobre os 4 ícones do topo).\n\n"
            "REGRAS ESTRATÉGICAS DE SOBREVIVÊNCIA EM REIGNS:\n"
            "1. Os 4 pilares no topo (Igreja/Cruz, Povo/Boneco, Exército/Espada, Tesouro/Dinheiro) NUNCA podem chegar a 0% nem a 100%, ou o rei morre na hora.\n"
            "2. Meta principal: manter TODAS as 4 barras próximas de 50% (faixa segura: 30% a 70%).\n"
            "3. Leia os PONTOS BRANCOS acima de cada ícone nas duas imagens: ponto grande = impacto forte; ponto pequeno = impacto leve. "
            "Use o texto da carta e da opção para prever se cada barra vai SUBIR ou DESCER. Evite empurrar barras baixas (<25%) para 0% ou altas (>75%) para 100%.\n"
            "4. Táticas de reinado longo: priorize salvaguardas (Celeiro, Torre, Catedral, Banco), recuse comidas suspeitas/bolos e experimentos do médico, "
            "evite efeitos contínuos que travem o controle das barras (como Cruzadas longas) e evite masmorras letais sem necessidade.\n"
            "5. Se a tela mostrar que o rei morreu, marque \"morreu\": true e use \"AVANCAR\". "
            "Se for transição de novo rei ou carta informativa, use \"AVANCAR\". "
            "Se a tela não for o jogo Reigns (ou estiver carregando), use \"ESPERAR\".\n\n"
            f"=== MEMÓRIA DE RUNS E LIÇÕES DO REIGNS ===\n{memoria_reigns}\n\n"
            "Responda ESTRITAMENTE em JSON com este formato:\n"
            "{\n"
            '  "carta": "nome do personagem e resumo curto da carta atual",\n'
            '  "morreu": false,\n'
            '  "barras": {"igreja": 50, "povo": 50, "exercito": 50, "tesouro": 50},\n'
            '  "escolha": "ESQUERDA" | "DIREITA" | "AVANCAR" | "ESPERAR",\n'
            '  "motivo_curto": "explicação tática de 1 linha",\n'
            '  "comentario": "frase curta e divertida da Capri reagindo à decisão (máx 14 palavras, em PT-BR)"\n'
            "}"
        )

        resp = client.models.generate_content(
            model=MODELO_REIGNS,
            contents=[prompt, p_esq, p_dir],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3,
            ),
        )
        return json.loads(_limpar_json_bruto(resp.text or "{}"))

    def _loop_jogo(self):
        self.hud.atualizar_estado("REIGNS // PRONTO", "#A3E635", "Foque a janela do Reigns... começando em 3s!")
        for _ in range(30):
            if not self.ativo or not self.hud.rodando or _esc_pressionado():
                self.parar()
                return
            time.sleep(0.1)

        while self.ativo and self.hud.rodando:
            if _esc_pressionado():
                self.parar()
                self.hud.atualizar_estado("EM ESPERA", self.hud.BORDER_PINK, "Reigns pausado via ESC.")
                self._falar_assincrono("Pausa de emergência ativada. Te devolvi o trono.")
                break

            client = self.estado.get("client")
            if not client:
                self.hud.atualizar_estado("ERRO", "#FF0055", "Configure a chave do Gemini antes de jogar.")
                self.parar()
                break

            try:
                self.hud.atualizar_estado("REIGNS // ESPIANDO", "#54F2F2", "Lendo opções da carta...")
                img_esq, img_dir, larg, alt = self._espiar_opcoes()

                if not self.ativo or _esc_pressionado():
                    continue

                self.hud.atualizar_estado("REIGNS // PENSANDO", "#9B72FF", "Calculando equilíbrio dos 4 pilares...")
                decisao = self._decidir_com_gemini(client, img_esq, img_dir)

                escolha = str(decisao.get("escolha", "ESPERAR")).upper().strip()
                if escolha not in ("ESQUERDA", "DIREITA", "AVANCAR", "ESPERAR"):
                    escolha = "ESPERAR"

                carta = str(decisao.get("carta", "Carta desconhecida")).strip()
                morreu = bool(decisao.get("morreu", False))
                comentario = str(decisao.get("comentario", "")).strip()
                motivo = str(decisao.get("motivo_curto", "")).strip()
                barras = decisao.get("barras", {})

                if morreu and not self.morte_registrada_na_run:
                    self.morte_registrada_na_run = True
                    if self.memoria and self.turnos_jogados > 0:
                        self.memoria.aprender_com_morte_reigns_async(
                            client, self.run_id, self.turnos_jogados, causa_morte=motivo or carta
                        )
                        self.run_id = max(self.run_id + 1, self.memoria.iniciar_nova_run_reigns())
                        self.turnos_jogados = 0
                elif escolha in ("ESQUERDA", "DIREITA"):
                    self.morte_registrada_na_run = False
                    self.turnos_jogados += 1
                    if self.memoria:
                        self.memoria.registrar_jogada_reigns(
                            self.run_id, self.turnos_jogados, carta, escolha, barras, motivo
                        )

                resumo = f"Run #{self.run_id} T{self.turnos_jogados}: {escolha} | {carta} | Barras={barras} | {motivo}"
                self.historico_turnos.append(resumo)
                if len(self.historico_turnos) > 10:
                    del self.historico_turnos[:-10]

                print(f"  [Reigns] {resumo}")

                if escolha != "ESPERAR":
                    self.hud.atualizar_estado(f"REIGNS // {escolha}", "#A3E635", motivo or f"Escolhendo {escolha}...")
                    self._executar_jogada(escolha, larg, alt)

                if comentario:
                    self._falar_assincrono(comentario)

            except pyautogui.FailSafeException:
                print("  [Agente Reigns]: FailSafe acionado (mouse no canto superior esquerdo).")
                self.parar()
                self.hud.atualizar_estado("EM ESPERA", self.hud.BORDER_PINK, "Reigns encerrado pelo FailSafe.")
                break
            except Exception as e:
                print(f"  [Aviso Agente Reigns]: {e}")
                time.sleep(2.0)

            passos = int(self.intervalo_segundos * 10)
            for _ in range(passos):
                if not self.ativo or not self.hud.rodando or _esc_pressionado():
                    break
                time.sleep(0.1)