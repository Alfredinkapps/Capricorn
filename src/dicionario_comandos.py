import re
import unicodedata

# =====================================================================
# 1. GATILHOS DE CHAMADA DA CAPRI (INCLUINDO "CAP")
# =====================================================================

# Ordenados dos nomes completos para os curtos ("cap" e "kep" no final)
GATILHOS_CAPRI = (
    "capricórnio", "capricornio", "capricorn", "capricho",
    "capri", "cápri", "cabri", "gabri", "kpri", "capre", "kapri",
    "ca pri", "capi", "carpi", "capim", "capr", "capry", "kapry",
    "cap", "kep"
)

# Expressões regulares de palavra inteira para cada gatilho (evita cortar "capri" no meio)
_REGEX_GATILHOS_CAPRI = [
    (gatilho, re.compile(rf"\b{re.escape(gatilho)}\b", re.IGNORECASE))
    for gatilho in GATILHOS_CAPRI
]

PALAVRAS_SAUDACAO_INICIAL = {
    "oi", "olá", "ola", "ei", "hey", "aí", "ai", "ô", "o", "ou",
    "eai", "eae", "fala", "opa", "bom", "dia", "boa", "tarde", "noite",
    "mano", "chefe", "linda", "querida", "assistente", "por", "favor", "pfv"
}

# =====================================================================
# 2. CORRETOR FONÉTICO (Corrige o que o microfone entende errado)
# =====================================================================

CORRECOES_FONETICAS = {
    # Jogos e Launchers
    r"\bc\s*s\s*2\b": "cs2",
    r"\bc\s*s\s*dois\b": "cs2",
    r"\bcs\s*dois\b": "cs2",
    r"\bcounter\s*strike\s*(?:2|dois)?\b": "cs2",
    r"\bcontra\s*strike\b": "cs2",
    r"\bvalor\s*ante\b": "valorant",
    r"\bvalora\b": "valorant",
    r"\bistim\b": "steam",
    r"\bestim\b": "steam",
    r"\bestin\b": "steam",
    r"\bstim\b": "steam",
    r"\bépoca\s*games\b": "epic games",
    r"\bepic\s*game\b": "epic games",
    # Programas e Dev
    r"\bv\s*s\s*code\b": "vscode",
    r"\bvs\s*cold\b": "vscode",
    r"\bvê\s*esse\s*code\b": "vscode",
    r"\bvesicode\b": "vscode",
    r"\bvisual\s*studio\s*code\b": "vscode",
    r"\bvisual\s*code\b": "vscode",
    # Música e Comunicação
    r"\bespotifai\b": "spotify",
    r"\bspot\s*fai\b": "spotify",
    r"\bsportfy\b": "spotify",
    r"\bspotifai\b": "spotify",
    r"\bespotfy\b": "spotify",
    r"\bdiscorde\b": "discord",
    r"\bdesconcorde\b": "discord",
    r"\bdis\s*cord\b": "discord",
    # Navegadores
    r"\bfire\s*fox\b": "firefox",
    r"\bfai\s*fox\b": "firefox",
    r"\bcrome\b": "chrome",
    r"\bgugou\s*crome\b": "chrome",
}

NUMEROS_POR_EXTENSO = {
    r"\bzero\b": "0", r"\bdez\b": "10", r"\bvinte\b": "20",
    r"\btrinta\b": "30", r"\bquarenta\b": "40", r"\bcinquenta\b": "50",
    r"\bsessenta\b": "60", r"\bsetenta\b": "70", r"\boitenta\b": "80",
    r"\bnoventa\b": "90", r"\bcem\b": "100"
}

_REGEX_CORRECOES = [(re.compile(padrao, re.IGNORECASE), sub) for padrao, sub in CORRECOES_FONETICAS.items()]
_REGEX_NUMEROS = [(re.compile(padrao, re.IGNORECASE), sub) for padrao, sub in NUMEROS_POR_EXTENSO.items()]
_REGEX_ESPACOS = re.compile(r"\s+")
_REGEX_LETRA_NUMERO = re.compile(r"([a-zA-Z])\s+(\d)")


# =====================================================================
# 3. DICIONÁRIO MASSIVO DE INTENÇÕES E COMANDOS
# =====================================================================

VERBOS_ABRIR = (
    "abrir", "abra", "abre", "abri", "iniciar", "inicia", "inicie",
    "executar", "executa", "execute", "rodar", "roda", "rode",
    "ligar", "liga", "ligue", "startar", "starta", "start",
    "lançar", "lança", "lance", "carregar", "carrega", "carregue",
    "entrar no", "entrar na", "entra no", "entra na", "entre no", "entre na",
    "acessar", "acessa", "acesse", "puxar", "puxa", "puxe",
    "chamar", "chama", "chame", "colocar na tela", "bota pra rodar",
    "botar pra rodar", "dar play no", "da play no", "abrir o programa",
    "abrir o aplicativo", "abrir o jogo", "inicializar", "inicializa"
)

