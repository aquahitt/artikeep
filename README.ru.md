# artikeep

**Всё, что делают ваши AI-агенты, — не потеряется.**

[English](https://github.com/aquahitt/artikeep/blob/main/README.md) · Русский

[![test](https://github.com/aquahitt/artikeep/actions/workflows/test.yml/badge.svg)](https://github.com/aquahitt/artikeep/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/artikeep?color=2E5E4E)](https://pypi.org/project/artikeep/)
![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-2E5E4E)
![dependencies: none](https://img.shields.io/badge/dependencies-none-2E5E4E)
![macOS | Linux](https://img.shields.io/badge/platform-macOS%20%7C%20Linux-2E5E4E)
[![MIT](https://img.shields.io/badge/license-MIT-2E5E4E)](https://github.com/aquahitt/artikeep/blob/main/LICENSE)

Агенты публикуют страницы, холсты и документы туда, где вы ничего не решаете: ссылка на
артефакт на чужом сервере, чат, доступ к которому можно потерять, временная папка, которую
однажды почистят. artikeep сохраняет копию каждого такого результата на ваш диск в момент его
создания. Каждое изменение становится версией, галерея позволяет листать и сравнивать
версии, а MCP-сервер даёт любому агенту искать то, что у вас уже есть.

**В Claude Code это плагин: две команды, никакой настройки.**
[К быстрому старту](#claude-code-плагин-рекомендуется).

![Поиск по архиву, открытие карточки, сравнение первой и текущей версий](https://raw.githubusercontent.com/aquahitt/artikeep/main/docs/media/demo.gif)

- **Автоматически, где это возможно.** Hook-и Claude Code и Codex сохраняют копии без
  участия модели: ей ничего не нужно помнить.
- **Каждое изменение — версия.** Любые две версии можно сравнить рядом, с изменёнными
  строками текста.
- **Обычные файлы в git.** Архив — папка с HTML, Markdown и JSON. Она открывается и без
  artikeep и синхронизируется между машинами через приватный git-remote.
- **Агенты сами заглядывают в архив.** Прежде чем собирать отчёт заново, агент ищет его в
  архиве через MCP.
- **Без зависимостей.** Стандартная библиотека Python 3.9+. Для сохранения копий ничего
  ставить через `pip` не нужно.

## Быстрый старт

### Claude Code: плагин (рекомендуется)

Две команды прямо в Claude Code, заранее ничего ставить не нужно:

```
/plugin marketplace add aquahitt/artikeep
/plugin install artikeep@artikeep
```

Готово. Плагин приносит hook-и и MCP-сервер, обновляется через `/plugin` и требует только
`python3` 3.9+, который уже есть на большинстве Mac и Linux. Со следующей сессии каждая
страница, холст и документ из Claude Code попадает в `~/artikeep`, каждое изменение —
отдельной версией. Галерея — `~/artikeep/index.html`.

То же из терминала:
`claude plugin marketplace add aquahitt/artikeep && claude plugin install artikeep@artikeep`.

Два необязательных дополнения, по команде на каждое (`uvx` входит в
[uv](https://docs.astral.sh/uv/) и запускает artikeep без установки):

- **Резервная копия и синхронизация:** `uvx artikeep init ~/artikeep` делает архив
  git-репозиторием; добавьте `--remote git@github.com:you/my-artifacts.git` (**приватный**
  репозиторий), чтобы синхронизировать машины.
- **Транскрипты дольше:** пропишите `"cleanupPeriodDays": 3650` в `~/.claude/settings.json`,
  чтобы потерянный артефакт можно было восстановить из его сессии.

### Codex, Claude Desktop или всё сразу

```bash
uv tool install artikeep        # или: pipx install artikeep
artikeep init ~/artikeep        # папка архива (git-репозиторий)
artikeep install                # hook-и и MCP для найденных агентов
artikeep doctor                 # проверка
```

С этого момента всё, что делают Claude Code и Codex, попадает в `~/artikeep`. Галерея
открывается командой `artikeep open`, локальное приложение — `artikeep serve --open`.
Плагин уже стоит? Ограничьте установку остальным: `artikeep install --agents codex,claude-desktop`.

Нет менеджера пакетов? Клон работает как есть, без установки:
`git clone https://github.com/aquahitt/artikeep ~/artikeep-src`, затем
`python3 ~/artikeep-src/bin/artikeep init ~/artikeep` и дальше по списку.

## Что сохраняется

| Источник | Как | Что |
|---|---|---|
| Claude Code | hook-и, автоматически | страницы, опубликованные инструментом `Artifact` (со всеми файлами), холсты Claude Design, документы Claude Docs (экспорт по вкладкам), неопубликованные страницы из scratchpad сессии |
| Codex | hook-и, автоматически | документы, которые сессия пишет мимо git, — отчёты, страницы, таблицы во временных папках, неотслеживаемые и игнорируемые файлы, — и визуализации сессии |
| Чат Claude Desktop | MCP, по просьбе | попросите Claude сохранить сделанное; у чата нет hook-ов, так что это единственный живой путь (вкладка Code в Desktop — это Claude Code, она сохраняется автоматически) |
| ChatGPT | `artikeep import chatgpt <export.zip>` | документы canvas, каждая правка воспроизводится как версия |
| claude.ai | `artikeep import claude-ai <export.zip>` | артефакты из чатов, каждое обновление — версия; React-компоненты открываются как живые страницы, в том числе офлайн |
| Что угодно ещё | `artikeep add <файл или папка>` или MCP-инструмент `save_artifact` | то, на что укажете |

Файлы, которые уже отслеживает git, пропускаются: они и так в сохранности.

## Галерея

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/aquahitt/artikeep/main/docs/media/gallery-dark.png">
  <img alt="Галерея: элементы из Claude Code, Codex, Claude Desktop, ChatGPT и claude.ai с фильтрами по проекту, источнику и типу" src="https://raw.githubusercontent.com/aquahitt/artikeep/main/docs/media/gallery-light.png">
</picture>

`index.html` в корне архива — статическая страница, которая работает прямо с диска. Сетка
или список, фильтры (проект, источник, тип, как получена копия), группировка, полнотекстовый
поиск, панель элемента с историей версий, сравнение любых двух версий рядом с изменёнными
строками текста. Светлая и тёмная темы, английский и русский интерфейс, удобно и с телефона.

<table>
  <tr>
    <td width="50%"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/aquahitt/artikeep/main/docs/media/versions-dark.png">
      <img alt="Панель элемента: превью, откуда он взялся, история версий" src="https://raw.githubusercontent.com/aquahitt/artikeep/main/docs/media/versions-light.png">
    </picture></td>
    <td width="50%"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/aquahitt/artikeep/main/docs/media/compare-dark.png">
      <img alt="Две версии рядом и изменённые строки текста" src="https://raw.githubusercontent.com/aquahitt/artikeep/main/docs/media/compare-light.png">
    </picture></td>
  </tr>
  <tr>
    <td>Каждое сохранение, которое что-то меняет, — версия: время, метка, объём изменений.</td>
    <td>Сравнение любых двух версий: обе страницы живые, плюс что поменялось в тексте.</td>
  </tr>
  <tr>
    <td><img alt="Полнотекстовый поиск по всем элементам с подсветкой совпадений" src="https://raw.githubusercontent.com/aquahitt/artikeep/main/docs/media/search-light.png"></td>
    <td align="center"><img alt="Галерея на телефоне" src="https://raw.githubusercontent.com/aquahitt/artikeep/main/docs/media/mobile-light.png" width="210"></td>
  </tr>
  <tr>
    <td>Полнотекстовый поиск по всем элементам и источникам, на любом языке.</td>
    <td>Работает и на телефоне.</td>
  </tr>
</table>

Клавиши: `/` поиск, `G` / `L` сетка или список, `←` `→` предыдущий и следующий элемент,
`C` сравнить первую и текущую версии, `Esc` закрыть, `?` все сочетания.

### Как локальное приложение

`artikeep serve` запускает галерею на `http://127.0.0.1:8765` (файлы архива — на следующем
порту; `--port` меняет оба). Вдобавок к файловой версии оно ищет по полному тексту каждого
элемента и подсвечивает совпадение, обновляется само, когда агент что-то сохранил, позволяет
переименовать элемент и добавить описание, сделать старую версию текущей (новой версией:
ничего не перезаписывается), удалить элемент (он остаётся в git-истории архива), показать его
в Finder и добавить файлы или выгрузки чатов, перетащив их на страницу. Страницы, которые
подгружают свои файлы через `fetch()` или ES-модули — браузеры запрещают это для `file://`, —
здесь работают. В Chrome пункт «Установить как приложение» даёт отдельное окно и иконку в доке.

Если сохранить копию не удалось, artikeep сообщает об этом и на рабочем столе (уведомление
macOS или `notify-send` в Linux), не чаще раза в час для каждого вида сбоя; `"notify": false`
это отключает.

## Установка подробно

`install` находит Claude Code (`~/.claude`), Codex (`~/.codex`) и Claude Desktop, добавляет
свои hook-и рядом с вашими (больше ничего не трогает; каждый изменяемый файл сначала
копируется в резервную копию), регистрирует MCP-сервер через собственную команду `mcp add`
каждого агента (для Desktop — в `claude_desktop_config.json`; после этого Desktop нужно
перезапустить) и добавляет короткий блок правил в `~/.claude/CLAUDE.md` и `~/.codex/AGENTS.md`.
Если `~/.local/bin` есть в `PATH`, туда же ставится ссылка на команду `artikeep`.
`--agents claude-code,codex,claude-desktop` ограничивает список агентов, `--dry-run`
показывает изменения, `--uninstall` их откатывает.

Для синхронизации между машинами дайте архиву **приватный** remote:
`artikeep init ~/artikeep --remote git@github.com:you/my-artifacts.git`. Фоновый проход
делает коммит после каждого сохранения и пушит.

По умолчанию Claude Code удаляет транскрипты сессий через 30 дней. `install` поднимает
`cleanupPeriodDays` до десяти лет: транскрипты — последнее место, откуда можно восстановить
потерянный артефакт.

### Плагин для Claude Code

Плагин ([быстрый старт](#claude-code-плагин-рекомендуется)) приносит те же hook-и и
MCP-сервер, что и `install --agents claude-code`. Для Claude Code выберите что-то одно, не оба
способа: иначе каждый артефакт сохранится дважды (`artikeep doctor` об этом предупредит).
Остальное, что делает `install`, плагину недоступно: подключить Codex и Claude Desktop,
добавить блок правил в `CLAUDE.md` и поднять `cleanupPeriodDays` (`doctor` напомнит).

## Использование

```bash
artikeep open                      # галерея как файл: фильтры, версии, сравнение
artikeep serve --open              # та же галерея как локальное приложение
artikeep search планировка кухни   # полнотекстовый, любой язык; --agent, --type, --project, --json
artikeep add ~/Downloads/report.pdf --title "Отчёт за Q3"
artikeep import chatgpt ~/Downloads/chatgpt-export.zip
artikeep scan codex --all          # сохранить результаты прошлых сессий Codex
artikeep scan claude-code          # подобрать пропущенные публикации за 30 дней (--days N, --all)
artikeep rebuild                   # пересобрать галерею и поисковый индекс, коммит и пуш
```

(`artikeep` здесь — команда, установленная `uv tool` или `pipx`, ссылка, которую `install`
поставил в `~/.local/bin` для клона, или `python3 <клон>/bin/artikeep`. Если стоит только
плагин, запускайте любую из них как `uvx artikeep …`.)

**Из любого агента** через MCP:

| Инструмент | Что делает |
|---|---|
| `search_artifacts` | ищет элементы по словам, источнику, типу |
| `read_artifact` | метаданные, список файлов и текст элемента или одной из его версий |
| `list_versions` | версии со временем, меткой и объёмом изменений |
| `diff_versions` | изменённые строки текста между двумя версиями |
| `save_artifact` | сохраняет страницу или документ (выключено без `--mcp-save`) |

По умолчанию агент видит только элементы, сделанные в репозитории, где он работает. Почему
так и как это расширить — в [SECURITY.md](https://github.com/aquahitt/artikeep/blob/main/SECURITY.md).

## Настройки

Архив лежит в `~/artikeep`, если только `artikeep init <путь>` не выбрал другую папку
(запоминается в `~/.config/artikeep/config.json`) или не задан `$ARTIKEEP_HOME`. Поведение
задаётся в `artikeep.json` в корне архива, так что настройки переезжают вместе с ним:

| Ключ | По умолчанию | Что делает |
|---|---|---|
| `git_push` | `true` | пушить в remote архива после каждого коммита |
| `thumbnails` | `"auto"` | миниатюры в галерее, если `python3` может импортировать Playwright; `"off"` отключает |
| `issue_links` | `true` | связывать элементы с GitHub issues, которые на них ссылаются (нужен `gh`), раз в день |
| `lang` | `"auto"` | язык галереи и сообщений hook-ов: `"en"`, `"ru"` или по браузеру / локали |
| `notify` | `true` | уведомление на рабочем столе, если сохранить копию не удалось |
| `mcp_scope` | `"project"` | `"all"` открывает агентам элементы всех проектов |
| `mcp_save` | `false` | разрешить агентам сохранять через MCP |
| `codex_extensions` | `.html .htm .svg .md .pdf .docx .pptx .xlsx .csv` | какие файлы сессии Codex считаются результатом работы |

## Как это устроено

<img alt="Claude Code, Codex, Claude Desktop, выгрузки чатов и любые файлы попадают в ~/artikeep, git-репозиторий; галерея, MCP-сервер и приватный remote читают из него" src="https://raw.githubusercontent.com/aquahitt/artikeep/main/docs/media/how-it-works.svg" width="100%">

Hook-и только копируют файлы и запускают отдельный фоновый проход, так что агент никогда не
ждёт диска или сети. Фоновый проход собирает просмотрщики (холсты Design, документы Markdown,
React-компоненты с библиотеками, которые могут импортировать артефакты claude.ai: React,
Tailwind, recharts, lucide-react, lodash, d3, mathjs, PapaParse, SheetJS, three, Tone,
Chart.js и заглушки для shadcn/ui), делает офлайн-копии с локальными копиями скриптов и
шрифтов с CDN, обновляет поисковый индекс (SQLite FTS5) и галерею, затем коммитит и пушит.
Формат на диске описан в [FORMAT.md](https://github.com/aquahitt/artikeep/blob/main/FORMAT.md);
писать в архив может любой инструмент.

## Ограничения, честно

- **macOS и Linux.** Windows не поддерживается (блокировки файлов через `fcntl`).
- **Форматы хост-программ не документированы.** Входные данные hook-ов инструмента
  `Artifact` в Claude Code, rollout-файлы Codex и экспорт Claude Docs могут измениться в любом
  релизе. artikeep пишет каждый сырой вход hook-а в `.hooklog/payloads.jsonl`, а при старте
  сессии проверяет свежие транскрипты на пропущенные публикации и сохраняет их задним числом.
  `artikeep doctor` показывает, когда каждый источник последний раз что-то сохранил.
- **Импортёры проверены на документированных структурах и синтетических выгрузках**, а не на
  множестве настоящих. Всё, что они не распознали, подсчитывается и выводится, а не угадывается.
  Если импорт прошёл неправильно, откройте issue с обезличенным примером.
- **У Codex нет инструмента для артефактов.** artikeep узнаёт результаты работы по
  расширению, по тому, что файл лежит вне git, и по упоминанию в итоговом ответе. Файл, который
  записал скрипт, а ответ не упомянул, будет пропущен.
- **Веб-чаты не сохраняются на лету.** ChatGPT и claude.ai попадают в архив через выгрузки
  данных, которые запрашиваются вручную.

## Разработка

```bash
python3 -m unittest discover -s tests -t .     # тесты, без зависимостей
scripts/e2e-codex.sh                           # живая проверка адаптера Codex: один настоящий запрос к Codex
scripts/readme-media/make.sh                   # пересобрать скриншоты и GIF для README
```

Скриншоты сняты с синтетического архива (`scripts/readme-media/seed.py`), а не с чьего-то
настоящего; для пересборки нужны Playwright с Chromium и Pillow.

## Лицензия

MIT. Изменения перечислены в [CHANGELOG.md](https://github.com/aquahitt/artikeep/blob/main/CHANGELOG.md).
