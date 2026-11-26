import os
import ctypes
import subprocess
from datetime import datetime
from collections.abc import Callable
from typing import Any

from google.genai import types

from audio.comandos import remover_acentos
from core.logger import obter_logger

log = obter_logger("ferramentas")

MODELOS_BUSCA_WEB_FALLBACK = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
]

try:
    from ai.visao import analisar_tela_sob_demanda
except Exception as e:
    log.warning("Visão indisponível para ferramentas: %s", e)
    analisar_tela_sob_demanda = None

try:
    from system import spotify as spotify_control
except Exception as e:
    log.warning("Spotify indisponível para ferramentas: %s", e)
    spotify_control = None


def pesquisar_web_gemini(
    client: Any,
    consulta: str,
    modelos: list[str] | None = None,
    contexto_memoria: str = "",
) -> str:
    """
    Executa busca na web em tempo real usando Google Search Grounding do Gemini.
    Retorna resposta direta em português do Brasil pronta para HUD e voz (sem URLs longas).
    """
    if client is None:
        return "Configure sua chave da API do Gemini antes de pesquisar na web."

    pergunta = (consulta or "").strip()
    if not pergunta:
        return "Informe o que você deseja pesquisar na web."

    hoje = datetime.now().strftime("%d/%m/%Y (%H:%M)")
    instrucao = (
        f"Você é a Capri, assistente virtual cyberpunk. Data/hora atual: {hoje}. "
        "Use a pesquisa do Google para responder com dados atualizados e verificados. "
        "Responda em português do Brasil em 1 a 3 frases curtas e diretas (sem URLs nem links crus, "
        "pois o texto será lido em voz alta). Cite valores, placares, datas ou versões exatas quando aplicável."
    )

    prompt = (
        f"Contexto recente do usuário:\n{contexto_memoria}\n\nPergunta atual: {pergunta}"
        if contexto_memoria
        else pergunta
    )

    lista_modelos = list(dict.fromkeys((modelos or []) + MODELOS_BUSCA_WEB_FALLBACK))
    config_busca = types.GenerateContentConfig.model_validate(
        {
            "system_instruction": instrucao,
            "tools": [types.Tool(google_search=types.GoogleSearch())],
        }
    )

    ultimo_erro = ""
    for modelo in lista_modelos:
        try:
            resp = client.models.generate_content(
                model=modelo,
                contents=prompt,
                config=config_busca,
            )
            texto = (getattr(resp, "text", "") or "").strip()
            if texto:
                log.info("Busca Web Grounding OK -> %s | consulta='%s'", modelo, pergunta[:60])
                return texto
        except Exception as e:
            ultimo_erro = str(e)
            log.warning("Aviso Busca Web (%s): %s", modelo, e)
            continue

    log.error("Falha na Busca Web Grounding: %s", ultimo_erro)
    return ""


def _pressionar_vk(vk_code: int, vezes: int = 1) -> None:
    for _ in range(vezes):
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)


def _buscar_app_config(
    apps: dict[str, dict[str, Any]], nome_busca: str
) -> tuple[str, dict[str, Any]] | None:
    """Localiza um aplicativo ativo no dicionário de configuração por chave, nome ou apelido."""
    alvo = remover_acentos((nome_busca or "").strip().lower())
    if not alvo:
        return None

    for chave, info in apps.items():
        if not info.get("ativo", True):
            continue
        candidatos = [
            remover_acentos(chave.lower()),
            remover_acentos(str(info.get("nome", "")).lower()),
        ] + [remover_acentos(str(a).lower()) for a in info.get("apelidos", [])]
        if alvo in candidatos:
            return chave, info

    for chave, info in apps.items():
        if not info.get("ativo", True):
            continue
        candidatos = [
            remover_acentos(chave.lower()),
            remover_acentos(str(info.get("nome", "")).lower()),
        ] + [remover_acentos(str(a).lower()) for a in info.get("apelidos", [])]
        for cand in candidatos:
            if cand and (cand in alvo or alvo in cand):
                return chave, info

    return None


