import io
import time
import threading
import mss
from PIL import Image
from google.genai import types

from core.logger import obter_logger

log = obter_logger("visao")

MODELO_VISAO = "gemini-3.5-flash"
MODELOS_VISAO_FALLBACK = ["gemini-3.5-flash", "gemini-3.5-flash-lite"]


def capturar_tela_jpeg(largura_max: int = 1024, qualidade: int = 75, monitor_idx: int = 1) -> bytes:
    """Captura o monitor principal direto na RAM e converte em JPEG leve."""
    # mss.mss() precisa ser instanciado dentro da thread que realiza a captura no Windows
    with mss.mss() as sct:
        indice = monitor_idx if monitor_idx < len(sct.monitors) else 1
        captura = sct.grab(sct.monitors[indice])
        img = Image.frombytes("RGB", captura.size, captura.bgra, "raw", "BGRX")

    if img.width > largura_max:
        proporcao = largura_max / float(img.width)
        nova_altura = int(img.height * proporcao)
        img = img.resize((largura_max, nova_altura), Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=qualidade, optimize=True)
    return buffer.getvalue()


def analisar_tela_sob_demanda(client, pedido_usuario: str) -> str:
    """
    Modo Sob Demanda: lê a tela em boa nitidez para ajudar com código,
    explicar erros ou responder qualquer pergunta sobre o que está aberto.
    """
    if client is None:
        return "Configure sua chave da API do Gemini antes de usar a visão de tela."

    try:
        # 1024px / qualidade 75 mantém código legível e reduz tempo de upload/processamento
        img_bytes = capturar_tela_jpeg(largura_max=1024, qualidade=75)
        parte_imagem = types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
    except Exception as e:
        log.warning("Falha ao capturar tela para visão sob demanda: %s", e)
        return "Não consegui capturar a imagem da sua tela agora."

    prompt = (
        "Você é a Capri, uma assistente virtual de PC com personalidade cyberpunk, "
        "direta, inteligente e parceira. Ignore qualquer janela pequena chamada 'CAPRI HUD' na tela.\n"
        f"Pedido do usuário: \"{pedido_usuario}\"\n"
        "Instruções:\n"
        "- Se houver código na tela (VS Code, Dev-C++, terminal, etc.), leia o trecho visível "
        "e sugira o complemento ou correção de forma clara e objetiva.\n"
        "- Seja breve o suficiente para fazer sentido tanto lendo no card quanto ouvindo por voz."
    )

    ultimo_erro = None
    for modelo in MODELOS_VISAO_FALLBACK:
        try:
            resp = client.models.generate_content(
                model=modelo,
                contents=[prompt, parte_imagem],
            )
            texto = (getattr(resp, "text", "") or "").strip()
            if texto:
                log.info("Visão sob demanda respondida via %s", modelo)
                return texto
        except Exception as e:
            ultimo_erro = e
            log.warning("Erro Visão Sob Demanda (%s): %s", modelo, e)

    if ultimo_erro and "504" in str(ultimo_erro):
        return (
            "O servidor do Gemini demorou demais para responder a imagem (erro 504). "
            "Tente novamente em alguns segundos."
        )
    return "Tive um problema ao analisar a imagem da sua tela."


