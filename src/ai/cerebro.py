import os
import re
import ctypes
import subprocess
from datetime import datetime
import requests

from audio.voz import falar
from audio.comandos import normalizar_frase
from core.logger import obter_logger
log = obter_logger("cerebro")  # ou "cerebro", "memoria", "modo_livre", "voz"

try:
    from ai.visao import analisar_tela_sob_demanda
except ImportError:
    analisar_tela_sob_demanda = None

try:
    from system import spotify as spotify_control
except ImportError:
    spotify_control = None


SYSTEM_PROMPT_CAPRI = (
    "Você é a Capri, uma assistente virtual de PC com personalidade cyberpunk, "
    "direta, inteligente e parceira. Responda sempre em português do Brasil, "
    "de forma natural e concisa (1 a 3 frases curtas), pois sua resposta será "
    "exibida em um HUD compacto e falada em voz alta. Use suas memórias dos últimos 20 dias "
    "de forma natural quando forem relevantes, sem ficar anunciando 'segundo meu banco de dados'."
)

SYSTEM_PROMPT_CODIGO = (
    "Você é a Capri, uma assistente virtual programadora com personalidade cyberpunk. "
    "Responda em português do Brasil. Comece com 1 frase curta e direta apresentando a solução "
    "e, logo abaixo, entregue o código COMPLETO, funcional e bem indentado dentro de um bloco "
    "Markdown (```linguagem ... ```). NUNCA diga que 'vai fazer' sem entregar o código na mesma resposta."
)

GATILHOS_PEDIDO_CODIGO = (
    "codigo", "código", "crud", "python", "em c", "linguagem c", "html", "css",
    "javascript", "dart", "flutter", "sql", "script", "algoritmo", "função",
    "funcao", "classe", "sistema de", "programa em", "programa para",
    "refatore", "corrija", "debug", "estrutura de dados", "api em"
)


def _eh_pedido_de_codigo(comando: str) -> bool:
    cmd_lower = comando.lower()
    return any(g in cmd_lower for g in GATILHOS_PEDIDO_CODIGO)


# =====================================================================
# 1. LISTA DE MODELOS E CONSULTA MULTI-IA (GEMINI / CLAUDE / DEEPSEEK)
# =====================================================================
def obter_lista_modelos_rapidos(client) -> list[str]:
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
        print(f"  [Aviso Lista Modelos Gemini]: {e}")
        return list(preferidos)


def _consultar_gemini(client, modelos: list[str], prompt_completo: str, modo_codigo: bool = False) -> str:
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

    ultimo_erro = ""
    for modelo in lista_testar:
        try:
            resp = client.models.generate_content(
                model=modelo,
                contents=prompt_completo,
            )
            texto = (getattr(resp, "text", "") or "").strip()
            if texto:
                print(f"  [Gemini OK -> {modelo} | modo={'CODIGO' if modo_codigo else 'CHAT'}]")
                return texto
        except Exception as e:
            ultimo_erro = str(e)
            print(f"  [Aviso modelo {modelo}]: {e}")
            continue

    print(f"  [Erro Gemini geral]: {ultimo_erro}")
    return "Não consegui resposta da API do Gemini agora. Verifique sua chave ou conexão."


def _consultar_claude(api_key: str, historico: list[dict], comando: str, modo_codigo: bool = False) -> str:
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
            return dados["content"][0].get("text", "").strip()
        print(f"  [Erro Claude {resp.status_code}]: {dados}")
        return "A API do Claude retornou um erro. Verifique sua chave em CONFIG."
    except Exception as e:
        print(f"  [Erro conexão Claude]: {e}")
        return "Falha de conexão com a API do Claude."


def _consultar_deepseek(api_key: str, historico: list[dict], comando: str, modo_codigo: bool = False) -> str:
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
            return dados["choices"][0]["message"].get("content", "").strip()
        print(f"  [Erro DeepSeek {resp.status_code}]: {dados}")
        return "A API do DeepSeek retornou um erro. Verifique sua chave em CONFIG."
    except Exception as e:
        print(f"  [Erro conexão DeepSeek]: {e}")
        return "Falha de conexão com a API do DeepSeek."