def criar_ferramentas_capri(
    hud: Any,
    client: Any,
    modelos: list[str] | None = None,
    observador: Any = None,
    agente_reigns: Any = None,
    memoria: Any = None,
) -> list[Callable[..., str]]:
    """
    Cria a lista de ferramentas tipadas para Function Calling no Gemini.
    Cada função captura o contexto da Capri por closure e expõe apenas parâmetros simples ao modelo.
    """

    def abrir_aplicativo(nome_app: str) -> str:
        """Abre um aplicativo ou jogo configurado no PC do usuário (ex: 'vscode', 'discord', 'spotify', 'chrome', 'valorant')."""
        apps = hud.config.get("apps", {})
        encontrado = _buscar_app_config(apps, nome_app)
        if encontrado is None:
            return f"Aplicativo '{nome_app}' não encontrado ou desativado nas configurações."

        chave, info = encontrado
        caminho = str(info.get("caminho_abrir", "")).strip()
        nome = str(info.get("nome", chave))
        if not caminho:
            return f"Caminho de abertura não configurado para {nome}."

        try:
            hud.atualizar_estado("EXECUTANDO AÇÃO...", "#A3E635", f"Abrindo {nome}...")
            os.startfile(caminho)
            log.info("[Tool] abrir_aplicativo -> %s", nome)
            return f"{nome} aberto com sucesso."
        except Exception as e:
            log.warning("[Tool] Erro ao abrir %s: %s", nome, e)
            return f"Falha ao abrir {nome}: {e}"

    def fechar_aplicativo(nome_app: str) -> str:
        """Fecha/encerra um aplicativo ou jogo em execução no Windows (ex: 'discord', 'chrome', 'spotify')."""
        apps = hud.config.get("apps", {})
        encontrado = _buscar_app_config(apps, nome_app)
        if encontrado is None:
            return f"Aplicativo '{nome_app}' não encontrado nas configurações."

        chave, info = encontrado
        exe = str(info.get("executavel", "")).strip()
        nome = str(info.get("nome", chave))
        if not exe:
            return f"Não há nome de executável (.exe) cadastrado para fechar {nome}."

        try:
            hud.atualizar_estado("EXECUTANDO AÇÃO...", "#A3E635", f"Fechando {nome}...")
            subprocess.run(
                ["taskkill", "/F", "/IM", exe, "/T"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            log.info("[Tool] fechar_aplicativo -> %s (%s)", nome, exe)
            return f"{nome} encerrado."
        except Exception as e:
            log.warning("[Tool] Erro ao fechar %s: %s", nome, e)
            return f"Falha ao fechar {nome}: {e}"

    def listar_aplicativos_disponiveis() -> str:
        """Lista os nomes dos aplicativos ativos que a Capri pode abrir ou fechar neste PC."""
        apps = hud.config.get("apps", {})
        ativos = sorted(
            str(info.get("nome", chave))
            for chave, info in apps.items()
            if info.get("ativo", True)
        )
        if not ativos:
            return "Nenhum aplicativo ativo configurado."
        return "Aplicativos disponíveis: " + ", ".join(ativos[:30])

    def tocar_musica_spotify(busca: str) -> str:
        """Busca e coloca uma música, artista ou playlist para tocar no Spotify Desktop."""
        if spotify_control is None:
            return "Módulo de controle do Spotify não está disponível."
        termo = (busca or "").strip()
        if not termo:
            return "Informe o nome da música ou artista para buscar no Spotify."
        try:
            hud.atualizar_estado("SPOTIFY", "#A3E635", f"Buscando: {termo}")
            resultado = spotify_control.tocar_musica_spotify(termo)
            log.info("[Tool] tocar_musica_spotify -> '%s'", termo)
            return str(resultado)
        except Exception as e:
            log.warning("[Tool] Erro Spotify: %s", e)
            return f"Não consegui tocar '{termo}' no Spotify: {e}"

    def controlar_midia(acao: str) -> str:
        """Controla a reprodução de mídia do Windows. Valores aceitos para acao: 'pausar', 'continuar', 'proxima', 'anterior'."""
        acao_limpa = remover_acentos((acao or "").strip().lower())
        hud.atualizar_estado("SPOTIFY", "#A3E635", f"Mídia: {acao_limpa}...")
        if spotify_control is not None and hasattr(spotify_control, "controlar_midia_windows"):
            res = str(spotify_control.controlar_midia_windows(acao_limpa))
            log.info("[Tool] controlar_midia -> %s", acao_limpa)
            return res

        mapa_vk = {
            "pausar": (0xB3, "Reprodução pausada."),
            "continuar": (0xB3, "Reprodução retomada."),
            "proxima": (0xB0, "Próxima faixa."),
            "anterior": (0xB1, "Faixa anterior."),
        }
        if acao_limpa not in mapa_vk:
            return "Ação de mídia inválida. Use: pausar, continuar, proxima ou anterior."
        vk, msg = mapa_vk[acao_limpa]
        _pressionar_vk(vk)
        log.info("[Tool] controlar_midia (VK) -> %s", acao_limpa)
        return msg

    def ajustar_volume(acao: str, porcentagem: int = -1, alvo: str = "pc") -> str:
        """
        Ajusta o volume do PC ou do Spotify.
        acao: 'aumentar', 'diminuir', 'mutar' ou 'definir'.
        porcentagem: de 0 a 100 (usado quando alvo='spotify' e acao='definir'); use -1 caso contrário.
        alvo: 'pc' (padrão) ou 'spotify'.
        """
        acao_limpa = remover_acentos((acao or "").strip().lower())
        alvo_limpo = remover_acentos((alvo or "pc").strip().lower())
        hud.atualizar_estado("EXECUTANDO AÇÃO...", "#A3E635", f"Ajustando volume ({alvo_limpo})...")

        if alvo_limpo == "spotify" and spotify_control is not None and acao_limpa != "mutar":
            nivel = porcentagem if (acao_limpa == "definir" or porcentagem >= 0) else -1
            acao_sp = "aumentar" if acao_limpa == "aumentar" else "diminuir"
            res = str(spotify_control.ajustar_volume_spotify(acao_sp, nivel_porcentagem=nivel))
            log.info("[Tool] ajustar_volume (spotify) -> acao=%s, pct=%d", acao_limpa, nivel)
            return res

        if acao_limpa == "aumentar":
            _pressionar_vk(0xAF, vezes=5)
            return "Volume do PC aumentado."
        if acao_limpa == "diminuir":
            _pressionar_vk(0xAE, vezes=5)
            return "Volume do PC reduzido."
        if acao_limpa == "mutar":
            _pressionar_vk(0xAD, vezes=1)
            return "Áudio do PC alternado (mudo/ativo)."
        return "Ação de volume não reconhecida. Use aumentar, diminuir, mutar ou definir."

    def analisar_tela_atual(pedido: str, foco_janela: bool = False) -> str:
        """
        Captura e analisa o que está aparecendo na tela ou na janela ativa do usuário.
        Use quando o usuário pedir para olhar a tela, ler um erro, revisar código aberto ou ver o que está acontecendo.
        foco_janela: True para recortar apenas a janela ativa (melhor para código/terminal), False para modo automático.
        """
        if analisar_tela_sob_demanda is None:
            return "O módulo de visão de tela não está disponível."
        hud.atualizar_estado("ANALISANDO TELA...", "#54F2F2", "Capturando tela via ferramenta...")
        monitor_visao = int(hud.config.get("monitor_visao", 1) or 1)
        modo_padrao = str(hud.config.get("modo_captura_visao", "auto") or "auto")
        modo_final = "janela_ativa" if foco_janela else modo_padrao
        log.info("[Tool] analisar_tela_atual -> pedido='%s' (modo=%s)", pedido, modo_final)
        return str(
            analisar_tela_sob_demanda(
                client,
                pedido,
                monitor_idx=monitor_visao,
                modo_captura=modo_final,
            )
        )

    def pesquisar_web(consulta: str) -> str:
        """
        Pesquisa informações atualizadas na internet em tempo real via Google Search.
        Use para notícias recentes, placares de jogos, classificação de campeonatos, previsão do tempo,
        cotação de moedas, lançamentos, preços atuais ou versões recentes de bibliotecas/softwares.
        """
        if not bool(hud.config.get("busca_web_ativa", True)):
            return "A pesquisa web em tempo real está desativada nas configurações."
        termo = (consulta or "").strip()
        if not termo:
            return "Informe o assunto para pesquisar na web."
        hud.atualizar_estado("PESQUISANDO WEB...", "#54F2F2", f"Google Search: {termo}")
        log.info("[Tool] pesquisar_web -> '%s'", termo)
        resultado = pesquisar_web_gemini(client, termo, modelos=modelos)
        return resultado or "Não consegui obter resultados atualizados da web agora."

    def salvar_lembrete(descricao: str, dias_para_perguntar: int = 2) -> str:
        """
        Salva um lembrete, prova, compromisso ou evento importante na memória de longo prazo da Capri.
        dias_para_perguntar: quantos dias até a Capri perguntar proativamente como foi (entre 1 e 14).
        """
        if memoria is None:
            return "Banco de memória indisponível."
        desc = (descricao or "").strip()
        if not desc:
            return "Descrição do lembrete vazia."
        dias = max(1, min(14, int(dias_para_perguntar)))
        salvou = memoria.salvar_evento_manual(desc, dias)
        if salvou:
            log.info("[Tool] salvar_lembrete -> '%s' (%d dia(s))", desc, dias)
            return f"Lembrete salvo: '{desc}'. Vou te perguntar sobre isso em {dias} dia(s)."
        return f"Esse lembrete ('{desc}') já estava salvo na memória."

    def alternar_modo_capri(modo: str, ativar: bool = True) -> str:
        """
        Ativa ou desativa modos especiais da Capri.
        modo: 'observador' (co-piloto de jogos), 'modo_livre' (pet andando na tela) ou 'reigns' (agente que joga Reigns).
        ativar: True para ligar, False para desligar.
        """
        m = remover_acentos((modo or "").strip().lower())
        if m == "observador":
            if observador is None:
                return "Modo observador não conectado."
            if ativar:
                observador.iniciar()
                return "Modo observador ativado."
            observador.parar()
            return "Modo observador desativado."

        if m in ("modo_livre", "livre", "pet"):
            if ativar and hasattr(hud, "ativar_modo_livre"):
                hud.ativar_modo_livre()
                return "Modo livre ativado (Capri solta na área de trabalho)."
            if not ativar and hasattr(hud, "desativar_modo_livre"):
                hud.desativar_modo_livre()
                return "Modo livre desativado (HUD restaurado)."
            return "Controle de modo livre indisponível."

        if m == "reigns":
            if agente_reigns is None:
                return "Agente do Reigns não conectado."
            if ativar:
                agente_reigns.iniciar()
                return "Agente do Reigns ativado. Foque a janela do jogo e segure ESC para parar."
            agente_reigns.parar()
            return "Agente do Reigns parado."

        return f"Modo '{modo}' desconhecido. Opções: observador, modo_livre ou reigns."

    def controlar_energia_pc(acao: str, segundos: int = 30) -> str:
            """
            Controla a energia do computador Windows do usuário (desligar, reiniciar, bloquear, suspender ou cancelar desligamento).
            acao: 'desligar', 'reiniciar', 'cancelar', 'bloquear' ou 'suspender'.
            segundos: tempo de espera em segundos antes de desligar/reiniciar (padrão 30; use 5 para imediato).
            """
            acao_limpa = remover_acentos((acao or "").strip().lower())
            tempo = max(0, min(86400, int(segundos)))
            hud.atualizar_estado("EXECUTANDO AÇÃO...", "#FF0055", f"Energia do PC: {acao_limpa}...")
    
            if acao_limpa in ("cancelar", "abortar", "cancelar_desligamento"):
                subprocess.run(
                    ["shutdown", "/a"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                log.info("[Tool] controlar_energia_pc -> cancelar")
                return "Desligamento ou reinicialização agendada cancelada."
    
            if acao_limpa in ("bloquear", "trancar", "lock"):
                log.info("[Tool] controlar_energia_pc -> bloquear")
                ctypes.windll.user32.LockWorkStation()
                return "Tela do computador bloqueada."
    
            if acao_limpa in ("suspender", "hibernar", "dormir"):
                log.info("[Tool] controlar_energia_pc -> suspender")
                ctypes.windll.powrprof.SetSuspendState(False, True, False)
                return "Computador colocado em suspensão."
    
            if acao_limpa in ("desligar", "shutdown"):
                subprocess.run(
                    ["shutdown", "/s", "/t", str(tempo)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                log.info("[Tool] controlar_energia_pc -> desligar (%ds)", tempo)
                return (
                    f"Desligamento agendado para daqui a {tempo} segundos. "
                    "Diga 'cancelar desligamento' se mudar de ideia."
                )
    
            if acao_limpa in ("reiniciar", "restart", "reboot"):
                subprocess.run(
                    ["shutdown", "/r", "/t", str(tempo)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                log.info("[Tool] controlar_energia_pc -> reiniciar (%ds)", tempo)
                return (
                    f"Reinicialização agendada para daqui a {tempo} segundos. "
                    "Diga 'cancelar desligamento' para abortar."
                )
    
            return "Ação de energia inválida. Use: desligar, reiniciar, cancelar, bloquear ou suspender."
        
    
    def obter_data_hora_atual() -> str:
        """Retorna a data e a hora atuais do computador do usuário."""
        agora = datetime.now()
        return agora.strftime("Hoje é %d/%m/%Y e agora são %H:%M.")

    ferramentas: list[Callable[..., str]] = [
        abrir_aplicativo,
        fechar_aplicativo,
        listar_aplicativos_disponiveis,
        tocar_musica_spotify,
        controlar_midia,
        ajustar_volume,
        analisar_tela_atual,
        salvar_lembrete,
        alternar_modo_capri,
        controlar_energia_pc,
        obter_data_hora_atual,
    ]
    if bool(hud.config.get("busca_web_ativa", True)):
        ferramentas.append(pesquisar_web)

    return ferramentas

    