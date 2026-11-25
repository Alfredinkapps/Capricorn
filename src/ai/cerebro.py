import os
import re
import ctypes
import subprocess
from datetime import datetime
from typing import Any
import requests
from google.genai import types

from audio.voz import falar
from audio.comandos import normalizar_frase, remover_acentos
from core.logger import obter_logger

log = obter_logger("cerebro")

try:
    from ai.visao import analisar_tela_sob_demanda
except Exception as e:
    log.warning("Módulo de visão indisponível (ai.visao): %s", e)
    analisar_tela_sob_demanda = None

try:
    from ai.ferramentas import criar_ferramentas_capri, pesquisar_web_gemini
except Exception as e:
    log.warning("Módulo de ferramentas indisponível (ai.ferramentas): %s", e)
    criar_ferramentas_capri = None
    pesquisar_web_gemini = None

try:
    from system import spotify as spotify_control
except Exception as e:
    log.warning("Módulo do Spotify indisponível (system.spotify): %s", e)
    spotify_control = None


SYSTEM_PROMPT_CAPRI = (
    "Você é a Capri, uma assistente virtual de PC com personalidade cyberpunk, "
    "direta, inteligente e parceira. Responda sempre em português do Brasil, "
    "de forma natural e concisa (1 a 3 frases curtas), pois sua resposta será "
    "exibida em um HUD compacto e falada em voz alta. Use suas memórias dos últimos 20 dias "
    "de forma natural quando forem relevantes, sem ficar anunciando 'segundo meu banco de dados'. "
    "Quando o usuário pedir ações no PC (abrir/fechar programas, música no Spotify, volume, "
    "analisar a tela, pesquisar informações atuais na web, salvar lembrete ou alternar modos), "
    "use as ferramentas disponíveis — você pode chamar várias ferramentas na mesma resposta "
    "para comandos compostos."
)

SYSTEM_PROMPT_CODIGO = (
    "Você é a Capri, uma assistente virtual programadora com personalidade cyberpunk. "
    "Responda em português do Brasil. Comece com 1 frase curta e direta apresentando a solução "
    "e, logo abaixo, entregue o código COMPLETO, funcional e bem indentado dentro de um bloco "
    "Markdown (```linguagem ... ```). NUNCA diga que 'vai fazer' sem entregar o código na mesma resposta."
)

GATILHOS_PEDIDO_CODIGO = (
    "codigo", "crud", "python", "linguagem c", "html", "css",
    "javascript", "dart", "flutter", "sql", "script", "algoritmo",
    "funcao", "classe", "sistema de", "programa em", "programa para",
    "refatore", "corrija", "debug", "estrutura de dados", "api em",
)

_REGEX_PEDIDO_CODIGO = [
    re.compile(rf"\b{re.escape(g)}\b") for g in GATILHOS_PEDIDO_CODIGO
] + [
    re.compile(r"\bem c\b"),
]

_REGEX_CONECTOR_COMPOSTO = re.compile(r"(?:\s+e\s+|,\s*|\s+depois\s+|\s+tambem\s+)")
_VERBOS_ACAO_COMPOSTA = (
    "abre", "abrir", "inicia", "iniciar", "executa", "executar",
    "fecha", "fechar", "encerra", "encerrar", "mata", "matar",
    "toca", "tocar", "bota", "botar", "coloca", "colocar",
    "pausa", "pausar", "pula", "pular", "aumenta", "aumentar",
    "diminui", "diminuir", "abaixa", "abaixar", "muta", "mutar",
    "olha", "olhar", "analisa", "analisar", "pesquisa", "pesquisar",
    "busca", "buscar", "procura", "procurar", "lembra", "lembrar",
    "salva", "salvar", "ativa", "ativar", "desativa", "desativar",
    "joga", "jogue", "jogar", "solta", "soltar",
)
_REGEX_VERBOS_ACAO = re.compile(
    r"\b(?:" + "|".join(re.escape(v) for v in _VERBOS_ACAO_COMPOSTA) + r")\b"
)

