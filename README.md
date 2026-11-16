# ⚡ CAPRI // PROJECT CAPRICORN `v0.1.4`

> **Assistente Virtual Tática Cyberpunk para Windows** com arquitetura 100% modular, menu de configurações inspirado em *Cyberpunk 2077*, dicionário fonético inteligente, integração nativa com o **Spotify Desktop**, cadastro manual de executáveis (`.exe`) por voz, síntese vocal fluida sem pausas artificiais e pesquisa em tempo real via Google Gemini.

---

## 🚀 O que há de novo na versão `0.1.4`

* 🧠 **Novo Módulo `dicionario_comandos.py` (Vocabulário Expandido & Correção Fonética):**
  * **Corretor Fonético Automático:** Corrige instantaneamente termos que o microfone costuma transcrever errado em português (ex: *"espotifai"* $\rightarrow$ `spotify`, *"vê esse code"* $\rightarrow$ `vscode`, *"c s dois"* $\rightarrow$ `cs2`, *"valor ante"* $\rightarrow$ `valorant`, *"istim"* $\rightarrow$ `steam`).
  * **Gatilho Rápido `"Cap"`:** Além de *"Capri"* e *"Capricorn"*, a assistente agora reconhece a chamada curta **`"Cap"`** com verificação de palavra inteira via Regex, sem cortar comandos.
  * **Centenas de Variações Naturais:** Compreende gírias, sinônimos e números falados por extenso para abrir/fechar programas, controlar mídia, ajustar volume e gerenciar energia do PC.

* 🎨 **Menu de Configurações Cyberpunk 2077 (Layout PC):**
  * Interface `CAPRI // SYSTEM SETTINGS` totalmente redesenhada com paleta **Cyberpunk** (fundo vinho escuro `#120912`, detalhes em vermelho-coral `#E8504B` e destaques em ciano neon `#54F2F2`).
  * Navegação limpa para computador dividida em 3 abas superiores (**`APLICATIVOS`**, **`APIS & VOZ`** e **`SISTEMA`**), switches deslizantes chanfrados (`ON` / `OFF`), botão lateral chanfrado **`+ ADICIONAR .EXE`** e rodapé direto com **`SALVAR E APLICAR`**.

* 🧹 **Scanner Inteligente de Aplicativos (Sem Lixo do Sistema):**
  * Substituição da varredura bruta do Menu Iniciar por um filtro inteligente que ignora atalhos administrativos e secundários do Windows (como *ODBC Data Sources*, *Narrator*, *Node.js documentation* e *Navegação privativa*), exibindo apenas aplicativos reais do dia a dia, utilitários nativos essenciais (`Notepad`, `CMD`, `Calculadora`, `Explorador de Arquivos`, `Paint`, `Gerenciador de Tarefas`) e 100% dos `.exe` cadastrados pelo usuário.

* 🎙️ **Voz Contínua & Otimização de Performance ($O(1)$):**
  * **Fim das Respiradas Artificiais:** Remoção das quebras forçadas e ativação de `normalize: True` na API da Fish Audio para uma fala contínua, natural e direta (com respostas de chamada limpas: *"Oie."*, *"Fala."*, *"Diga lá."*, *"Tô ouvindo, fala aí."*).
  * **Sessão HTTP Persistente:** Reaproveitamento de conexão via `requests.Session()` para reduzir a latência na geração de áudio.
  * **Cache de Apps em Memória:** O arquivo `capri_config.json` só é relido do disco quando sofre modificação real (`os.path.getmtime`), tornando a abertura e o fechamento de apps instantâneos.

* 🖼️ **Identidade Visual Unificada (`assets/`):**
  * Suporte nativo à pasta `assets/` com conversão automática de `icone.png` para `icone.ico` multi-resolução ($16 \times 16$ até $256 \times 256$), aplicando o símbolo personalizado no executável `Capri.exe`, na barra de tarefas, no Gerenciador de Tarefas (`AppUserModelID`), nas janelas e na bandeja do sistema.

