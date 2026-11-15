# ⚡ CAPRI // PROJECT CAPRICORN `v0.1.3`

![Version](https://img.shields.io/badge/version-0.1.3-00F0FF?style=for-the-badge)
![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-00FF66?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.10%2B-A855F7?style=for-the-badge)
![Architecture](https://img.shields.io/badge/arquitetura-Modular%20(src%2F)-FF0055?style=for-the-badge)

> **Assistente Virtual Tática Cyberpunk para Windows** com controle nativo de sistema, integração direta com o aplicativo **Spotify Desktop**, cadastro manual de jogos/executáveis (`.exe`) por apelido de voz, síntese de voz clonada com cache instantâneo e pesquisa web em tempo real via Google Gemini.

---

## 🚀 O que há de novo na versão `0.1.3`

* 🧩 **Arquitetura 100% Modular (`src/`):** O antigo código monolítico foi dividido em 8 módulos independentes e organizados dentro da pasta `src/`, facilitando a manutenção, leitura e expansão do projeto.
* 🎵 **Integração Nativa com Spotify Desktop:** Substituição definitiva do navegador pelo aplicativo oficial do **Spotify para Windows**. A Capri pesquisa e inicia músicas dentro da própria janela do app (`spotify:search:`) e controla o **volume interno do Spotify** (`Ctrl + Cima/Baixo` direto no processo `spotify.exe`) sem abaixar o volume da voz da assistente.
* 🎮 **Seletor Manual de Executáveis (`.exe`) + Apelidos de Voz:** Agora você pode selecionar qualquer arquivo `.exe` ou atalho manualmente nas pastas do PC (pelo botão na interface ou por comando de voz) e definir como quer chamá-lo (ex: selecionar `cs2.exe` e apelidar de **"CS2"**). Inclui normalização fonética inteligente (`"cs 2"` $\rightarrow$ `"cs2"`) e inicialização no diretório raiz do jogo (`cwd`).
* 🖥️ **HUD Minimalista:** Limpeza visual da janela principal, removendo o excesso de legendas de transcrição e mantendo o prompt fixo **`Diga, CAPRI`**, o indicador de estado dinâmico e o oscilador de sinal de voz em tempo real.
* ⚡ **Energia e Sessão Aprimoradas:** Correção no reconhecimento natural para comandos de **Bloquear Tela** (`LockWorkStation`) e **Suspender PC** via chamada nativa da DLL `powrprof.dll`.

---

## 📂 Estrutura Modular do Projeto

```text
Capricorn/
├── cache/                  # Áudios de resposta rápida gerados (ignorado pelo Git)
├── src/                    # Código-fonte modularizado da Capri
│   ├── capri_core.py       # Ponto de entrada principal (inicializa threads e loops)
│   ├── hud.py              # Interface Cyberpunk, Bandeja do Sistema e Janela de Configs
│   ├── voz.py              # Escuta com VAD, Barra de Sinal, Fish Audio TTS e Cache
│   ├── cerebro_ia.py       # Roteador de comandos, Cadastro de .exe por voz e Gemini API
│   ├── spotify_control.py  # Busca, Play automático e Volume exclusivo do Spotify Desktop
│   ├── sistema_pc.py       # Energia (Bloquear, Suspender, Desligar), Tema e Relógio
│   ├── abrir_apps.py       # Abertura rápida de programas e jogos personalizados
│   └── fechar_apps.py      # Encerramento forçado de processos (taskkill)
├── .gitignore              # Proteção de chaves de API, cache e arquivos compilados
├── capri_config.json       # Chaves de API e lista de aplicativos/apelidos (gerado localmente)
└── README.md               # Documentação do projeto
```

---

## 🛠️ Funcionalidades Principais

### 1. 🎵 Controle Total do Spotify Desktop
* **Busca e Reprodução Direta:** Peça *"Capri, coloque uma música"* ou *"Capri, troque a música para [nome]"*. Ela aciona o aplicativo do Spotify, seleciona o melhor resultado e inicia a faixa sem abrir abas de navegador.
* **Volume Independente:** Peça *"Volume em 30%"*, *"Abaixar volume"* ou *"Volume no máximo"*. A Capri ajusta apenas o volume interno do Spotify e devolve o foco para a janela que você estava usando.
* **Controle de Faixas:** Comandos instantâneos para pausar, retomar, pular para a próxima música ou voltar à faixa anterior.

### 2. 🎮 Cadastro Manual de Jogos e Programas (`.exe`)
* **Via Interface Gráfica:** Abra as configurações (`⚙`) e clique em **`➕ ADICIONAR EXECUTÁVEL (.EXE) MANUALMENTE`**, escolha o arquivo `.exe` no Windows Explorer e digite como quer chamá-lo (ex: `CS2`, `Valorant`, `Photoshop`).
* **Via Comando de Voz:** Diga *"Capri, adicionar executável"*. Ela abrirá o seletor de arquivos do Windows e perguntará em voz alta: **"Como você quer chamar esse executável?"**.
* Apps cadastrados manualmente recebem destaque com estrela (`⭐`) no topo da lista de permissões e podem ser abertos (*"Capri, abrir CS2"*) ou fechados (*"Capri, fechar CS2"*).

### 3. 💻 Controle do Sistema Windows (Execução em `0.1s`)
* **Energia e Segurança:** Bloquear estação de trabalho, suspender o computador, desligar/reiniciar com timer de segurança de 10 segundos e comando de abortar desligamento.
* **Personalização:** Alternância instantânea entre o **Modo Escuro** e **Modo Claro** do Windows via Registro.
* **Execução em Segundo Plano:** Minimiza para a Bandeja do Sistema (*System Tray*) perto do relógio do Windows e inicia automaticamente junto com o sistema.

### 4. 🧠 Cérebro Gemini + Pesquisa Google em Tempo Real
* Integrada aos modelos `gemini-2.5-flash` com a ferramenta `GoogleSearch` ativada para responder perguntas sobre fatos atuais, clima, cotações, notícias e curiosidades com respostas curtas, diretas e sem marcações poluídas.

---

## 🎙️ Guia Rápido de Comandos de Voz

| Categoria | Exemplos de Comandos | Ação Executada |
| :--- | :--- | :--- |
| **Chamada** | *"Capri"* / *"Oi Capri"* | Ativa a escuta com resposta rápida em cache |
| **Spotify (Música)** | *"Coloque uma música"* / *"Trocar a música"* | Pergunta qual música você quer e dá Play no Spotify |
| **Spotify (Direto)** | *"Coloque a música Numb"* | Busca e toca a faixa imediatamente no Spotify |
| **Volume Spotify** | *"Volume em 30%"* / *"Abaixar volume"* / *"Aumentar volume"* | Ajusta o volume interno do app do Spotify |
| **Mídia** | *"Pausar música"* / *"Continuar música"* / *"Próxima música"* | Controla a reprodução atual |
| **Cadastrar `.exe`** | *"Adicionar executável"* / *"Cadastrar programa"* | Abre o seletor de `.exe` e pergunta o apelido por voz |
| **Abrir / Fechar** | *"Abrir CS2"* / *"Abrir VS Code"* / *"Fechar CS2"* | Inicia ou encerra o aplicativo autorizado |
| **Energia / Tela** | *"Bloquear o PC"* / *"Suspender o PC"* | Tranca a tela do Windows ou suspende a máquina |
| **Desligamento** | *"Desligar o computador"* / *"Cancelar desligamento"* | Agenda desligamento em 10s ou cancela a contagem |
| **Sistema** | *"Modo escuro"* / *"Modo claro"* / *"Que horas são?"* | Altera o tema do Windows ou informa o horário |
| **Interface** | *"Abrir configurações"* / *"Fique quieta"* | Abre o painel de controle da Capri ou silencia o mic |

---

## ⚙️ Instalação e Uso

### 1. Pré-requisitos
* **Windows 10 ou 11** (64 bits)
* **Python 3.10 ou superior**
* **Spotify Desktop** instalado no computador (para os comandos de música)

### 2. Instalando as dependências
No terminal PowerShell, dentro da pasta raiz do projeto:

```powershell
python -m pip install google-genai pygame-ce sounddevice numpy edge-tts SpeechRecognition pystray Pillow requests
```

### 3. Executando a Capri em modo de desenvolvimento
```powershell
python src/capri_core.py
```

### 4. Compilando o executável (`Capri.exe`)
Caso queira gerar o executável único sem janela de terminal usando o **PyInstaller**:

```powershell
python -m PyInstaller --noconsole --onefile --paths src --name "Capri" src/capri_core.py
```

---

## 🔑 Configuração Inicial
Na primeira execução, clique no botão **`⚙`** no HUD (ou diga *"Capri, abrir configurações"*):
1. Insira sua **Gemini API Key** (obrigatória para perguntas gerais).
2. *(Opcional)* Insira sua **Fish Audio API Key** e **Voice ID** para utilizar voz clonada personalizada (caso deixe em branco, a Capri utilizará automaticamente a voz neural nativa em Português).
3. Marque em **Verde (`✔`)** os aplicativos que a Capri tem permissão para abrir/fechar ou clique em **`➕ ADICIONAR EXECUTÁVEL (.EXE) MANUALMENTE`** para cadastrar seus jogos e programas favoritos.