VERBOS_FECHAR = (
    "fechar", "fecha", "feche", "encerrar", "encerra", "encerre",
    "finalizar", "finaliza", "finalize", "matar", "mata", "mate",
    "quitar", "quita", "quite", "sair do", "sair da", "sai do", "sai da",
    "parar o", "parar a", "para o", "para a", "desligar o", "desliga o",
    "derrubar", "derruba", "derrube", "eliminar", "fechar janela",
    "fechar aplicativo", "fechar programa", "fechar o jogo", "fechar processo"
)

COMANDOS_MIDIA = {
    "pausar": (
        "pausar música", "pausa a música", "pause a música", "pausar musica",
        "pausar spotify", "pausa o spotify", "pausar reprodução", "parar música",
        "para a música", "pare a música", "parar o som", "para o som",
        "pausar o som", "pausa o som", "segura o som", "dar pause", "da pause",
        "dá pause", "stop", "parar faixa", "interromper música", "silenciar música"
    ),
    "continuar": (
        "continuar música", "continue a música", "continua a música",
        "retomar música", "retoma a música", "voltar a música", "volta a música",
        "despausar", "despausa", "tirar do pause", "tira do pause",
        "dar play", "da play", "dá play", "solta o som", "solta o play",
        "continuar spotify", "continuar tocando", "voltar a tocar", "reproduzir"
    ),
    "proxima": (
        "próxima música", "proxima musica", "pular música", "pula a música",
        "pule a música", "passar música", "passa a música", "passe a música",
        "próxima faixa", "proxima faixa", "avançar música", "avança a música",
        "pular faixa", "pula essa", "passa essa", "próximo som", "skip",
        "skipar", "outra faixa", "música seguinte"
    ),
    "anterior": (
        "música anterior", "musica anterior", "voltar música", "volta a música",
        "voltar faixa", "faixa anterior", "música passada", "música de antes",
        "repetir a anterior", "som anterior", "faixa passada"
    )
}

COMANDOS_VOLUME = {
    "Contexto": (
        "volume", "som", "áudio", "audio", "música está", "musica esta",
        "música tá", "musica ta", "spotify está", "spotify ta", "barulho"
    ),
    "maximo": (
        "máximo", "maximo", "no talo", "tudo", "100", "estourando",
        "volume total", "no limite", "mais alto possível"
    ),
    "minimo": (
        "mínimo", "minimo", "baixinho", "quase mudo", "bem baixo",
        "sussurrando", "quase zero", "bem fraquinho"
    ),
    "aumentar": (
        "aumentar", "aumenta", "aumente", "subir", "sobe", "suba",
        "mais alto", "erguer", "ergue", "levantar", "levanta",
        "muito baixo", "tá baixo", "ta baixo", "está baixo", "não tô ouvindo",
        "nao to ouvindo", "dá um gás", "da um gas", "amplificar"
    ),
    "diminuir": (
        "abaixar", "abaixa", "abaixe", "diminuir", "diminui", "diminua",
        "baixar", "baixa", "baixe", "reduzir", "reduz", "reduza",
        "mais baixo", "muito alta", "muito alto", "tá alto", "ta alto",
        "está alto", "tá estourando", "ta estourando", "ensurdecedor", "suavizar"
    )
}

COMANDOS_ENERGIA = {
    "cancelar": (
        "cancelar desligamento", "cancele o desligamento", "cancela o desligamento",
        "abortar desligamento", "aborta o desligamento", "não desligar", "nao desligar",
        "não desliga", "nao desliga", "cancelar reinicialização", "deixa ligado",
        "cancela o shutdown", "parar desligamento"
    ),
    "bloquear": (
        "bloquear", "bloqueia", "bloqueie", "trancar", "tranca", "tranque",
        "tela de bloqueio", "lock screen", "proteger tela", "bloquear estação"
    ),
    "suspender": (
        "suspender", "suspende", "suspenda", "suspensão", "suspensao",
        "hibernar", "hiberna", "hiberne", "dormir", "colocar pra dormir",
        "bota pra dormir", "modo soneca", "modo descanso", "descansar o pc",
        "descansar computador", "standby", "stand by"
    ),
    "alvos_pc": (
        "computador", "pc", "p c", "notebook", "máquina", "maquina",
        "sistema", "windows", "desktop", "setup"
    ),
    "verbos_desligar": (
        "desligar", "desliga", "desligue", "encerrar", "encerra",
        "apagar", "apaga", "shutdown"
    ),
    "verbos_reiniciar": (
        "reiniciar", "reinicia", "reinicie", "resetar", "reseta",
        "reboot", "reinicializar", "recomeçar"
    )
}