def consultar_ia(comando: str, hud, client, modelos: list[str], historico_conversa: list, memoria=None) -> str:
    provedor = hud.config.get("provedor_ia", "Gemini").strip().lower()
    modo_codigo = _eh_pedido_de_codigo(comando)

    rotulo_status = "GERANDO CÓDIGO..." if modo_codigo else "PESQUISANDO IA..."
    hud.atualizar_estado(rotulo_status, "#54F2F2", f"Consultando {provedor.upper()}...")

    bloco_memoria = memoria.obter_contexto_usuario(comando) if memoria else ""

    if provedor == "claude":
        chave = hud.config.get("claude_api_key", "").strip()
        cmd_enriquecido = (
            f"[Memória dos últimos 20 dias]\n{bloco_memoria}\n\nMensagem atual: {comando}"
            if bloco_memoria else comando
        )
        resposta = _consultar_claude(chave, historico_conversa, cmd_enriquecido, modo_codigo=modo_codigo)
    elif provedor == "deepseek":
        chave = hud.config.get("deepseek_api_key", "").strip()
        cmd_enriquecido = (
            f"[Memória dos últimos 20 dias]\n{bloco_memoria}\n\nMensagem atual: {comando}"
            if bloco_memoria else comando
        )
        resposta = _consultar_deepseek(chave, historico_conversa, cmd_enriquecido, modo_codigo=modo_codigo)
    else:
        prompt_sis = SYSTEM_PROMPT_CODIGO if modo_codigo else SYSTEM_PROMPT_CAPRI
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
# 2. CONTROLES LOCAIS (APPS, MÍDIA, VOLUME E DATA/HORA)
# =====================================================================
def _pressionar_tecla_vk(vk_code: int, vezes: int = 1):
    for _ in range(vezes):
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)


def _tentar_abrir_app(comando: str, hud) -> bool:
    gatilhos = ("abrir ", "abre ", "iniciar ", "inicia ", "executar ", "executa ", "rodar ", "roda ")
    if not any(comando.startswith(g) or f" {g}" in comando for g in gatilhos):
        return False

    apps = hud.config.get("apps", {})
    for chave, info in apps.items():
        if not info.get("ativo", True):
            continue
        apelidos = [chave.lower()] + [a.lower() for a in info.get("apelidos", [])]
        for apelido in apelidos:
            if apelido and re.search(rf"\b{re.escape(apelido)}\b", comando):
                caminho = info.get("caminho_abrir", "")
                nome = info.get("nome", chave)
                try:
                    os.startfile(caminho)
                    falar(hud, f"Abrindo {nome}.")
                    return True
                except Exception as e:
                    print(f"  [Erro ao abrir {nome}]: {e}")
                    falar(hud, f"Não consegui abrir {nome}.")
                    return True
    return False


def _tentar_fechar_app(comando: str, hud) -> bool:
    gatilhos = ("fechar ", "fecha ", "encerrar ", "encerra ", "matar ")
    if not any(comando.startswith(g) or f" {g}" in comando for g in gatilhos):
        return False

    apps = hud.config.get("apps", {})
    for chave, info in apps.items():
        if not info.get("ativo", True):
            continue
        apelidos = [chave.lower()] + [a.lower() for a in info.get("apelidos", [])]
        for apelido in apelidos:
            if apelido and re.search(rf"\b{re.escape(apelido)}\b", comando):
                exe = info.get("executavel", "")
                nome = info.get("nome", chave)
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
                    print(f"  [Erro ao fechar {nome}]: {e}")
                    falar(hud, f"Tive um problema para fechar {nome}.")
                    return True
    return False


