# План доработок memo: UI/UX, code review, Stage 5

## Context

`memo` — локальный AI-ассистент для документов (Tauri + React + FastAPI sidecar + Ollama).
UC-01..UC-04 реализованы (Stages 0–4), **Stage 5 (polish/onboarding/сборка) не начат**.

Пользователь хочет: (1) улучшить UI/UX, (2) исправить найденные при code review проблемы
корректности/оптимизации, (3) завершить Stage 5. Скоуп — **всё**.

Направление по UI: полировка текущей тёмной VSCode-темы + насыщенная, но не перегруженная
обратная связь (прогресс-бары, спиннеры, скелетоны, step-indicator, закрываемые toast,
status-badge). Иконки — SVG через `lucide-react` (чистые SVG-компоненты, кроссплатформенно,
без нативных зависимостей). UX-приоритет №1 — **отмена генерации** и **состояния загрузки**.

### Что НЕ делаем (ложные срабатывания субагентов, проверено по коду)
- «Эмбеддинг считается дважды» — неверно: вопрос эмбеддится один раз (`rag.py:120`).
- «stale-warning проверяет только первый файл» — неверно: `break` стоит ПОСЛЕ установки флага (`rag.py:132-138`).
- «Мутация состояния в useAppStore» — неверно: иммутабельные апдейты корректны (`useAppStore.ts:121-138`).

---

## Подход

6 фаз, можно выполнять инкрементально и независимо коммитить. Фаза 0 — фундамент для всего UI.
Самый рискованный пункт (продакшн-бандлинг Python) изолирован в Фазе 5 и помечен.

---

## Фаза 0 — Фундамент UI (design tokens + иконки)

**Цель:** убрать хардкод цветов/размеров, дать общую базу для всех UI-доработок.

- `src/frontend/src/index.css`: добавить `:root` с CSS-переменными на основе **текущей** палитры
  (не меняя вид): цвета (`--bg #1e1e1e`, `--panel #252526`, `--panel-2 #1a1a1a`, `--text #cccccc`,
  `--text-muted #888`, `--accent #0078d4`, `--ok`, `--warn`, `--err`, `--border`), типошкала
  (`--fs-xs 11px … --fs-lg 16px`), отступы (`--sp-1..6`), радиусы (`--r-sm/md/lg`), переходы
  (`--t-fast 120ms`), z-index. Завести `--font-mono` для путей/preview.
- Прогнать существующие `*.css` компонентов на использование переменных (механическая замена
  хардкод-значений). Файлы: `App.css`, `components/**/**.css`.
- Добавить зависимость `lucide-react` в `package.json`. Создать тонкую обёртку
  `src/frontend/src/components/ui/Icon.tsx` (ре-экспорт нужных иконок + единый размер/`aria-hidden`).
- `prefers-reduced-motion`: глобальный media-guard, отключающий анимации.

---

## Фаза 1 — Переиспользуемые UI-компоненты обратной связи

Новая папка `src/frontend/src/components/ui/`:

- **`Spinner.tsx`** — инлайн-спиннер (SVG, `aria-label`).
- **`Skeleton.tsx`** — плейсхолдер-блоки с shimmer (respect reduced-motion).
- **`ProgressBar.tsx`** — вынести существующую логику прогресса индексации в общий компонент
  (сейчас дублируется в `LeftPanel`/`Chat`), добавить `aria-valuenow`.
- **`StepIndicator.tsx`** — для многошаговых операций (индексация: «Чтение → Эмбеддинг → Запись»;
  организация: «Анализ → Кластеризация → Превью»).
- **`StatusBadge.tsx`** — статус-чип (indexed/stale/error/indexing) с иконкой lucide + цветом токена.
- **`Toast`** — система уведомлений:
  - слайс в `useAppStore.ts`: `toasts: Toast[]`, `pushToast`, `dismissToast` (id, kind: info/success/warn/error, авто-dismiss с таймером, кнопка закрытия).
  - `components/ui/ToastContainer.tsx` монтируется в `App.tsx`, рендерит стек справа-снизу.
  - Заменить нынешние инлайн-сообщения об ошибках/успехе (`LeftPanel`, `DocGenerator`) на toast там, где это разовое событие; постоянные состояния (ошибки индексации списком) оставить инлайн.

**Иконки:** заменить эмодзи на lucide:
- `FileTree.tsx`: `File`/`Folder`/`FolderOpen` + статус через `StatusBadge` (`CheckCircle2`/`AlertTriangle`/`XCircle`/`Loader2`).
- Кнопки тулбаров (`LeftPanel`, `Chat`, `ChatList`, `DocGenerator`, `OrganizePreview`): осмысленные иконки + сохранить `title`/добавить `aria-label`.

---

## Фаза 2 — Отмена генерации + состояния загрузки (UX-приоритет)