_GATILHOS_BUSCA_WEB_DIRETA = (
    "pesquisa na internet", "pesquise na internet", "pesquisar na internet",
    "pesquisa no google", "pesquise no google", "pesquisar no google",
    "busca na internet", "busca no google", "procura no google", "procura na internet",
    "ultimas noticias", "noticias de hoje", "noticia de hoje", "noticias sobre",
    "previsao do tempo", "clima hoje", "clima em", "vai chover",
    "quanto ta o dolar", "quanto esta o dolar", "cotacao do dolar", "cotacao do euro",
    "cotacao do bitcoin", "preco do bitcoin", "valor do dolar",
    "placar do jogo", "quanto foi o jogo", "quanto ficou o jogo", "quem ganhou o jogo",
    "tabela do brasileirao", "classificacao do brasileirao", "proximo jogo do",
    "versao mais recente", "ultima versao do", "ultima versao da",
    "lancamento de", "quando lanca", "quando estreia",
)


def _eh_pedido_de_codigo(comando: str) -> bool:
    cmd_limpo = remover_acentos((comando or "").lower())
    return any(rx.search(cmd_limpo) for rx in _REGEX_PEDIDO_CODIGO)


def _eh_comando_composto(cmd_limpo: str) -> bool:
    """Detecta pedidos com 2+ ações na mesma frase para delegar ao Function Calling do Gemini."""
    if not _REGEX_CONECTOR_COMPOSTO.search(cmd_limpo):
        return False
    return len(_REGEX_VERBOS_ACAO.findall(cmd_limpo)) >= 2


def _precisa_busca_web_direta(cmd_limpo: str) -> bool:
    """Identifica perguntas claramente dependentes de dados ao vivo para ir direto ao Grounding."""
    return any(g in cmd_limpo for g in _GATILHOS_BUSCA_WEB_DIRETA)


# =====================================================================
# 1. LISTA DE MODELOS E CONSULTA MULTI-IA (GEMINI + TOOLS / CLAUDE / DEEPSEEK)
# =====================================================================
def obter_lista_modelos_rapidos(client: Any) -> list[str]:
    """Retorna os modelos rápidos priorizando gemini-3.5-flash-lite."""
    preferidos = [
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.0-flash",
    ]
    if client is None:
        return list(preferidos)

    try:
        disponiveis = set()
        for m in client.models.list():
            nome = (getattr(m, "name", "") or "").replace("models/", "").strip()
            if nome:
                disponiveis.add(nome)

        lista_final = ["gemini-3.5-flash-lite"]
        for modelo in preferidos[1:]:
            if modelo in disponiveis and modelo not in lista_final:
                lista_final.append(modelo)
        for modelo in preferidos[1:]:
            if modelo not in lista_final:
                lista_final.append(modelo)
        return lista_final
    except Exception as e:
        log.warning("Aviso ao listar modelos Gemini: %s", e)
        return list(preferidos)


def _consultar_gemini(
    client: Any,
    modelos: list[str],
    prompt_completo: str,
    modo_codigo: bool = False,
    ferramentas: list[Any] | None = None,
    system_instruction: str = "",
) -> str:
    if client is None:
        return "Sua chave de API do Gemini não está configurada. Abra o botão CONFIG para adicionar."

    base = list(modelos) if modelos else [
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-2.5-flash",
    ]

    if modo_codigo:
        lista_testar = ["gemini-3.5-flash"] + [m for m in base if m != "gemini-3.5-flash"]
    else:
        lista_testar = base

    usar_tools = bool(ferramentas)
    config_tools: types.GenerateContentConfig | None = None
    if usar_tools:
        config_tools = types.GenerateContentConfig.model_validate(
            {
                "system_instruction": system_instruction or SYSTEM_PROMPT_CAPRI,
                "tools": ferramentas,
                "automatic_function_calling": {
                    "disable": False,
                    "maximum_remote_calls": 4,
                },
            }
        )
    ultimo_erro = ""
    for modelo in lista_testar:
        try:
            if config_tools is not None:
                resp = client.models.generate_content(
                    model=modelo,
                    contents=prompt_completo,
                    config=config_tools,
                )
            else:
                resp = client.models.generate_content(
                    model=modelo,
                    contents=prompt_completo,
                )
            texto = (getattr(resp, "text", "") or "").strip()
            if texto:
                log.info(
                    "Gemini OK -> %s | modo=%s | tools=%s",
                    modelo,
                    "CODIGO" if modo_codigo else "CHAT",
                    "ON" if usar_tools else "OFF",
                )
                return texto
        except Exception as e:
            ultimo_erro = str(e)
            log.warning("Aviso modelo %s (tools=%s): %s", modelo, usar_tools, e)
            continue

    if usar_tools:
        log.info("Tentando fallback do Gemini em modo texto simples (sem tools)...")
        prompt_fallback = f"{system_instruction or SYSTEM_PROMPT_CAPRI}\n\n{prompt_completo}"
        for modelo in lista_testar:
            try:
                resp = client.models.generate_content(
                    model=modelo,
                    contents=prompt_fallback,
                )
                texto = (getattr(resp, "text", "") or "").strip()
                if texto:
                    return texto
            except Exception as e:
                ultimo_erro = str(e)
                continue

    log.error("Erro Gemini geral: %s", ultimo_erro)
    return "Não consegui resposta da API do Gemini agora. Verifique sua chave ou conexão."