---

## 📂 Estrutura Modular do Projeto

```text
Capricorn/
├── assets/                     # Ícone oficial da Capri (icone.png / icone.ico)
├── cache/                      # Áudios de resposta rápida gerados (ignorado pelo Git)
├── src/                        # Código-fonte modularizado da Capri (9 módulos)
│   ├── capri_core.py           # Ponto de entrada principal (inicializa threads e loops)
│   ├── hud.py                  # HUD principal, Bandeja, Filtro de Apps e Menu Cyberpunk 2077
│   ├── dicionario_comandos.py  # Dicionário massivo de intenções, corretor fonético e gatilhos
│   ├── voz.py                  # Escuta com VAD, Sessão HTTP persistente, Fish Audio TTS e Cache
│   ├── cerebro_ia.py           # Roteador de comandos, Cadastro de .exe por voz e Gemini API
│   ├── spotify_control.py      # Busca, Play automático e Volume exclusivo do Spotify Desktop
│   ├── sistema_pc.py           # Energia (Bloquear, Suspender, Desligar), Tema e Relógio
│   ├── abrir_apps.py           # Abertura rápida de programas com cache em memória
│   └── fechar_apps.py          # Encerramento forçado de processos (taskkill)
├── .gitignore                  # Proteção de chaves de API, cache e arquivos temporários
├── capri_config.json           # Chaves de API e lista de aplicativos/apelidos (gerado localmente)
└── README.md                   # Documentação oficial do projeto
```

---

## 🛠️ Funcionalidades Principais

### 1. 🎵 Controle Total do Spotify Desktop
* **Busca e Reprodução Direta:** Peça *"Capri, coloque uma música"* ou *"Cap, toca Numb"*. Ela aciona o aplicativo nativo do Spotify (`spotify:search:`), seleciona o melhor resultado e inicia a faixa sem abrir abas de navegador.
* **Volume Independente:** Peça *"Volume em 30%"*, *"Abaixar volume"* ou *"Volume no máximo"*. A Capri ajusta apenas o volume interno do processo `spotify.exe` e devolve o foco para a janela ou jogo que você estava usando.
* **Controle de Faixas:** Comandos instantâneos para pausar, retomar, pular para a próxima música ou voltar à faixa anterior.

### 2. 🎮 Cadastro Manual de Jogos e Programas (`.exe`) + Filtro Limpo
* **Via Menu Cyberpunk:** Abra as configurações (`⚙`) e clique no botão chanfrado **`+ ADICIONAR .EXE`**, escolha o arquivo `.exe` no Windows Explorer e defina o gatilho de voz (ex: `CS2`, `Valorant`, `Blender`).
* **Via Comando de Voz:** Diga *"Capri, adicionar executável"*. Ela abrirá o seletor de arquivos do Windows e perguntará em voz alta: **"Como você quer chamar esse executável?"**.
* **Catálogo Limpo:** Apenas aplicativos reais instalados no PC e utilitários essenciais do Windows aparecem na lista, organizados com switches `ON` (ciano) e `OFF` (coral).

### 3. 💻 Controle do Sistema Windows (Execução Instantânea)
* **Energia e Segurança:** Bloquear estação de trabalho (`LockWorkStation`), suspender o computador (`powrprof.dll`), desligar/reiniciar com timer de segurança de 10 segundos e comando para cancelar desligamento.
* **Personalização:** Alternância instantânea entre **Modo Escuro** e **Modo Claro** do Windows via Registro.
* **Execução em Segundo Plano:** Minimiza para a Bandeja do Sistema (*System Tray*) com ícone personalizado e opção de iniciar automaticamente junto com o Windows.

### 4. 🧠 Cérebro Gemini + Pesquisa Google em Tempo Real
* Integrada ao modelo `gemini-2.5-flash` com a ferramenta `GoogleSearch` ativada para responder perguntas sobre fatos atuais, clima, cotações, notícias e curiosidades com respostas curtas, diretas e sem marcações poluídas.