class ObservadorTela:
    """
    Modo Co-Piloto para jogos (futebol, Forza, Assetto Corsa, etc.).
    Captura 2 quadros espaçados para detectar eventos reais e só comenta quando vale a pena.
    """

    def __init__(self, hud, estado_compartilhado: dict, lock: threading.Lock, funcao_falar):
        self.hud = hud
        self.estado = estado_compartilhado
        self.lock = lock
        self.funcao_falar = funcao_falar

        self.ativo = False
        self.thread = None
        self.ultimo_comentario_ts = 0.0
        self.cooldown_segundos = 14.0  # Evita que ela fale sem parar
        self.ultimo_resumo = ""

    def iniciar(self):
        if self.ativo:
            return
        self.ativo = True
        self.thread = threading.Thread(target=self._loop_observador, daemon=True)
        self.thread.start()
        log.info("Modo Observador ATIVADO.")

    def parar(self):
        if not self.ativo:
            return
        self.ativo = False
        log.info("Modo Observador DESATIVADO.")

    def _loop_observador(self):
        while self.ativo and self.hud.rodando:
            try:
                client = self.estado.get("client")
                if not client or not self.estado.get("pronto"):
                    time.sleep(2.0)
                    continue

                # Respeita o tempo mínimo entre comentários
                if time.time() - self.ultimo_comentario_ts < self.cooldown_segundos:
                    time.sleep(1.0)
                    continue

                # Captura dois quadros com 2.5s de diferença para perceber ação/movimento
                frame_antes = capturar_tela_jpeg(largura_max=768, qualidade=65)
                time.sleep(2.5)
                if not self.ativo or not self.hud.rodando:
                    break
                frame_depois = capturar_tela_jpeg(largura_max=768, qualidade=65)

                comentario = self._avaliar_jogada(client, frame_antes, frame_depois)

                if comentario and "SILENCIO" not in comentario.upper():
                    self.ultimo_comentario_ts = time.time()
                    self.ultimo_resumo = comentario

                    # Ativa sprite de comemoração se for gol, vitória ou 1º lugar
                    palavras_hype = (
                        "gol", "golaço", "primeiro", "1º", "vitória", "venceu", "ganhou", "pódio"
                    )
                    if any(p in comentario.lower() for p in palavras_hype):
                        self.hud.acionar_sprite_temporario("capri-idle-happy.png", duracao=4.0)

                    # Só fala se o microfone/barra não estiver no meio de outro comando
                    if self.lock.acquire(blocking=False):
                        try:
                            self.funcao_falar(self.hud, comentario, usar_cache=False)
                            estado_pos = "MIC SILENCIADO" if self.hud.pausada else "EM ESPERA"
                            self.hud.atualizar_estado(estado_pos, self.hud.BORDER_PINK)
                        finally:
                            self.lock.release()

                time.sleep(2.5)
            except Exception as e:
                log.warning("Aviso Observador de Tela: %s", e)
                time.sleep(4.0)

    def _avaliar_jogada(self, client, frame_1: bytes, frame_2: bytes) -> str:
        p1 = types.Part.from_bytes(data=frame_1, mime_type="image/jpeg")
        p2 = types.Part.from_bytes(data=frame_2, mime_type="image/jpeg")

        prompt = (
            "Você é a Capri, assistente cyberpunk assistindo a tela do usuário em tempo real. "
            "Você recebeu 2 capturas seguidas (2.5 segundos de diferença). Ignore a janela 'CAPRI HUD'.\n"
            f"Seu último comentário foi: \"{self.ultimo_resumo}\". NÃO repita o mesmo assunto.\n\n"
            "Regras estritas de reação:\n"
            "1. JOGO DE FUTEBOL: Se acabou de sair um GOL (comemoração, placar subiu, replay de gol) "
            "ou uma defesa absurda, comemore empolgada!\n"
            "2. JOGO DE CORRIDA (Forza, Assetto Corsa, etc.): Observe o velocímetro e a posição (POS). "
            "Comente se estiver em altíssima velocidade (acima de 260 km/h), fazendo uma ultrapassagem "
            "ou se acabou de chegar/assumir o 1º lugar.\n"
            "3. QUALQUER OUTRA COISA: Se for apenas menu, tela estática, navegação normal ou jogada comum "
            "sem nada marcante, responda EXATAMENTE com a palavra: SILENCIO\n\n"
            "Se houver um evento real, responda em português do Brasil com NO MÁXIMO 1 frase curta e natural."
        )

        for modelo in MODELOS_VISAO_FALLBACK:
            try:
                resp = client.models.generate_content(
                    model=modelo,
                    contents=[prompt, p1, p2],
                )
                texto = (getattr(resp, "text", "") or "").strip()
                if texto:
                    return texto
            except Exception as e:
                log.warning("Aviso Observador (%s): %s", modelo, e)

        return "SILENCIO"