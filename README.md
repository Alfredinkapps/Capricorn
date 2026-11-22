# ⚡ CAPRI — Assistente Virtual Cyberpunk (`v0.2.0`)

![Versão](https://img.shields.io/badge/versão-0.1.5%20pre--alpha-F06A82?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white)
![Architecture](https://img.shields.io/badge/Architecture-Hybrid%20Local%20%2B%20Cloud-9B72FF)

Assistente virtual de desktop para Windows com estética **Cyberpunk**, arquitetura híbrida (reconhecimento de voz offline + APIs de IA em nuvem), modo desktop pet interativo, visão computacional, memória persistente em SQLite e agente autônomo para jogos.

---

## Download

Não é necessário instalar Python para usar a Capri no Windows:

👉 **[Baixar a última versão pronta (`Capri.exe`)](https://github.com/Alfredinkapps/Capricorn/releases/latest)**

1. Na seção **Assets** da última release, baixe o arquivo **`Capricorn-vX.X.X-Windows.zip`**.
2. Extraia todo o conteúdo para uma pasta (mantenha `Capri.exe`, `assets/` e `bin/` juntos).
3. Execute **`Capri.exe`**.
4. Clique em **`⚙ CONFIG`** no HUD e adicione sua chave de API (**Gemini**, **Claude** ou **DeepSeek**). A pasta `data/` será criada automaticamente no primeiro uso.

---

## Principais Recursos

* **HUD Cyberpunk & Modo Livre ("Fuga da Caixa"):**
  * Interface compacta com sprites dinâmicos, sincronização labial e balão de fala acoplado.
  * No **Modo Livre** (`🐾`), a Capri sai do HUD e circula pela barra de tarefas com física de gravidade, arraste pelo mouse, carinho (*headpat*), mini-chat flutuante e encaixe automático na borda superior das suas janelas ativas (permanecendo sempre no topo via Win32 sem roubar o foco).
* **Memória Persistente (SQLite) & Acompanhamento Proativo:**
  * Armazena o histórico de conversas em uma janela móvel de **20 dias** em `data/capri_memoria.db`.
  * Identifica automaticamente eventos, provas, testes e prazos citados durante a conversa e puxa assunto proativamente dias depois para saber como foi.
* **Agente Autônomo para *Reigns*:**
  * Joga *Reigns* de forma autônoma lendo a tela a cada 3 segundos, inclinando a carta para espiar ambas as opções e os indicadores de impacto dos 4 pilares (Igreja, Povo, Exército e Tesouro).
  * Possui travas de emergência instantâneas (**segurar `ESC`** ou mover o mouse para o canto superior esquerdo).
  * Aprende entre runs: após cada morte, gera um *post-mortem* automático das últimas jogadas e salva lições táticas permanentes no SQLite para bater os próprios recordes.
* **Visão Computacional & Co-piloto:**
  * Analisa a tela sob demanda para depurar código, responder dúvidas visuais ou comentar o que está aberto.
  * Modo Observador para acompanhar jogos em tempo real.
* **Roteamento Multi-IA:**
  * Suporte nativo a **Google Gemini** (priorizando `gemini-3.5-flash-lite` para respostas rápidas e `gemini-3.5-flash` para código, visão e *Reigns*), **Claude** e **DeepSeek**.
* **Voz Híbrida & Controle do Windows:**
  * Reconhecimento de voz offline com **Vosk** (baixo consumo de RAM) + fallback online e síntese de voz.
  * Scanner automático de aplicativos instalados no Windows, controle de volume, mídia e Spotify.
* **Logs em Arquivo:**
  * Registro estruturado e rotativo em `data/capri.log`, facilitando diagnósticos mesmo ao executar o `Capri.exe` sem console.

---

## Comandos Rápidos (Voz ou Barra de Texto)

| Categoria | Exemplos de Comando |
| :--- | :--- |
| **Modo Livre** | `"sair da caixa"`, `"modo livre"`, `"voltar para a caixa"` |
| **Agente *Reigns*** | `"jogue reigns"`, `"parar reigns"`, `"esquecer reigns"` *(ou segure `ESC`)* |
| **Visão de Tela** | `"olha minha tela"`, `"corrige esse código"`, `"/tela o que há aqui?"` |
| **Co-piloto** | `"ativar modo observador"`, `"desativar modo observador"` |
| **Memória** | `"o que você lembra?"`, `"minhas memórias"` |
| **Apps e Mídia** | `"abrir vscode"`, `"fechar chrome"`, `"toca [música]"`, `"pausar música"`, `"aumentar volume"` |

---

## Arquitetura do Projeto

```text
Capricorn/
├── assets/                   # Sprites, efeitos e recursos visuais
├── bin/                      # Binários externos e modelo offline do Vosk
├── data/                     # (Ignorada no Git) capri_config.json, capri_memoria.db, capri.log, cache/
├── src/
│   ├── main.py               # Ponto de entrada principal
│   ├── core/
│   │   ├── config.py         # Caminhos, leitura/escrita de JSON e inicialização no Windows
│   │   ├── engine.py         # Orquestração de threads, locks e loops principais
│   │   └── logger.py         # Logs rotativos em arquivo e captura global de exceções
│   ├── ui/
│   │   ├── hud.py            # Interface principal, balão de fala e configurações
│   │   └── modo_livre.py     # Física do desktop pet e ancoragem em janelas via Win32
│   ├── ai/
│   │   ├── cerebro.py        # Roteamento Multi-IA e interpretador de comandos
│   │   ├── visao.py          # Captura de tela sob demanda e Modo Observador
│   │   └── memoria.py        # Banco SQLite (20 dias, eventos proativos e lições do Reigns)
│   ├── agents/
│   │   └── reigns.py         # Agente visual autônomo de Reigns
│   ├── audio/
│   │   ├── voz.py            # STT (Vosk / Google) e TTS
│   │   └── comandos.py       # Normalização de frases e wake-words
│   └── system/
│       ├── apps.py           # Scanner e gerenciamento de aplicativos do Windows
│       └── spotify.py        # Controle de reprodução do Spotify
├── capri_config.example.json # Modelo de configuração sem chaves de API
├── Capri.spec                # Receita reproduzível de build do PyInstaller
├── pyrightconfig.json        # Configuração de paths do Pylance/Pyright
├── requirements.txt          # Dependências Python do projeto
└── README.md
```

---

## Rodando pelo Código-Fonte (Desenvolvedores)

### Pré-requisitos
* **Windows 10/11**
* **Python 3.10+**
* Modelo offline do Vosk posicionado em `bin/` (caso use STT offline)

### Instalação e Execução

```powershell
# 1. Clone o repositório
git clone [https://github.com/Alfredinkapps/Capricorn.git](https://github.com/Alfredinkapps/Capricorn.git)
cd Capricorn

# 2. Crie e ative o ambiente virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Inicie a Capri
python src/main.py
```

Na primeira execução, configure suas chaves em **`⚙ CONFIG`** (ou copie `capri_config.example.json` para `data/capri_config.json` e preencha manualmente).

---

## Compilando o Executável (`Capri.exe`)

Com a `.venv` ativa e o `pyinstaller` instalado:

```powershell
pyinstaller --clean Capri.spec
```

O executável será gerado em `dist/Capri.exe`. Para distribuir ou rodar de forma portátil, mantenha `Capri.exe`, `assets/` e `bin/` no mesmo diretório — **não** inclua a pasta `data/` ao empacotar versões públicas.

---

## Privacidade e Dados Locais

Todas as credenciais (`data/capri_config.json`), memórias conversacionais (`data/capri_memoria.db`), caches de áudio (`data/cache/`) e registros de execução (`data/capri.log`) ficam isolados localmente na pasta `data/`, que permanece bloqueada no `.gitignore`.