---

## 🎙️ Guia Rápido de Comandos de Voz

| Categoria | Exemplos de Comandos | Ação Executada |
| :--- | :--- | :--- |
| **Chamada (Wake Word)** | *"Capri"* / *"Cap"* / *"Oi Capri"* | Ativa a escuta com resposta rápida em cache |
| **Spotify (Música)** | *"Coloque uma música"* / *"Trocar a música"* | Pergunta qual música você quer e dá Play no Spotify |
| **Spotify (Direto)** | *"Coloque a música Numb"* / *"Toca Linkin Park"* | Busca e toca a faixa imediatamente no Spotify |
| **Volume Spotify** | *"Volume em 30%"* / *"Abaixar volume"* / *"Som no máximo"* | Ajusta o volume interno exclusivo do app Spotify |
| **Mídia** | *"Pausar música"* / *"Continuar música"* / *"Próxima música"* | Controla a reprodução atual |
| **Cadastrar `.exe`** | *"Adicionar executável"* / *"Cadastrar jogo"* | Abre o seletor de `.exe` e pergunta o apelido por voz |
| **Abrir / Fechar** | *"Abrir CS2"* / *"Abrir VS Code"* / *"Fechar Discord"* | Inicia ou encerra o aplicativo autorizado |
| **Energia / Tela** | *"Bloquear o PC"* / *"Suspender o computador"* | Tranca a tela do Windows ou suspende a máquina |
| **Desligamento** | *"Desligar o computador"* / *"Cancelar desligamento"* | Agenda desligamento em 10s ou aborta a contagem |
| **Sistema** | *"Modo escuro"* / *"Modo claro"* / *"Que horas são?"* | Altera o tema do Windows ou informa o horário atual |
| **Interface** | *"Abrir configurações"* / *"Fique quieta"* | Abre o painel Cyberpunk da Capri ou silencia o microfone |

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

### 4. Compilando o executável (`Capri.exe`) com Ícone Personalizado
Coloque a imagem do seu ícone dentro da pasta **`assets/`** e execute os comandos abaixo no PowerShell para converter o ícone e gerar o **`Capri.exe`** na raiz do projeto:

```powershell
taskkill /F /IM "Capri.exe" /T 2>$null

python -c "import os, glob; from PIL import Image; arqs = [f for f in glob.glob('assets/*.*') if not f.lower().endswith('.ico')] or glob.glob('assets/*.ico'); img = Image.open(arqs[0]).convert('RGBA').resize((256, 256), Image.Resampling.LANCZOS); img.save('assets/icone.ico', format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"

$caminhoIcone = Join-Path $PWD "assets\icone.ico"
python -m PyInstaller --noconsole --onefile --clean --paths src --icon="$caminhoIcone" --add-data "assets;assets" --distpath . --name "Capri" src/capri_core.py
Remove-Item -Recurse -Force build, Capri.spec -ErrorAction SilentlyContinue
```

---

## 🔑 Configuração Inicial

Na primeira execução, clique no botão **`⚙`** no HUD (ou diga *"Capri, abrir configurações"*):

1. Acesse a aba **`APIS & VOZ`** e insira sua **Gemini API Key** (obrigatória para perguntas gerais).
2. *(Opcional)* Insira sua **Fish Audio API Key** e **Fish Audio Voice ID** para utilizar voz clonada personalizada (caso deixe em branco, a Capri utilizará automaticamente a voz neural nativa em Português).
3. Na aba **`APLICATIVOS`**, ative os switches **`ON`** nos aplicativos que a Capri tem permissão para abrir/fechar ou clique em **`+ ADICIONAR .EXE`** à esquerda para registrar seus jogos e programas favoritos.
4. Clique em **`SALVAR E APLICAR`**.