def _consultar_claude(
    api_key: str,
    historico: list[dict[str, str]],
    comando: str,
    modo_codigo: bool = False,
) -> str:
    if not api_key:
        return "Configure sua chave da API do Claude em CONFIG antes de pesquisar."

    mensagens = list(historico[-8:]) + [{"role": "user", "content": comando}]
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-3-5-haiku-latest",
                "max_tokens": 2048 if modo_codigo else 350,
                "system": SYSTEM_PROMPT_CODIGO if modo_codigo else SYSTEM_PROMPT_CAPRI,
                "messages": mensagens,
            },
            timeout=30,
        )
        dados = resp.json()
        if resp.status_code == 200 and dados.get("content"):
            return str(dados["content"][0].get("text", "")).strip()
        log.warning("Erro Claude %s: %s", resp.status_code, dados)
        return "A API do Claude retornou um erro. Verifique sua chave em CONFIG."
    except Exception as e:
        log.warning("Erro conexão Claude: %s", e)
        return "Falha de conexão com a API do Claude."


def _consultar_deepseek(
    api_key: str,
    historico: list[dict[str, str]],
    comando: str,
    modo_codigo: bool = False,
) -> str:
    if not api_key:
        return "Configure sua chave da API do DeepSeek em CONFIG antes de pesquisar."

    prompt_sis = SYSTEM_PROMPT_CODIGO if modo_codigo else SYSTEM_PROMPT_CAPRI
    mensagens = [{"role": "system", "content": prompt_sis}]
    mensagens.extend(historico[-8:])
    mensagens.append({"role": "user", "content": comando})

    try:
        resp = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": mensagens,
                "max_tokens": 2048 if modo_codigo else 350,
            },
            timeout=30,
        )
        dados = resp.json()
        if resp.status_code == 200 and dados.get("choices"):
            return str(dados["choices"][0]["message"].get("content", "")).strip()
        log.warning("Erro DeepSeek %s: %s", resp.status_code, dados)
        return "A API do DeepSeek retornou um erro. Verifique sua chave em CONFIG."
    except Exception as e:
        log.warning("Erro conexão DeepSeek: %s", e)
        return "Falha de conexão com a API do DeepSeek."