**Отмена генерации (frontend):**
- `api/chat.ts`, `api/generate.ts`, `api/index.ts`: пробросить `AbortSignal` в `fetch` для
  `streamMessage`/`streamGenerate`/`streamIndex`. На `abort` генератор завершается, `reader.cancel()`
  уже есть в `finally`.
- Хранить `AbortController` в ref компонента (`Chat.tsx`, `DocGenerator.tsx`). Кнопка **«Стоп»**
  (lucide `Square`/`X`) в тулбаре, видна во время стриминга; по клику — `controller.abort()` +
  сброс `streamingChatId`.

**Отмена генерации (backend):**
- `api/chats.py stream()`: при разрыве соединения сохранять **частичный** ответ ассистента.
  Обернуть тело в `try/finally`; в `finally`, если `done` не наступил, но `full_content` непуст —
  `chat_store.add_message(..., "".join(full_content), ..., partial=True)` (добавить флаг/маркер).
  Закрывает заодно code-review-stage2 #1 (потеря ответа при ошибке Ollama).

**Состояния загрузки:**
- `Chat.tsx`: skeleton-сообщения при загрузке истории чата; «typing»-индикатор (spinner) в момент
  между отправкой и первым токеном; для индексации внутри стрима — `StepIndicator`/`ProgressBar`.
- `ChatList.tsx`: skeleton-строки при первой загрузке списка; spinner на кнопке удаления во время запроса.
- `FileTree`/`LeftPanel`: skeleton дерева вместо «Введите путь…» во время загрузки `/fs/tree`;
  сейчас есть искусственный `setTimeout(1500)` на refresh-stale — **убрать**, заменить реальным состоянием.
- `DocGenerator.tsx`: показывать preview инкрементально во время генерации (уже стримится) + кнопка «Стоп».

---

## Фаза 3 — Корректность и оптимизация бэкенда

- **`indexer.py mark_changed_stale` (N+1):** заменить цикл `query(...).first()` на один
  `query(IndexState).filter(IndexState.file_path.in_(paths)).all()` + словарь по `file_path`.
- **Хеширование вне event loop:** в `api/chats.py:114` `mark_changed_stale(expanded)` вызывается
  синхронно в async-генераторе → блокирует loop на больших контекстах. Обернуть в
  `await asyncio.to_thread(mark_changed_stale, expanded)`. Аналогично `_files_needing_index`.
- **Блокирующие вызовы ChromaDB:** в `index_files` (`indexer.py:174-201`) `collection.get/delete/add`
  синхронны внутри async-генератора. Обернуть в `await asyncio.to_thread(...)`.
- **`organizer.py`:** заменить N+1 `collection.get(where={file_path})` на один батч-запрос
  с `{"file_path": {"$in": paths}}`; объединить двойной запрос (embeddings + documents) в один
  `include=["embeddings","documents"]`. Тяжёлый KMeans/silhouette — в `asyncio.to_thread`.
- **`rag.py:136` ложные stale-warning:** не выставлять `stale_warning` для файлов со `status=="error"`,
  если расширение не в `SUPPORTED` (перманентно неиндексируемые). Предупреждать только о реальной
  устарелости (`stale`) и о транзиентных ошибках поддерживаемых форматов.
- **`chroma.py`:** кэшировать объект коллекции (сейчас `get_or_create_collection` на каждый вызов).
- **`ollama_client.py`:** вынести `import json`/`import asyncio` на верх модуля (сейчас внутри
  горячих циклов `generate_stream`/`chat_stream`/`embed`); снизить read-timeout стрима с 300s до
  разумного (connect ~5s, read ~120s). Не ломать ретраи на 500 (загрузка модели).