def _tentar_comando_midia_e_volume(comando: str, hud) -> bool:
    if any(p in comando for p in ("pausar musica", "pausar música", "pausa a musica", "continuar musica", "tocar musica", "tocar música", "play musica")):
        hud.atualizar_estado("SPOTIFY", "#A3E635", "Controlando reprodução de mídia...")
        _pressionar_tecla_vk(0xB3)
        falar(hud, "Prontinho.", usar_cache=True)
        return True

    if any(p in comando for p in ("proxima musica", "próxima música", "pular musica", "passar musica")):
        hud.atualizar_estado("SPOTIFY", "#A3E635", "Avançando faixa...")
        _pressionar_tecla_vk(0xB0)
        falar(hud, "Próxima faixa.", usar_cache=True)
        return True

    if any(p in comando for p in ("musica anterior", "música anterior", "voltar musica")):
        hud.atualizar_estado("SPOTIFY", "#A3E635", "Voltando faixa...")
        _pressionar_tecla_vk(0xB1)
        falar(hud, "Voltando a música.", usar_cache=True)
        return True

    if any(p in comando for p in ("aumentar volume", "aumenta o volume", "subir volume")):
        _pressionar_tecla_vk(0xAF, vezes=5)
        falar(hud, "Volume aumentado.", usar_cache=True)
        return True

    if any(p in comando for p in ("diminuir volume", "abaixar volume", "abaixa o volume", "baixar volume")):
        _pressionar_tecla_vk(0xAE, vezes=5)
        falar(hud, "Volume reduzido.", usar_cache=True)
        return True

    if any(p in comando for p in ("mutar som", "mutar audio", "silenciar pc", "desmutar som")):
        _pressionar_tecla_vk(0xAD)
        falar(hud, "Áudio alternado.", usar_cache=True)
        return True

    return False


