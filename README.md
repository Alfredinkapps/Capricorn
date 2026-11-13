# ⚡ CAPRI // Project Capricorn OS

Assistente virtual tática com estética Cyberpunk para Windows, equipada com interface flutuante (HUD), central de configurações com scanner automático de programas, ativação em duas etapas com detecção inteligente de voz (VAD), integração de pesquisa em tempo real via Google Gemini, reprodução inteligente de músicas no YouTube, controle global de mídia/energia e síntese de voz clonada com cache local.

---

## 📁 1. Estrutura de Arquivos do Projeto

Mantenha os arquivos principais na mesma pasta do projeto:

* **`capri_core.py`**: Núcleo do sistema. Contém o HUD Cyberpunk, a Central de Configurações (`⚙`), captura inteligente de microfone, integração com voz clonada, controle de energia/mídia, player do YouTube e o cérebro conectado ao Gemini com Pesquisa Google.
* **`abrir_apps.py`**: Módulo dinâmico que inicia apenas os programas autorizados com o botão verde (`✔`) nas configurações.
* **`fechar_apps.py`**: Módulo dinâmico que encerra processos em segundo plano via `taskkill` respeitando as permissões da interface.
* **`capri_config.json`** *(Gerado automaticamente)*: Armazena suas chaves de API e o catálogo de aplicativos escaneados do computador.
* **`cache/`** *(Pasta gerada automaticamente)*: Guarda os arquivos `.mp3` das respostas rápidas e da voz sintetizada para resposta instantânea (`0.1s`) e economia de requisição de API.
* **`.gitignore`**: Protege suas chaves de API (`capri_config.json`) e áudios locais (`cache/`) para não serem enviados ao GitHub.

---

## 🚀 2. Passo a Passo para Instalar em Outro Computador