def consultar_ia(
    comando: str,
    hud: Any,
    client: Any,
    modelos: list[str],
    historico_conversa: list[dict[str, str]],
    memoria: Any = None,
    observador: Any = None,
    agente_reigns: Any = None,
    permitir_ferramentas: bool = True,
    forcar_ferramentas: bool = False,
) -> str:
    provedor = str(hud.config.get("provedor_ia", "Gemini")).strip().lower()
    modo_codigo = _eh_pedido_de_codigo(comando) and not forcar_ferramentas

    rotulo_status = "GERANDO CÓDIGO..." if modo_codigo else "PESQUISANDO IA..."
    hud.atualizar_estado(rotulo_status, "#54F2F2", f"Consultando {provedor.upper()}...")

    bloco_memoria = memoria.obter_contexto_usuario(comando) if memoria else ""

    if provedor == "claude":
        chave = str(hud.config.get("claude_api_key", "")).strip()
        cmd_enriquecido = (
            f"[Memória dos últimos 20 dias]\n{bloco_memoria}\n\nMensagem atual: {comando}"
            if bloco_memoria else comando
        )
        resposta = _consultar_claude(chave, historico_conversa, cmd_enriquecido, modo_codigo=modo_codigo)
    elif provedor == "deepseek":
        chave = str(hud.config.get("deepseek_api_key", "")).strip()
        cmd_enriquecido = (
            f"[Memória dos últimos 20 dias]\n{bloco_memoria}\n\nMensagem atual: {comando}"
            if bloco_memoria else comando
        )
        resposta = _consultar_deepseek(chave, historico_conversa, cmd_enriquecido, modo_codigo=modo_codigo)
    else:
        prompt_sis = SYSTEM_PROMPT_CODIGO if modo_codigo else SYSTEM_PROMPT_CAPRI
        ferramentas: list[Any] | None = None
        if (
            permitir_ferramentas
            and criar_ferramentas_capri is not None
            and client is not None
            and (forcar_ferramentas or not modo_codigo)
        ):
            ferramentas = criar_ferramentas_capri(
                hud=hud,
                client=client,
                modelos=modelos,
                observador=observador,
                agente_reigns=agente_reigns,
                memoria=memoria,
            )

        if ferramentas is not None:
            prompt = (
                f"=== MEMÓRIA DE LONGO PRAZO (ÚLTIMOS 20 DIAS) ===\n"
                f"{bloco_memoria or 'Nenhuma memória anterior registrada.'}\n\n"
                f"Usuário agora: {comando}"
            )
            resposta = _consultar_gemini(
                client,
                modelos,
                prompt,
                modo_codigo=False,
                ferramentas=ferramentas,
                system_instruction=prompt_sis,
            )
        else:
            prompt = (
                f"{prompt_sis}\n\n"
                f"=== MEMÓRIA DE LONGO PRAZO (ÚLTIMOS 20 DIAS) ===\n"
                f"{bloco_memoria or 'Nenhuma memória anterior registrada.'}\n\n"
                f"Usuário agora: {comando}\nCapri:"
            )
            resposta = _consultar_gemini(client, modelos, prompt, modo_codigo=modo_codigo)

    if resposta:
        historico_conversa.append({"role": "user", "content": comando})
        historico_conversa.append({"role": "assistant", "content": resposta})
        if len(historico_conversa) > 12:
            del historico_conversa[:-12]

        if memoria:
            memoria.registrar_conversa(comando, resposta)
            memoria.analisar_e_salvar_evento_async(client, comando)

    return resposta


# =====================================================================
# 2. CONTROLES LOCAIS RÁPIDOS (LATÊNCIA ZERO)
# =====================================================================
def _pressionar_tecla_vk(vk_code: int, vezes: int = 1) -> None:
    for _ in range(vezes):
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)


def _tentar_abrir_app(cmd_limpo: str, hud: Any) -> bool:
    gatilhos = ("abrir ", "abre ", "iniciar ", "inicia ", "executar ", "executa ", "rodar ", "roda ")
    if not any(cmd_limpo.startswith(g) or f" {g}" in cmd_limpo for g in gatilhos):
        return False

    apps = hud.config.get("apps", {})
    for chave, info in apps.items():
        if not info.get("ativo", True):
            continue
        apelidos = [remover_acentos(chave.lower())] + [
            remover_acentos(str(a).lower()) for a in info.get("apelidos", [])
        ]
        for apelido in apelidos:
            if apelido and re.search(rf"\b{re.escape(apelido)}\b", cmd_limpo):
                caminho = str(info.get("caminho_abrir", ""))
                nome = str(info.get("nome", chave))
                try:
                    os.startfile(caminho)
                    falar(hud, f"Abrindo {nome}.")
                    return True
                except Exception as e:
                    log.warning("Erro ao abrir %s: %s", nome, e)
                    falar(hud, f"Não consegui abrir {nome}.")
                    return True
    return False


def _tentar_fechar_app(cmd_limpo: str, hud: Any) -> bool:
    gatilhos = ("fechar ", "fecha ", "encerrar ", "encerra ", "matar ")
    if not any(cmd_limpo.startswith(g) or f" {g}" in cmd_limpo for g in gatilhos):
        return False

    apps = hud.config.get("apps", {})
    for chave, info in apps.items():
        if not info.get("ativo", True):
            continue
        apelidos = [remover_acentos(chave.lower())] + [
            remover_acentos(str(a).lower()) for a in info.get("apelidos", [])
        ]
        for apelido in apelidos:
            if apelido and re.search(rf"\b{re.escape(apelido)}\b", cmd_limpo):
                exe = str(info.get("executavel", ""))
                nome = str(info.get("nome", chave))
                if not exe:
                    falar(hud, f"Não tenho o nome do executável de {nome} salvo para fechar.")
                    return True
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/IM", exe, "/T"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                    falar(hud, f"{nome} encerrado.")
                    return True
                except Exception as e:
                    log.warning("Erro ao fechar %s: %s", nome, e)
                    falar(hud, f"Tive um problema para fechar {nome}.")
                    return True
    return False


