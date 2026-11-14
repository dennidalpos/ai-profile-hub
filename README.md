# AI Profile Hub

Launcher desktop per **Windows, macOS e Linux**. Gestisce profili con account diversi per Claude Code, Codex e Antigravity / Gemini. Dalla stessa finestra puoi aprire un sito con una sessione browser dedicata, avviare un client installato in un terminale o aprire un’istanza dell’app desktop sul sistema host.

## Avvio e build

| Sistema | Avvio dalla root | Build dalla root |
| --- | --- | --- |
| Windows | Doppio clic su `run.cmd` oppure `.\run.cmd` da PowerShell | `.\build.cmd` |
| macOS e Linux | `./run.sh` oppure `sh run.sh` | `./build.sh` oppure `sh build.sh` |

Serve Python 3.11+ con Tkinter. Su Windows e macOS puoi usare l’installer di [python.org](https://www.python.org/downloads/). Su Debian e Ubuntu installa `python3-tk` per la GUI. Per aprire profili CLI su Linux serve anche un terminale grafico, per esempio GNOME Terminal, Konsole o xterm. Su macOS l’apertura di Terminal può richiedere il consenso di Automazione al primo uso.

La build controlla la sintassi e genera `dist/ai-profile-hub.pyz`. Aprilo con `py -3 dist\ai-profile-hub.pyz` su Windows o `python3 dist/ai-profile-hub.pyz` su macOS e Linux. È un pacchetto portatile Python. Il runtime Python, Tkinter e i client dei provider vanno installati sul PC.

## Client disponibili

| Prodotto | Web | Client installati localmente |
| --- | --- | --- |
| Claude Code | Claude Code sul web, Claude sul web | Claude Code CLI (`claude`), Claude Desktop † |
| Codex | Codex sul web, ChatGPT sul web | Codex CLI (`codex`), Codex / ChatGPT Desktop † |
| Antigravity / Gemini | Gemini sul web | Antigravity CLI (`agy`) †, Gemini CLI (`gemini`), Antigravity IDE †, Antigravity App † |

† Integrazione sperimentale. Il launcher supporta i tre sistemi, mentre la disponibilità di ogni client dipende dalla distribuzione del produttore. Le app desktop possono ignorare il percorso del profilo, riutilizzare una finestra esistente o demandare il login al gestore di link del sistema. Controlla l’identità nella finestra di ogni istanza. Per Codex, la configurazione documentata di `CODEX_HOME` riguarda CLI, estensione IDE e app-server. L’avvio desktop multi-profilo è una procedura della community. Per Antigravity IDE, il flag è riportato nel forum Google. Per Antigravity App e `agy`, le directory dedicate sono un tentativo di isolamento da verificare sul client e sulla versione installata. [Codex desktop e piattaforme](https://learn.chatgpt.com/docs/app) · [Avvio multi-profilo Codex su Windows](https://github.com/phoem/Codex-Profile-Launcher) · [Download Antigravity](https://antigravity.google/download) · [Forum Antigravity IDE](https://discuss.ai.google.dev/t/how-do-user-data-dir-and-profile-work/137054)

## Uso

1. Premi **Nuovo profilo**, scegli il prodotto e il client, poi assegna un nome come `Personale` o `Lavoro`. Per i client locali puoi indicare l’eseguibile se il rilevamento automatico non lo trova e scegliere una cartella di lavoro.
2. Per il web, apri il profilo ed esegui l’accesso nella finestra Chrome o Chromium. Puoi selezionare l’eseguibile del browser da **Impostazioni**. Per il terminale usa **Accedi** oppure accedi direttamente dal client. Codex apre il flusso con codice dispositivo, che va abilitato nelle impostazioni di sicurezza del relativo account o workspace. [Autenticazione Codex](https://learn.chatgpt.com/docs/auth)
3. Per le app desktop usa **Accedi** con le altre istanze dello stesso client chiuse. Dopo il login controlla l’email. Per avviare più profili già configurati, selezionali con `Ctrl` o `⌘` e premi **Apri selezione**. Il doppio clic apre una singola riga.
4. **Modifica** permette di cambiare nome e percorsi. **Elimina** rimuove i dati locali del profilo dopo conferma. Chiudi le finestre o il terminale associato prima di eliminare il profilo. Il comando di eliminazione agisce sui dati locali e lascia l’account online disponibile.

### Profili esistenti

- **AI Profile Switch** usa la stessa directory locale. All’avvio AI Profile Hub aggiorna lo schema SQLite e riutilizza gli identificativi e le cartelle esistenti. I profili web Claude e ChatGPT continuano ad aprire i siti originali. Per le nuove destinazioni Claude Code e Codex, crea un profilo dedicato. Per tornare alla versione precedente, conserva una copia di `profiles.sqlite3` prima di aprire AI Profile Hub.
- **Claude Desktop Duo per Windows**. Se esiste `%LOCALAPPDATA%\ClaudeDesktopDuo\SecondProfile`, seleziona **Impostazioni → Collega il secondo profilo di Claude Desktop Duo**. L’app riutilizza quella cartella. Eliminare la voce da AI Profile Hub lascia i dati di Duo nella cartella originale.

### Come vengono separati i profili

- Il browser riceve `--user-data-dir` per ogni profilo. [Documentazione Chromium](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/user_data_dir.md)
- Claude Code riceve `CLAUDE_CONFIG_DIR`. Anthropic documenta questa modalità per accedere con account diversi. [Autenticazione Claude Code](https://code.claude.com/docs/en/authentication)
- Codex riceve `CODEX_HOME` e `CODEX_SQLITE_HOME`. Nella configurazione del profilo la modalità `file` fa salvare le credenziali in `auth.json`. Le regole di autenticazione gestite dall’organizzazione hanno precedenza. [Configurazione Codex](https://learn.chatgpt.com/docs/config-file/config-advanced) · [Archiviazione delle credenziali](https://learn.chatgpt.com/docs/auth)
- Gemini CLI riceve `GEMINI_CLI_HOME` e usa la modalità di archiviazione locale del client. Per `agy` e Antigravity, il launcher imposta una home dedicata per il processo e le directory di sistema rilevanti. Google documenta `~/.gemini/antigravity-cli/settings.json` e la migrazione da Gemini CLI. La separazione completa dell’autenticazione di `agy` va verificata. [Gemini CLI](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/enterprise.md) · [Impostazioni di Antigravity CLI](https://antigravity.google/docs/cli/using/) · [Migrazione Google](https://antigravity.google/docs/cli/gcli-migration)
- L’avvio di Claude Desktop su Windows passa una cartella dedicata all’app originale. Le build MSIX `2.42304.x` possono ignorarla e vanno aggiornate. Il primo login con una sola istanza aperta aiuta a far tornare il browser alla finestra prevista. [Segnalazione MSIX](https://github.com/anthropics/claude-code/issues/103068)

Le cartelle dei profili sono sotto `%LOCALAPPDATA%\AIProfileSwitch` su Windows, `~/Library/Application Support/AI Profile Switch` su macOS e `${XDG_DATA_HOME:-$HOME/.local/share}/ai-profile-switch` su Linux. Il launcher non legge, esporta o copia i file di autenticazione. I client operano con lo stesso utente del sistema e possono accedere agli stessi progetti e ai servizi del sistema operativo.

## Test e GitHub

```sh
python3 -m unittest discover -s tests -v
```

Su Windows usa `py -3`. Il workflow GitHub Actions esegue test e build su Windows, macOS e Linux. I test coprono la migrazione, l’eliminazione e i comandi generati. Per una verifica completa con il client installato, crea due profili, accedi con account diversi, chiudi e riapri entrambi, poi verifica le identità. Il comportamento dei login desktop e di `agy` richiede questa prova su ciascun sistema.

Per pubblicare, crea un repository GitHub vuoto e lancia dalla root:

```sh
git init -b main
git add .
git commit -m "Initial AI Profile Hub release"
git remote add origin https://github.com/TUO-USERNAME/ai-profile-hub.git
git push -u origin main
```

Progetto indipendente. Licenza [MIT](LICENSE).
