# План: исправление чатов (think-режим, форматирование, мультичат)

## Context

Чат-функциональность (Stage 2) имеет три подтверждённые проблемы. Я изучил весь путь данных
(frontend `Chat.tsx` → `api/chat.ts` → backend `api/chats.py` → `services/rag.py` →
`services/ollama_client.py`) и **эмпирически проверил поведение Ollama 0.9.2** на этой машине.
Выводы ниже основаны на реальных ответах Ollama, а не на догадках.

### Корневые причины (диагностика)

1. **Тумблер «рассуждения» не работает.**
   - Frontend корректно шлёт `thinking: bool`, backend корректно передаёт `think=` в Ollama.
   - НО: **qwen3:4b (чат-модель) игнорирует `think=false`** — всегда генерирует chain-of-thought
     прямо в `response`/`content`, завершая его «висячим» `</think>` **без открывающего** `<think>`.
     Это [Ollama issue #12234](https://github.com/ollama/ollama/issues/12234) (баг шаблона конкретной сборки модели; 8b работает, 4b нет).
   - qwen3:1.7b наоборот — честно соблюдает параметр и возвращает рассуждения в **отдельном поле
     `thinking`**, а `response` остаётся чистым.
   - Текущий код не обрабатывает НИ один из путей: backend читает только `chunk["response"]` и
     полностью игнорирует поле `thinking`; frontend `parseThink` ищет **открывающий** `<think>`,
     которого qwen3:4b не выдаёт → весь CoT + `</think>` вываливается в ответ как «рассуждения всегда включены».

2. **Нет форматирования.** `ReactMarkdown` подключён, но `src/frontend/src/index.css` содержит
   глобальный сброс `*, *::before, *::after { margin:0; padding:0 }`, который убивает маркеры/отступы
   списков и интервалы заголовков/цитат. В `Chat.css` стилизованы только `p/pre/code`. Плюс не
   подключён `remark-gfm` → таблицы/strikethrough/autolink не рендерятся.

3. **Проблемы при мультичате/переключении.**
   - Рассуждения хранятся в `thinkMap`, ключ — эфемерный `Date.now()+1`; после перезагрузки сообщений
     (переключение чата туда-обратно) ключи не совпадают с реальными id из БД → блок рассуждений исчезает.
   - Рассуждения **вообще не сохраняются в БД** → теряются при любой перезагрузке.
   - `isThinking` и `isStreaming` — одиночные глобальные флаги, не привязаны к чату → при стриминге в
     одном чате и переключении в другой состояние «течёт» между чатами и конфликтует при параллельных стримах.

### Решения, согласованные с пользователем
- **Think OFF должен реально работать** → гарантируем на уровне backend (вырезаем рассуждения по
  разделителю `</think>` и/или полю `thinking`), плюс рекомендация обновить Ollama / перетянуть модель.
- **Добавить историю переписки** → перейти на `/api/chat` с массивом `messages` (память чата).
- **Контекст — из текущего выделения** (оставить текущее поведение `selectedPaths`/`workDir`).

---

## Изменения

### Backend

**1. `services/ollama_client.py` — добавить `chat_stream` на `/api/chat`.**
Новый метод (рядом с `generate_stream`), принимает `messages: list[dict]`, `think`, `num_ctx`.
Стримит чанки `/api/chat`, каждый чанк отдаёт `message.content` и `message.thinking` (оба могут быть пустыми).
`think` передаём только если не `None` (как сейчас в `generate_stream`).
`generate_stream` можно оставить (используется при индексации? нет — только в rag; после миграции на chat
станет неиспользуемым, удалить если нет других вызовов).

**2. `services/rag.py` — переписать `answer_stream` на chat-эндпоинт + сплиттер рассуждений.**
- Сигнатура получает `history: list[dict]` (предыдущие реплики `{role, content}` из БД).
- Формируем `messages`: `[{role:"system", content: SYSTEM + блок_контекста}]` + история + `{role:"user", content: question}`.
  Retrieval (эмбеддинг вопроса + `retrieve`) и `stale_warning` остаются как есть; найденные чанки идут в system-блок
  (переиспользовать `build_prompt`, выделив в нём построение блока контекста).
- **Разделение рассуждений и ответа** (устойчивое к обоим поведениям Ollama):
  - Если в чанке есть `thinking` → это рассуждение: при think=ON отдать `{"type":"thinking","content":...}`, при OFF — отбросить.
  - Содержимое `content` пропускать через сплиттер по разделителю `</think>`:
    - до появления `</think>` накапливать; при think=ON стримить как `thinking`, при OFF — буферизировать молча;
    - при встрече `</think>` — всё до него = рассуждение (отбросить/завершить), всё после = ответ, далее стримить `content` как `token` вживую;
    - если `</think>` так и не встретился к концу стрима (чистый ответ без CoT, напр. 1.7b с think=OFF) —
      сбросить накопленный буфер как **ответ** (`token`), не как рассуждение. Это ключевой кейс корректности.
  - Итог: при think=OFF пользователь видит **только чистый ответ** независимо от того, соблюла ли модель параметр.
- Типы событий: `{"type":"thinking",...}`, `{"type":"token",...}`, `{"type":"done", sources, stale_warning}`, `{"type":"error",...}`.

**3. `api/chats.py` — `send_message`.**
- Сформировать `history` из `chat_store.list_messages(chat_id)` (до добавления текущего user-сообщения; роли user/assistant, поле content).
- Передать `history` в `answer_stream`.
- В стриме: накапливать `thinking`-токены отдельно от `content`-токенов; на `done` сохранять оба
  через `chat_store.add_message(chat_id, "assistant", content, sources, thinking=...)`.
- Пробрасывать SSE-событие `thinking` на фронт (сейчас оно теряется).

**4. БД: добавить поле `thinking` в `Message`.**
- `db/models.py`: `thinking = Column(Text, nullable=True)`.
- Миграция авто-применится через существующий `_migrate_add_missing_columns` в `db/session.py` (трогать не нужно).
- `services/chat_store.py`: `add_message(..., thinking: str | None = None)` сохраняет поле; `_msg_to_dict` отдаёт `"thinking"`.

### Frontend

**5. `index.css` / `Chat.css` — починить форматирование Markdown.**
- В `Chat.css` добавить стили, скоупленные на `.chat-message-content`, восстанавливающие то, что съел
  глобальный сброс: `ul/ol` (`padding-left`, `list-style`), `li`, `h1..h6` (размеры/отступы),
  `blockquote`, `hr`, `a`, `strong/em`, `table/th/td` (рамки). Тёмная тема — под существующую палитру.
- Добавить `remark-gfm`: `npm i remark-gfm`, в `Chat.tsx` `<ReactMarkdown remarkPlugins={[remarkGfm]}>`.

**6. `api/chat.ts` — новый тип события + проброс thinking.**
- `ChatEvent` дополнить `| { type: "thinking"; content: string }`.
- `MessageItem` дополнить `thinking?: string`.

**7. `store/useAppStore.ts` — состояние per-chat, рассуждения в самом сообщении.**
- Убрать глобальный `thinkMap`/`isThinking` из логики: рассуждения хранить прямо в объекте сообщения
  (`MessageItem.thinking`). Добавить экшн `updateLastAssistantThinking(content)` (по аналогии с
  `updateLastAssistantMessage`).
- Заменить `isStreaming: boolean` на `streamingChatId: number | null` (+ сеттер). Стрим привязан к чату:
  ввод блокируется/индикатор показывается только для активного чата, равного `streamingChatId`.

**8. `components/Chat/Chat.tsx` — убрать клиентский `parseThink`, читать события.**
- Удалить `parseThink`, локальные `thinkMap`/`isThinking`.
- В цикле `streamMessage`: `token` → `updateLastAssistantMessage(answer += content)`;
  `thinking` → `updateLastAssistantThinking(thinking += content)`; `done` → финализировать и
  `setMessages` с обновлённым `content`/`thinking`/`sources` (как сейчас, плюс thinking).
- Рендер блока «Рассуждения» из `msg.thinking` (не из thinkMap) — переживает переключение и перезагрузку,
  т.к. поле приходит из БД. Показывать блок если `thinkingEnabled` ИЛИ `msg.thinking` непустой.
- Индикатор «Думаю…»: показывать пока для активного чата идёт стрим (`streamingChatId === activeChatId`),
  у последнего ассистент-сообщения есть thinking, но ещё пуст `content`.
- `handleSend`: использовать `streamingChatId` вместо `isStreaming`; сохранить существующий guard
  `getState().activeChatId !== chatId` (он корректно останавливает обновление UI при переключении).

**9. `components/ChatList/ChatList.tsx`.**
- Проверить, что переключение чата (`setActiveChatId` + `setMessages([])`) согласовано с
  `streamingChatId` (не сбрасывать чужой стрим). Существующий `useEffect([activeChatId])` в `Chat.tsx`
  с флагом `cancelled` перезагрузит сообщения корректно.

---

## Критичные файлы
- `src/backend/memo/services/ollama_client.py` — новый `chat_stream`
- `src/backend/memo/services/rag.py` — `answer_stream` на `/api/chat` + сплиттер `</think>` + история
- `src/backend/memo/api/chats.py` — история, проброс/сохранение thinking
- `src/backend/memo/db/models.py` + `services/chat_store.py` — поле `thinking`
- `src/frontend/src/components/Chat/Chat.tsx` — удалить parseThink, читать `thinking`-события
- `src/frontend/src/store/useAppStore.ts` — `streamingChatId`, thinking в сообщении
- `src/frontend/src/api/chat.ts` — типы событий
- `src/frontend/src/components/Chat/Chat.css` + `index.css` — стили Markdown, `remark-gfm`

## Тесты
- `tests/unit/test_rag.py`: добавить кейсы сплиттера — (A) чистый ответ без тегов; (B) `<think>..</think>ответ`;
  (C) `..</think>ответ` (висячий закрывающий, как у qwen3:4b); проверить, что при think=OFF рассуждения
  не попадают в ответ, при think=ON идут в `thinking`-события. Мокать Ollama-стрим.
- `tests/unit/test_chat_store.py`: сохранение/чтение поля `thinking`; история сообщений.

## Verification (end-to-end)
1. `cd src\backend; .venv\Scripts\python -m pytest tests\unit -v` — все unit-тесты зелёные.
2. `cd src\frontend; npx tsc --noEmit` — типы без ошибок.
3. `npm run tauri dev`, модель qwen3:4b:
   - Think **OFF**: ответ без рассуждений и без `</think>` в тексте (главный критерий пользователя).
   - Think **ON**: рассуждения в сворачиваемом блоке «Рассуждения», ответ отдельно, оба переживают
     переключение чатов и перезапуск приложения (берутся из БД).
   - Markdown: списки с маркерами, заголовки, **жирный**, таблицы (gfm), блоки кода — отрисованы.
   - Мультичат: стрим в чате A, переключение в B и отправка там — состояния не конфликтуют; возврат в A
     показывает полный сохранённый ответ.
4. **Рекомендация пользователю** (среда, не код): обновить Ollama и `ollama pull qwen3:4b` —
   тогда `think=false` будет соблюдаться нативно (рассуждения не будут даже генерироваться, экономия времени).
   До обновления backend всё равно скрывает их, так что UX корректен.
```
```