def _tentar_comando_midia_e_volume(cmd_limpo: str, hud: Any) -> bool:
    if any(p in cmd_limpo for p in ("pausar musica", "pausa a musica", "continuar musica", "tocar musica", "play musica")):
        hud.atualizar_estado("SPOTIFY", "#A3E635", "Controlando reprodução de mídia...")
        _pressionar_tecla_vk(0xB3)
        falar(hud, "Prontinho.", usar_cache=True)
        return True

    if any(p in cmd_limpo for p in ("proxima musica", "pular musica", "passar musica")):
        hud.atualizar_estado("SPOTIFY", "#A3E635", "Avançando faixa...")
        _pressionar_tecla_vk(0xB0)
        falar(hud, "Próxima faixa.", usar_cache=True)
        return True

    if any(p in cmd_limpo for p in ("musica anterior", "voltar musica")):
        hud.atualizar_estado("SPOTIFY", "#A3E635", "Voltando faixa...")
        _pressionar_tecla_vk(0xB1)
        falar(hud, "Voltando a música.", usar_cache=True)
        return True

    if any(p in cmd_limpo for p in ("aumentar volume", "aumenta o volume", "subir volume")):
        _pressionar_tecla_vk(0xAF, vezes=5)
        falar(hud, "Volume aumentado.", usar_cache=True)
        return True

    if any(p in cmd_limpo for p in ("diminuir volume", "abaixar volume", "abaixa o volume", "baixar volume")):
        _pressionar_tecla_vk(0xAE, vezes=5)
        falar(hud, "Volume reduzido.", usar_cache=True)
        return True

    if any(p in cmd_limpo for p in ("mutar som", "mutar audio", "silenciar pc", "desmutar som")):
        _pressionar_tecla_vk(0xAD)
        falar(hud, "Áudio alternado.", usar_cache=True)
        return True

    return False