### Passo 2.1: Instalar o Python
1. Baixe e instale o **Python** (versão 3.10 até 3.14) em [python.org](https://www.python.org/).
2. **Importante:** Na primeira tela do instalador, marque a opção **"Add Python to PATH"** antes de clicar em *Install Now*.

### Passo 2.2: Instalar as Bibliotecas no Terminal
Abra o terminal (**PowerShell** ou **CMD**) dentro da pasta do projeto e execute o comando abaixo para instalar todas as dependências:

```powershell
pip install requests numpy sounddevice SpeechRecognition edge-tts pygame-ce pystray Pillow google-genai
```

### Passo 2.3: Iniciar e Configurar pela Interface Gráfica (Primeiro Uso)
Não é necessário editar chaves dentro do código. Basta iniciar a assistente pelo terminal:

```powershell
python capri_core.py
```

1. **Abertura Automática no 1º Uso:** Na primeira execução, a **Central de Configurações (`⚙`)** se abrirá automaticamente e fará um scan completo dos aplicativos instalados no seu Windows.
2. **Chaves de API:** Preencha nos campos da janela:
   * **Gemini API Key:** Gere gratuitamente no [Google AI Studio](https://aistudio.google.com/).
   * **Fish Audio API Key:** Gere na aba API do site [fish.audio](https://fish.audio/).
   * **Fish Audio Voice ID:** Copie o ID do modelo de voz clonada criado no Fish Audio.
3. **Permissões de Aplicativos (`✔` / `✖`):** Use a barra de busca para filtrar seus programas e clique no interruptor ao lado de cada aplicativo para ativar (**Verde `✔`**) ou bloquear (**Vermelho `✖`**) o controle por voz. O salvamento é automático.
4. **Inicialização com o Windows:** Após a primeira execução, a Capri se registra automaticamente no Windows via `pythonw.exe` para iniciar junto com o computador sem abrir a tela preta do terminal.

### Passo 2.4: Liberar o Autoplay do YouTube no Firefox
Para que as músicas pedidas à Capri comecem a tocar sozinhas:
1. Abra um vídeo do YouTube no **Firefox** e clique no ícone de **permissões da página** (ao lado esquerdo de `youtube.com` na barra de endereços).
2. Em **Reproduzir automaticamente**, mude de *Bloquear áudio* para **Permitir áudio e vídeo**.

---

## 🎙️ 3. Funcionalidades e Comandos de Voz

### 🟢 Ativação em 2 Etapas e Medidor de Voz Discreto
* **Modo de Espera Discreto:** Enquanto você não chama a Capri, o medidor **"SINAL DE VOZ"** fica desligado (`EM ESPERA`), garantindo privacidade visual.
* **Chamada Natural:** Diga apenas **"Capri"**. Ela responderá imediatamente (*"Oie"*, *"Fala, bobão"*, *"Diga lá"*) usando o cache local, ativará a barra verde de sinal de voz (`OUVINDO VOCÊ...`) e aguardará o seu comando ou pergunta.

### 🎵 YouTube Inteligente (Mesma Aba) e Controle de Mídia
* **Tocar Música:** Diga *"Coloque uma música"* (ela perguntará qual você quer ouvir) ou diga direto *"Coloque a música [nome]"*.
* **Troca na Mesma Guia:** Se o YouTube já estiver aberto no Firefox, ao pedir *"Troque a música"* ou *"Coloque outra música"*, a Capri localiza a janela do navegador e substitui o vídeo na **mesma aba**, sem acumular guias abertas.
* **Controle Global de Reprodução:** Diga *"Pausar música"*, *"Continuar música"*, *"Próxima música"* ou *"Música anterior"* para controlar o áudio mesmo com o navegador minimizado.

### 🌐 Pesquisa Google em Tempo Real (Gemini API)
* Faça perguntas sobre fatos atuais, notícias, clima ou curiosidades (ex: *"Quem é o atual presidente do Brasil?"*). A Capri consulta a ferramenta `GoogleSearch` integrada à Gemini API e responde de forma direta com memória de contexto da conversa.

### 🖥️ Controle de Aplicativos, Sistema e Energia
* **Abrir e Fechar Programas:** *"Abrir calculadora"*, *"Abrir Visual Studio Code"*, *"Fechar Discord"*, *"Abrir configurações"*.
* **Tema do Windows:** *"Mudar para o tema escuro"* ou *"Mudar para o tema claro"*.
* **Energia e Segurança:**
  * *"Bloquear a tela"* / *"Trancar o PC"*: Bloqueia a sessão do Windows em 2 segundos.
  * *"Desligar o computador"* / *"Reiniciar o computador"*: Inicia a contagem de 10 segundos para encerramento seguro.
  * *"Cancelar desligamento"*: Aborta imediatamente a contagem regressiva de desligamento.
  * *"Suspender o computador"*: Coloca o PC em modo de suspensão.
  * *"Mutar"* / *"Desligar sistema"*: Silencia o microfone da Capri ou fecha a assistente.

---

## 🔒 4. Segurança e Proteção no GitHub (`.gitignore`)

Para evitar que suas chaves pessoais no `capri_config.json` e os áudios gerados na pasta `cache/` sejam enviados para o seu repositório do GitHub, mantenha o arquivo **`.gitignore`** na raiz do projeto com o seguinte conteúdo:

```text
capri_config.json
cache/
capri_voz.mp3
.venv/
__pycache__/
```

---

## 🧩 5. O que cada `import` faz (Resumo Técnico)

### Bibliotecas Nativas do Python (Já vêm com o Python)
* **`os`, `sys` e `json`**: Gerenciam diretórios (`cache/`), variáveis de ambiente, leitura/gravação do `capri_config.json` e o caminho do `pythonw.exe`.
* **`time` e `datetime`**: Controlam temporizadores e consultam o relógio e calendário reais do sistema.
* **`ctypes` e `winreg`**: Acessam a API nativa e o Registro do Windows para escanear programas instalados, trocar o tema Claro/Escuro, bloquear a tela (`LockWorkStation`), enviar teclas multimídia/atalhos e focar a aba ativa do Firefox.
* **`subprocess` e `urllib.parse.quote_plus`**: Executam processos do sistema, enviam URLs para a área de transferência e formatam pesquisas para o YouTube.
* **`threading` e `asyncio`**: Mantêm o HUD, o ícone da bandeja, o scanner e a IA rodando em paralelo sem congelar a tela.
* **`re`, `random` e `collections.deque`**: Filtram textos, sorteiam saudações e mantêm um buffer circular de pré-fala (`0.4s`) para nunca cortar o início da voz do usuário.
* **`tkinter` e `tkinter.messagebox`**: Constroem o HUD flutuante Cyberpunk, a Central de Configurações com rolagem e os botões deslizantes customizados (`BotaoSwitchApp`).

### Bibliotecas Externas (Instaladas via `pip`)
* **`google.genai` (`genai`, `types`)**: Conecta o sistema aos modelos Gemini Flash com suporte à ferramenta de busca `GoogleSearch` em tempo real.
* **`requests`**: Conecta à API do Fish Audio (`s2.1-pro-free`), localiza o ID de vídeos no YouTube e envia mensagens via Webhook ao Discord.
* **`sounddevice` e `numpy`**: Capturam o áudio em blocos de `100ms`, detectam início e fim de frase automaticamente (VAD) e normalizam o ganho do volume do microfone.
* **`speech_recognition`**: Transcreve o áudio normalizado para texto em português (`pt-BR`).
* **`edge_tts`**: Sintetizador neural gratuito da Microsoft usado como fallback caso a API externa oscile.
* **`pygame` (`pygame-ce`)**: Reproduz os arquivos `.mp3` da pasta `cache/` em segundo plano sem abrir janelas externas.
* **`pystray` e `PIL` (`Image`, `ImageDraw`)**: Desenham o ícone neon e gerenciam o menu rápido na bandeja do sistema (ao lado do relógio do Windows).