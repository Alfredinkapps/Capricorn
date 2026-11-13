# ⚡ CAPRI // Project Capricorn OS

Assistente virtual tática com estética Cyberpunk para Windows, equipada com interface flutuante (HUD), medidor de voz em tempo real (VU Meter), ícone na bandeja do sistema (System Tray), controle local instantâneo de aplicativos (Fast-Track) e síntese de voz clonada.

---

## 📁 1. Estrutura de Arquivos do Projeto

Para que a assistente funcione em qualquer computador, mantenha sempre estes **3 arquivos** na mesma pasta:

* **`capri_corn.py`** *(ou `capri_core.py`)*: Núcleo do sistema. Contém a interface gráfica Cyberpunk, captura de microfone, integração com voz clonada, inicialização automática com o Windows e o cérebro conectado ao Gemini.
* **`abrir_apps.py`**: Módulo dedicado a iniciar programas e atalhos do sistema operacional.
* **`fechar_apps.py`**: Módulo dedicado a encerrar processos abertos em segundo plano via `taskkill`.

---

## 🚀 2. Passo a Passo para Instalar em Outro Computador

### Passo 2.1: Instalar o Python
1. Baixe e instale o **Python** (compatível da versão 3.10 até a 3.14) em [python.org](https://www.python.org/).
2. **Importante:** Na primeira tela do instalador do Python, marque a opção **"Add Python to PATH"** antes de clicar em *Install Now*.

### Passo 2.2: Instalar as Bibliotecas no Terminal
Abra o terminal (**PowerShell** ou **CMD**) dentro da pasta onde estão os arquivos do projeto e execute o comando abaixo para instalar todas as dependências de uma só vez:

```powershell
pip install requests numpy sounddevice SpeechRecognition edge-tts pygame-ce pystray Pillow google-genai
```

*(Observação: Caso o VS Code crie um ambiente virtual `.venv`, basta rodar esse mesmo comando dentro do terminal com o `(.venv)` ativado).*

### Passo 2.3: Configurar as Chaves de API e Voz Clonada
Abra o arquivo principal (`capri_corn.py`) no editor de código e preencha as 3 credenciais no topo do script:

1. **`GEMINI_API_KEY`**:
   * Crie uma chave gratuita no [Google AI Studio](https://aistudio.google.com/).
   * Cole em: `os.environ["GEMINI_API_KEY"] = "SUA_CHAVE_GEMINI_AQUI"`
2. **`FISH_API_KEY`** (Voz Clonada):
   * Crie uma conta em [fish.audio](https://fish.audio/), acesse a aba **API** e gere uma chave.
   * Cole em: `FISH_API_KEY = "SUA_FISH_API_KEY_AQUI"`
3. **`FISH_VOICE_ID`** (ID do Timbre da Voz):
   * No Fish Audio, vá em **Create Voice**, envie um áudio limpo (15 a 45 segundos em MP3/WAV) da voz desejada e copie o código final da URL (ou clique em *Copy Model ID*).
   * Cole em: `FISH_VOICE_ID = "SEU_FISH_VOICE_ID_AQUI"`

### Passo 2.4: Iniciar a Assistente
No terminal, execute o arquivo principal:

```powershell
python capri_corn.py
```

* Ao rodar pela primeira vez, a Capri se registra automaticamente no Registro do Windows (`HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`) usando o `pythonw.exe`.
* A partir do próximo reinício do computador, ela ligará sozinha junto com o Windows, mostrando apenas o **HUD Cyberpunk** e o **ícone ao lado do relógio**, sem abrir a janela preta do terminal.

---

## 🎙️ 3. Comandos Rápidos e Personalização

* **Ativação por voz:** Diga sempre **"Capri"** seguido do comando (ex: *"Capri, abra o navegador"*, *"Capri, feche a calculadora"*, *"Capri, mude para o tema escuro"*, *"Capri, que horas são?"*, *"Capri, mutar"*).
* **Adicionar novos programas:** Basta inserir o nome e o executável nos dicionários `MAPA_ABRIR` (em `abrir_apps.py`) e `MAPA_FECHAR` (em `fechar_apps.py`).
* **Alterar as falas e personalidade:**
  * As respostas imediatas de abertura/fechamento ficam nos `return` de `abrir_apps.py`, `fechar_apps.py` e `tentar_execucao_instantanea()`.
  * O humor e estilo de conversa da IA ficam no texto de `instrucao_sistema` dentro da função `loop_cerebro_capri()`.

---

## 🧩 4. O que cada `import` faz (Resumo Técnico)

### Bibliotecas Nativas do Python (Já vêm com o Python)
* **`os` e `sys`**: Gerenciam pastas locais, variáveis de ambiente e localizam o executável `pythonw.exe` para iniciar sem tela preta.
* **`time` e `datetime`**: Controlam pausas de processamento e consultam o relógio/calendário real do Windows.
* **`ctypes` e `winreg`**: Acessam o Registro e a API nativa do Windows para trocar o tema Claro/Escuro sem travar e configurar o boot automático.
* **`subprocess`**: Executa comandos diretos do Windows para abrir programas ou forçar o fechamento de aplicativos via `taskkill`.
* **`threading` e `asyncio`**: Fazem a janela gráfica (HUD), o ícone da bandeja, a escuta de voz e a inteligência artificial rodarem em paralelo sem congelar a tela.
* **`re`**: Usa expressões regulares para inserir pausas de respiração nas vírgulas e pontos finais antes de sintetizar a voz.
* **`tkinter`**: Constrói a janela flutuante Cyberpunk, o botão de Mute, o orbe pulsante e a barra medidora de voz.

### Bibliotecas Externas (Instaladas pelo comando `pip`)
* **`google.genai` (`genai`, `types`)**: Conecta o script aos modelos Gemini Flash/Lite na nuvem com rotação automática contra filas (erro 503) e acionamento de ferramentas.
* **`requests`**: Envia chamadas HTTP para gerar a voz clonada na API do Fish Audio (`s2.1-pro-free`) e enviar mensagens via Webhook ao Discord.
* **`sounddevice` e `numpy`**: Capturam o som do microfone em blocos de 0,1s e calculam a intensidade da voz matematicamente para animar a barra de sinal do HUD em tempo real.
* **`speech_recognition`**: Converte o áudio gravado pelo microfone em texto em português (`pt-BR`).
* **`edge_tts`**: Sintetizador neural gratuito da Microsoft que funciona como voz de segurança (fallback) caso a internet ou a API externa oscilem.
* **`pygame` (`pygame-ce`)**: Carrega e toca os arquivos `.mp3` da voz da Capri em segundo plano sem abrir reprodutores externos do Windows.
* **`pystray` e `PIL` (`Image`, `ImageDraw`)**: Desenham o ícone neon da Capri e criam o menu de clique direito na bandeja do sistema (perto do relógio do Windows).

### Módulos Locais do Projeto
* **`abrir_apps` e `fechar_apps`**: Importam as funções modulares criadas por você para manter o código principal limpo, rápido e fácil de dar manutenção.