COMANDOS_INTERFACE = {
    "configuracoes": (
        "abrir configurações", "abra as configurações", "abre as configurações",
        "configurar capri", "configurações", "configuracoes", "ajustes",
        "painel de controle", "central de aplicativos", "opções da capri",
        "abrir ajustes", "preferências", "preferencias"
    ),
    "cadastrar_exe": (
        "adicionar executável", "adicionar aplicativo", "adicionar programa",
        "cadastrar executável", "cadastrar aplicativo", "cadastrar programa",
        "cadastrar jogo", "adicionar jogo", "novo executável", "novo aplicativo",
        "novo programa", "selecionar executável", "mapear executável",
        "registrar aplicativo", "registrar programa", "escolher executável"
    ),
    "mutar": (
        "mutar", "silenciar", "modo silencioso", "fique quieta", "fica quieta",
        "pausar escuta", "parar de ouvir", "para de me ouvir", "desativar microfone",
        "mutar microfone", "xiu", "silêncio", "silencio", "descansar microfone"
    ),
    "horas": (
        "que horas são", "que horas sao", "que hora é", "que hora e",
        "horário", "horario", "que dia é hoje", "me vê as horas", "me ve as horas",
        "me diz as horas", "fala as horas", "horas por favor", "qual a hora"
    ),
    "desligar_capri": (
        "desligar sistema", "encerrar sistema", "pode desligar", "desligar capri",
        "fechar capri", "encerrar capri", "tchau capri", "até logo capri",
        "pode descansar", "sair da capri", "desativar capri"
    ),
    "cancelar_conversa": (
        "deixa pra lá", "deixa pra la", "nada não", "nada nao", "esquece",
        "cancelar", "cancela", "ignora", "falei errado", "não é nada", "nao e nada"
    )
}

PADROES_MUSICA_DIRETO = [
    re.compile(
        r"(?:trocar|troque|troca|mudar|mude|muda)\s+(?:a\s+|de\s+|o\s+)?(?:m[úu]sica|som|faixa)\s+(?:para|pra|por)\s+(.+)",
        re.IGNORECASE
    ),
    re.compile(
        r"(?:colocar|coloque|coloca|tocar|toque|toca|botar|bota|bote|reproduzir|reproduza|ouvir|escutar|põe|poe|lança|lanca|solta)\s+"
        r"(?:a\s+m[úu]sica\s+|o\s+som\s+|um\s+som\s+de\s+|uma\s+m[úu]sica\s+de\s+|m[úu]sica\s+)?(.+?)(?:\s+no\s+spotify|\s+pra\s+tocar|\s+por\s+favor)?$",
        re.IGNORECASE
    )
]

PALAVRAS_GENERICAS_MUSICA = {
    "uma", "outra", "alguma", "aí", "ai", "no spotify", "spotify",
    "música", "musica", "um som", "som", "qualquer uma", "qualquer",
    "uma música", "uma musica", "outra música", "outra musica", "algo"
}

VERBOS_PEDIR_MUSICA = (
    "coloque", "coloca", "colocar", "toque", "toca", "tocar",
    "bota", "bote", "botar", "troque", "troca", "trocar",
    "mude", "muda", "mudar", "outra", "ouvir", "escutar",
    "reproduzir", "solta", "lança", "lanca", "põe", "poe"
)


# =====================================================================
# 4. FUNÇÕES DE NORMALIZAÇÃO E EXTRAÇÃO RÁPIDA
# =====================================================================

def remover_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def normalizar_frase(frase: str) -> str:
    """Limpa a frase, corrige erros fonéticos do microfone e padroniza números."""
    if not frase:
        return ""

    texto = frase.lower().strip()

    for regex, substituto in _REGEX_CORRECOES:
        texto = regex.sub(substituto, texto)

    for regex, numero in _REGEX_NUMEROS:
        texto = regex.sub(numero, texto)

    texto = _REGEX_LETRA_NUMERO.sub(r"\1\2", texto)
    texto = _REGEX_ESPACOS.sub(" ", texto)
    return texto.strip()


def extrair_comando_apos_nome(frase: str) -> tuple[bool, str]:
    """Detecta qualquer variação do nome Capri (incluindo 'cap') e separa o comando limpo."""
    frase_norm = normalizar_frase(frase)

    for _, regex_gatilho in _REGEX_GATILHOS_CAPRI:
        match = regex_gatilho.search(frase_norm)
        if match:
            resto = frase_norm[match.end():].strip(" ,.!?-")
            if not resto:
                resto = frase_norm[:match.start()].strip(" ,.!?-")

            palavras = resto.split()
            while palavras and palavras[0] in PALAVRAS_SAUDACAO_INICIAL:
                palavras.pop(0)

            comando_limpo = " ".join(palavras).strip()
            return True, comando_limpo

    return False, ""