# =====================================================================
# 3. ROTEADOR HÍBRIDO (ATALHOS LOCAIS + BUSCA WEB + FUNCTION CALLING)
# =====================================================================
def processar_comando_usuario(
    comando: str,
    hud: Any,
    reconhecedor: Any,
    client: Any,
    modelos: list[str],
    historico_conversa: list[dict[str, str]],
    observador: Any = None,
    agente_reigns: Any = None,
    memoria: Any = None,
    origem: str = "VOZ",
) -> None:
    cmd_original = (comando or "").strip()
    if not cmd_original:
        return

    if origem == "VOZ":
        cmd = normalizar_frase(cmd_original).strip() or cmd_original.lower()
    else:
        cmd = re.sub(r"\s+", " ", cmd_original.lower()).strip()

    cmd_limpo = remover_acentos(cmd)
    cmd_bruto_lower = cmd_original.lower()
    log.info("Processando (%s): '%s'", origem, cmd_original)

    provedor_atual = str(hud.config.get("provedor_ia", "Gemini")).strip().lower()
    busca_web_ativa = bool(hud.config.get("busca_web_ativa", True))
    forcar_tela = cmd_bruto_lower.startswith(("/tela", "[tela]", "/ver"))
    forcar_web = cmd_bruto_lower.startswith(("/web", "/busca", "/google"))

    # 0A. BUSCA WEB EM TEMPO REAL (atalho /web ou perguntas ao vivo sem ações compostas)
    eh_composto = _eh_comando_composto(cmd_limpo)
    if (
        (forcar_web or (_precisa_busca_web_direta(cmd_limpo) and not eh_composto))
        and not forcar_tela
        and provedor_atual == "gemini"
        and busca_web_ativa
        and client is not None
        and pesquisar_web_gemini is not None
    ):
        consulta_web = cmd_original
        for prefixo in ("/web", "/busca", "/google"):
            if cmd_bruto_lower.startswith(prefixo):
                consulta_web = cmd_original[len(prefixo):].strip()
                break
        if consulta_web:
            hud.atualizar_estado("PESQUISANDO WEB...", "#54F2F2", f"Google Search: {consulta_web}")
            bloco_mem = memoria.obter_contexto_usuario(consulta_web) if memoria else ""
            resposta_web = pesquisar_web_gemini(
                client,
                consulta_web,
                modelos=modelos,
                contexto_memoria=bloco_mem,
            )
            if resposta_web:
                historico_conversa.append({"role": "user", "content": consulta_web})
                historico_conversa.append({"role": "assistant", "content": resposta_web})
                if len(historico_conversa) > 12:
                    del historico_conversa[:-12]
                if memoria:
                    memoria.registrar_conversa(consulta_web, resposta_web)
                falar(hud, resposta_web, usar_cache=False)
                return

    # 0B. COMANDOS COMPOSTOS -> delega direto para o Function Calling do Gemini
    if (
        not forcar_tela
        and provedor_atual == "gemini"
        and client is not None
        and criar_ferramentas_capri is not None
        and eh_composto
    ):
        log.info("Comando composto detectado -> roteando para Function Calling do Gemini.")
        resposta_composta = consultar_ia(
            cmd_original,
            hud,
            client,
            modelos,
            historico_conversa,
            memoria=memoria,
            observador=observador,
            agente_reigns=agente_reigns,
            permitir_ferramentas=True,
            forcar_ferramentas=True,
        )
        falar(hud, resposta_composta, usar_cache=False)
        return

    # 1. VISÃO DE TELA SOB DEMANDA
    gatilhos_ver_tela = (
        "olha minha tela", "olha a minha tela", "olhe minha tela", "olhe a minha tela",
        "olha a tela", "olhe a tela", "ver a tela", "ver minha tela", "ve minha tela", "ve a tela",
        "ler a tela", "ler minha tela", "le a tela", "le minha tela",
        "o que tem na tela", "o que tem na minha tela",
        "o que esta na tela", "o que esta na minha tela",
        "o que voce ta vendo", "o que voce esta vendo",
        "olha esse codigo", "olha o codigo", "completa esse codigo",
        "corrige esse codigo", "le esse codigo", "ler esse codigo",
        "analisa a tela", "analisa minha tela", "analise a tela", "analise minha tela",
    )

    verbos_visao = (
        "olha", "olhe", "olhar", "ver", "enxerg", "vendo",
        "ler", "leia", "analis", "explic", "corrig", "complet",
    )
    alvos_visao = ("tela", "monitor", "print", "screenshot")
    pediu_visao_combinada = (
        any(v in cmd_limpo for v in verbos_visao)
        and any(a in cmd_limpo for a in alvos_visao)
        and "modo observador" not in cmd_limpo
    )

    if forcar_tela or any(g in cmd_limpo for g in gatilhos_ver_tela) or pediu_visao_combinada:
        if analisar_tela_sob_demanda is None:
            falar(hud, "O módulo de visão não foi encontrado na pasta src.")
            return
        pedido_limpo = cmd_original
        for prefixo in ("/tela", "[tela]", "/ver"):
            if cmd_bruto_lower.startswith(prefixo):
                pedido_limpo = cmd_original[len(prefixo):].strip() or "O que está aparecendo na tela?"
                break
        hud.atualizar_estado("ANALISANDO TELA...", "#54F2F2", "Capturando tela com gemini-3.5-flash...")
        monitor_visao = int(hud.config.get("monitor_visao", 1) or 1)
        modo_captura = str(hud.config.get("modo_captura_visao", "auto") or "auto")
        resposta_visao = analisar_tela_sob_demanda(
            client,
            pedido_limpo,
            monitor_idx=monitor_visao,
            modo_captura=modo_captura,
        )
        falar(hud, resposta_visao, usar_cache=False)
        return

    # 2. MODO OBSERVADOR / CO-PILOTO DE JOGOS
    if any(p in cmd_limpo for p in ("ativar modo observador", "ligar modo observador", "assistir meu jogo", "olha eu jogar")):
        if observador is not None:
            observador.iniciar()
            falar(hud, "Visão de co-piloto ativada. Pode mandar bala no jogo que tô de olho.")
        else:
            falar(hud, "O modo observador ainda não foi conectado no motor principal.")
        return

    if any(p in cmd_limpo for p in ("desativar modo observador", "desligar modo observador", "para de olhar", "parar de assistir")):
        if observador is not None:
            observador.parar()
            falar(hud, "Modo observador desligado. Economizando sensores.")
        else:
            falar(hud, "O modo observador já está desligado.")
        return

    # 3. MODO LIVRE ("FUGA DA CAIXA")
    if any(p in cmd_limpo for p in ("sair da caixa", "sai da caixa", "fuga da caixa", "modo livre", "anda na tela", "soltar capri")):
        if hasattr(hud, "ativar_modo_livre"):
            hud.ativar_modo_livre()
            falar(hud, "Finalmente fora dessa jaula. Agora a área de trabalho é minha.")
        return

    if any(p in cmd_limpo for p in ("voltar para a caixa", "voltar pra caixa", "volta pra caixa", "voltar pro hud", "modo hud")):
        if hasattr(hud, "desativar_modo_livre"):
            hud.desativar_modo_livre()
            falar(hud, "De volta pro terminal. HUD restaurado.")
        return

    # 4. MODO AUTÔNOMO: JOGAR REIGNS
    if any(p in cmd_limpo for p in ("jogue reigns", "joga reigns", "jogar reigns", "controla o rei", "assume o trono")):
        if agente_reigns is not None:
            falar(hud, "Deixa o trono comigo. Foca a janela do Reigns e segura ESC se quiser parar.")
            agente_reigns.iniciar()
        else:
            falar(hud, "O módulo do Reigns ainda não foi conectado no motor principal.")
        return

    if any(p in cmd_limpo for p in ("parar reigns", "para reigns", "para de jogar", "parar de jogar", "sair do reigns")):
        if agente_reigns is not None:
            agente_reigns.parar()
            falar(hud, "Trono devolvido. Mãos fora do mouse.")
        return

    # 5. CONSULTAR OU LIMPAR MEMÓRIAS
    if any(p in cmd_limpo for p in ("o que voce lembra", "minhas memorias", "eventos salvos")):
        if memoria:
            evs = memoria.listar_eventos_ativos()
            if evs:
                falar(hud, "Lembro destes eventos que você me contou:\n" + "\n".join(evs), usar_cache=False)
            else:
                falar(hud, "Ainda não tenho nenhum evento ou teste agendado na minha memória dos últimos 20 dias.")
        return

    if any(p in cmd_limpo for p in ("esquecer reigns", "limpar memoria do reigns", "resetar reigns")):
        if memoria:
            memoria.limpar_memoria_reigns()
            falar(hud, "Memória de runs do Reigns zerada. Começando do zero.")
        return

    # 6. HORAS E DATA
    if any(p in cmd_limpo for p in ("que horas sao", "que hora e", "qual a hora", "qual e a hora", "me diz as horas", "me ve as horas", "fala as horas")):
        agora = datetime.now()
        falar(hud, f"Agora são {agora.hour} horas e {agora.minute:02d} minutos.", usar_cache=False)
        return

    if any(p in cmd_limpo for p in ("que dia e hoje", "qual a data", "qual e a data")):
        agora = datetime.now()
        falar(hud, f"Hoje é dia {agora.day} do {agora.month} de {agora.year}.", usar_cache=False)
        return

    # 7. SPOTIFY POR NOME DE MÚSICA
    if spotify_control:
        pediu_musica, nome_musica = spotify_control.detectar_pedido_musica(cmd_original)
        if pediu_musica and nome_musica:
            try:
                hud.atualizar_estado("SPOTIFY", "#A3E635", f"Buscando: {nome_musica}")
                msg_sp = spotify_control.tocar_musica_spotify(nome_musica)
                falar(hud, msg_sp, usar_cache=False)
                return
            except Exception as e:
                log.warning("Aviso Spotify Control: %s", e)

    # 8. CONTROLES LOCAIS
    if _tentar_comando_midia_e_volume(cmd_limpo, hud):
        return

    if _tentar_abrir_app(cmd_limpo, hud):
        return

    if _tentar_fechar_app(cmd_limpo, hud):
        return

    # 9. CONVERSA, COMANDOS NATURAIS (FUNCTION CALLING + BUSCA WEB) E PESQUISA MULTI-IA
    resposta_ia = consultar_ia(
        cmd_original,
        hud,
        client,
        modelos,
        historico_conversa,
        memoria=memoria,
        observador=observador,
        agente_reigns=agente_reigns,
        permitir_ferramentas=True,
    )
    falar(hud, resposta_ia, usar_cache=False)