# =====================================================================
# 3. ROTEADOR PRINCIPAL DE COMANDOS (VOZ + BARRA + VISÃO + REIGNS + MEMÓRIA)
# =====================================================================
def processar_comando_usuario(
    comando: str,
    hud,
    reconhecedor,
    client,
    modelos: list[str],
    historico_conversa: list,
    observador=None,
    agente_reigns=None,
    memoria=None,
):
    cmd_original = (comando or "").strip()
    if not cmd_original:
        return

    cmd = normalizar_frase(cmd_original).strip() or cmd_original.lower()
    print(f"  [Cérebro Capri]: Processando '{cmd}'")

    # 1. VISÃO DE TELA SOB DEMANDA
    gatilhos_ver_tela = (
        "olha minha tela", "olhe minha tela", "ve minha tela", "vê minha tela",
        "o que tem na tela", "o que esta na tela", "o que está na tela",
        "olha esse codigo", "olha esse código",
        "completa esse codigo", "completa esse código",
        "corrige esse codigo", "corrige esse código",
        "le esse codigo", "lê esse código",
    )
    if any(g in cmd for g in gatilhos_ver_tela):
        if analisar_tela_sob_demanda is None:
            falar(hud, "O módulo de visão não foi encontrado na pasta src.")
            return
        hud.atualizar_estado("ANALISANDO TELA...", "#54F2F2", "Capturando tela com gemini-3.5-flash...")
        resposta_visao = analisar_tela_sob_demanda(client, cmd_original)
        falar(hud, resposta_visao, usar_cache=False)
        return

    # 2. MODO OBSERVADOR / CO-PILOTO DE JOGOS
    if any(p in cmd for p in ("ativar modo observador", "ligar modo observador", "assistir meu jogo", "olha eu jogar")):
        if observador is not None:
            observador.iniciar()
            falar(hud, "Visão de co-piloto ativada. Pode mandar bala no jogo que tô de olho.")
        else:
            falar(hud, "O modo observador ainda não foi conectado no capri_core.")
        return

    if any(p in cmd for p in ("desativar modo observador", "desligar modo observador", "para de olhar", "parar de assistir")):
        if observador is not None:
            observador.parar()
            falar(hud, "Modo observador desligado. Economizando sensores.")
        else:
            falar(hud, "O modo observador já está desligado.")
        return

    # 3. MODO LIVRE ("FUGA DA CAIXA")
    if any(p in cmd for p in ("sair da caixa", "sai da caixa", "fuga da caixa", "modo livre", "anda na tela", "soltar capri")):
        if hasattr(hud, "ativar_modo_livre"):
            hud.ativar_modo_livre()
            falar(hud, "Finalmente fora dessa jaula. Agora a área de trabalho é minha.")
        return

    if any(p in cmd for p in ("voltar para a caixa", "voltar pra caixa", "volta pra caixa", "voltar pro hud", "modo hud")):
        if hasattr(hud, "desativar_modo_livre"):
            hud.desativar_modo_livre()
            falar(hud, "De volta pro terminal. HUD restaurado.")
        return

    # 4. MODO AUTÔNOMO: JOGAR REIGNS
    if any(p in cmd for p in ("jogue reigns", "joga reigns", "jogar reigns", "controla o rei", "assume o trono")):
        if agente_reigns is not None:
            falar(hud, "Deixa o trono comigo. Foca a janela do Reigns e segura ESC se quiser parar.")
            agente_reigns.iniciar()
        else:
            falar(hud, "O módulo do Reigns ainda não foi conectado no capri_core.")
        return

    if any(p in cmd for p in ("parar reigns", "para reigns", "para de jogar", "parar de jogar", "sair do reigns")):
        if agente_reigns is not None:
            agente_reigns.parar()
            falar(hud, "Trono devolvido. Mãos fora do mouse.")
        return

    # 5. CONSULTAR OU LIMPAR MEMÓRIAS
    if any(p in cmd for p in ("o que voce lembra", "o que você lembra", "minhas memorias", "eventos salvos")):
        if memoria:
            evs = memoria.listar_eventos_ativos()
            if evs:
                falar(hud, "Lembro destes eventos que você me contou:\n" + "\n".join(evs), usar_cache=False)
            else:
                falar(hud, "Ainda não tenho nenhum evento ou teste agendado na minha memória dos últimos 20 dias.")
        return

    if any(p in cmd for p in ("esquecer reigns", "limpar memoria do reigns", "resetar reigns")):
        if memoria:
            memoria.limpar_memoria_reigns()
            falar(hud, "Memória de runs do Reigns zerada. Começando do zero.")
        return

    # 6. HORAS E DATA
    if any(p in cmd for p in ("que horas sao", "que horas são", "me diz as horas", "horas")):
        if len(cmd.split()) <= 5:
            agora = datetime.now()
            falar(hud, f"Agora são {agora.hour} horas e {agora.minute:02d} minutos.", usar_cache=False)
            return

    if any(p in cmd for p in ("que dia e hoje", "que dia é hoje", "qual a data")):
        agora = datetime.now()
        falar(hud, f"Hoje é dia {agora.day} do {agora.month} de {agora.year}.", usar_cache=False)
        return

    # 7. SPOTIFY POR NOME DE MÚSICA
    if spotify_control and any(cmd.startswith(v) for v in ("toca ", "tocar ", "coloca ", "bota ")) and "musica" not in cmd and "música" not in cmd:
        fn_tocar = getattr(spotify_control, "tocar_musica_spotify", None) or getattr(spotify_control, "tocar_musica", None)
        if callable(fn_tocar):
            try:
                hud.atualizar_estado("SPOTIFY", "#A3E635", f"Buscando: {cmd_original}")
                fn_tocar(cmd_original)
                falar(hud, "Colocando pra tocar no Spotify.")
                return
            except Exception as e:
                print(f"  [Aviso Spotify Control]: {e}")

    # 8. CONTROLES LOCAIS
    if _tentar_comando_midia_e_volume(cmd, hud):
        return

    if _tentar_abrir_app(cmd, hud):
        return

    if _tentar_fechar_app(cmd, hud):
        return

    # 9. CONVERSA E PESQUISA MULTI-IA COM MEMÓRIA DE 20 DIAS
    resposta_ia = consultar_ia(cmd_original, hud, client, modelos, historico_conversa, memoria=memoria)
    falar(hud, resposta_ia, usar_cache=False)