- **(Опционально, code-review-stage2 #3)** `num_ctx` 4096→8192 в `chat_stream`/`generate_stream`
  или вынести в настройки — против переполнения контекста при длинной истории + RAG.
- **(Опционально)** вынести дублирующийся `_INVALID_CHARS`/санитайз имени файла в
  `memo/services/utils.py`, добавить проверку зарезервированных Windows-имён (CON/PRN/AUX/…).

### Алгоритмы: генерация имён и организация (проверено по коду)

- 🔴 **Утечка `<think>` в имена папок (`organizer._name_cluster`, organizer.py:124).** В отличие от
  `rag.py`/`doc_generator.py`, здесь нет срезания inline `<think>…</think>` — берётся `.splitlines()[0]`.
  Если `qwen3:1.7b` игнорирует `think=False` (задокументировано для qwen3), имя папки становится
  reasoning-мусором (`think`, «Хорошо, мне нужно…»). **Вынести общий стриппер reasoning** (из rag/doc_gen)
  в `memo/services/utils.py` и применить в `_name_cluster`. (Связано с уже запланированным выносом санитайза.)
- ⚠️ **Мёртвая ветка single-cluster (organizer.py:52-78, 180).** `_cluster` для n≥3 всегда даёт `k≥2`,
  поэтому `single_cluster` (UC-03 «все документы одной темы → одна папка + предупреждение») фактически
  срабатывает только для одного файла. Добавить детекцию одной темы: оценивать качество при k=1
  (низкий лучший silhouette / высокая внутрикластерная близость → вернуть один кластер + флаг).
- ⚠️ **Euclidean KMeans в cosine-пространстве (organizer.py:45-77).** Коллекция Chroma создана с метрикой
  cosine, а KMeans/`silhouette_score` считают евклидово; усреднение чанков денормирует вектор.
  **L2-нормировать** усреднённые векторы перед KMeans (или `silhouette_score(..., metric="cosine")`).
- 🔴 **Имя папки описывает только один (первый) файл — ПОДТВЕРЖДЕНО тестом пользователя**
  (`analyze` organizer.py:185-202 + `_name_cluster` :98-130). Сейчас на нейминг идёт первый чанк
  максимум 2 файлов (`cpaths[:2]` → `docs[0]`, отсортированы по алфавиту), имена файлов модели не
  передаются, а промпт не требует «общую тему ВСЕХ». Маленькая `qwen3:1.7b` залипает на титул первого
  документа.
  **Решение — нейминг по содержанию ВСЕХ документов кластера через cross-cluster TF-IDF + LLM-полировка**
  (выбрано как лучшее для сценариев вида рецепты/тренировки/путешествия: общий словарь темы повторяется
  во всех файлах кластера, а частности — блюда/страны — лишь в одном, и TF-IDF их гасит):
  1. Для каждого кластера собрать **все чанки всех его файлов** одним батч-запросом
     `collection.get(where={"file_path": {"$in": cpaths}}, include=["documents"])` (заодно убирает
     текущий N+1) и склеить в один текст-кластера.
  2. Обучить `sklearn.feature_extraction.text.TfidfVectorizer` на корпусе **из текстов-кластеров**
     (каждый кластер = один «документ» → IDF считается МЕЖДУ кластерами, что делает имена различимыми).
     Параметры: `stop_words=list(_STOPWORDS)`, `token_pattern=r"(?u)\b[а-яёa-z]{3,}\b"`,
     `ngram_range=(1,2)` (даёт биграммы «программа тренировок»). Для каждого кластера взять
     **топ-N (≈5) терминов** по TF-IDF-весу.
  3. Передать топ-термины (+ опц. несколько имён файлов как доп. сигнал) в `_name_cluster`; промпт:
     «Вот ключевые слова тематической группы из N документов: …. Назови папку 2–4 словами на русском,
     отражающими ОБЩУЮ тему (а не отдельный документ)».
  4. Из ответа модели **срезать `<think>…</think>`** (общий стриппер из utils, см. пункт выше) и брать
     последнюю непустую строку.
  5. **Фолбэк** (LLM недоступна/пустой ответ): имя = топ TF-IDF-термины (capitalize). `_tfidf_name`
     (:89) заменить на эту cross-cluster версию вместо текущей `chunks[:3]`.
  6. Граничные случаи: 1 кластер → IDF вырождается, TfidfVectorizer корректно откатывается к ранжированию
     по TF (частые осмысленные слова) — приемлемо.
- ⚠️ **Имя файла: markdown-разметка и коллизии (`suggest_filename`, doc_generator.py:38).** Убирать inline
  markdown (`* _ ` `` ` `` `[]()`) из заголовка; зарезервированные Windows-имена; в `save_document`
  (fs.py:66) при коллизии — авто-суффикс `(1)/(2)` вместо жёсткой ошибки 400.
- ⚠️ **Асимметрия валидации папок (`apply_organization`, fs.py:90).** Пользовательское имя проверяется
  только на `/ \ ..`; добавить отсев `:` и зарезервированных имён (через общий санитайзер из utils).
- ⚠️ **Осиротевшие векторы пустого документа (`index_files`, indexer.py:162).** Ветка `if not chunks`
  выходит до удаления старых эмбеддингов → векторы ставшего пустым файла остаются в Chroma.
  Удалять существующие `ids` перед выходом по «Empty document».
- ℹ️ **Чанкинг посимвольный (indexer.py:15), а не потокенный** (tech-spec говорит «~512 токенов»).
  Низкий приоритет; при желании — резать по границам абзацев/предложений для качества ретрива.

---

## Фаза 4 — Stage 5: онбординг и устойчивость

- **`/health` обогащение** (`api/health.py`): возвращать `{ollama: bool, models: {required: [...],
  present: [...], missing: [...]}}`. Требуемые: `bge-m3`, `qwen3:1.7b` (+ рекомендуемый чат `qwen3:4b`).
- **Баннер «Ollama недоступна»** (Stage 5.2): глобальный компонент сверху `App.tsx`, поллит `/health`
  (с backoff), показывается при недоступности, кнопка «Повторить». Использует toast-инфраструктуру/StatusBadge.
- **Онбординг при первом запуске** (Stage 5.1): модал, если есть `missing` модели — список + кнопка
  «Скачать». Backend-эндпоинт `POST /setup/pull-model` стримит прогресс `ollama pull` (Ollama
  `/api/pull` отдаёт прогресс) → `ProgressBar`/`StepIndicator`. Флаг «онбординг пройден» в localStorage.
- **Настройки** (Stage 5.3): панель/модал — `workDir` по умолчанию, embed-модель, чат-модель;
  сохранение в localStorage + (для backend-значений) через настройку/эндпоинт. Иконка-шестерёнка в шапке.
- **Логирование в файл** (Stage 5.4): `logging.handlers.RotatingFileHandler` в `MEMO_DATA_DIR/logs/memo.log`,
  настройка в `main.py` lifespan.
- **Сброс кэша порта** (code-review-stage2 #2, `ipc/backend.ts`): при сетевой ошибке `apiFetch`
  сбрасывать `_port=null`, чтобы переподключиться после рестарта бэкенда.

---

## Фаза 5 — Stage 5: упаковка и финальный polish (рискованная часть)

- **Иконка приложения + splash** (Stage 5.5): `tauri.conf.json` icons, splash-окно.
- **⚠️ Продакшн-бандлинг бэкенда (Stage 5.6, самый рискованный пункт):** сейчас `lib.rs` в релизе
  ищет Python в `resource_dir/backend` и зовёт системный `python` — у конечного пользователя его нет.
  Варианты: PyInstaller (`--onefile`) → положить exe как Tauri **sidecar**, обновить `lib.rs`
  (продакшн-ветка) и `tauri.conf.json` (`bundle.resources`/`externalBin`). Делать аккуратно,
  пер-ОС сборка реалистично требует CI на каждой ОС. **Согласовать объём отдельно** — можно
  ограничиться Windows MSI на первом шаге.
- **Graceful shutdown** (`lib.rs`): сейчас `child.kill()` по `WindowEvent::Destroyed` может оставлять
  дочерние процессы на Windows. Корректно завершать дерево процессов бэкенда.
- **`npm run tauri build`** → проверить установку MSI без dev-окружения.
- **README** (Stage 5.7): инструкции сборки и запуска для стороннего разработчика.

---

## Фаза 6 — Доступность и финальные штрихи (лёгкий проход)

- `aria-label` на icon-only кнопках; `aria-expanded` на сворачиваемых блоках (ошибки, thinking);
  `aria-live="polite"` на области стриминга ответа.
- Глобальный `:focus-visible` ring (`outline: 2px var(--accent)`), сейчас outline сброшен.
- Обработка ресайза окна в `Layout.tsx` (клампить ширину дивайдера при уменьшении окна).
- Субтильные переходы (hover/появление сообщений) на токенах `--t-fast`, под `prefers-reduced-motion`.
- `lang="ru"` на `<html>`.

---

## Критические файлы

**Frontend:** `src/index.css`, `src/App.tsx`, `src/store/useAppStore.ts`, `src/api/{chat,generate,index}.ts`,
`src/ipc/backend.ts`, `src/components/ui/*` (новые), `src/components/{Chat,ChatList,DocGenerator,LeftPanel,FileTree,OrganizePreview}/*`, `package.json`.
**Backend:** `memo/services/{indexer,organizer,rag,ollama_client,chroma,chat_store}.py`,
`memo/api/{chats,health}.py` + новый `memo/api/setup.py`, `memo/main.py`, `memo/services/utils.py` (новый).
**Tauri:** `src-tauri/src/lib.rs`, `src-tauri/tauri.conf.json`.

---

## Verification

- **Backend-юниты:** `cd src/backend && .venv\Scripts\pytest` — расширить `tests/unit`:
  батч `mark_changed_stale`, stale-warning не срабатывает на неподдерживаемый формат, санитайз имени.
- **Запуск:** `cd src/frontend && npm run tauri dev` (Ollama должна быть запущена).
- **Отмена:** начать ответ → «Стоп» в середине → стрим прекращается, частичный ответ сохранён (reload чата).
- **Загрузка:** переключение чатов/папок показывает skeleton; индексация — step-indicator/прогресс.
- **Toast:** ошибка/успех сохранения документа → закрываемый toast.
- **Онбординг/баннер:** остановить Ollama → баннер «недоступна» + retry; удалить модель → онбординг с pull-прогрессом.
- **Иконки/тема:** визуальная проверка кроссплатформенного рендера lucide (SVG, без нативных зависимостей).
- **Сборка (если делаем Фазу 5):** `npm run tauri build` → установить MSI на чистой машине без Python/Node.
