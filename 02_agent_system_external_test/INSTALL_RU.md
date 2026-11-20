# Внешний TEST 2024–2026: порядок работы

Отдельный проект для базы данных из публикаций 2024–2026 гг. (внешний TEST по TFM §3.1).
Протокол извлечения, проверки и QA тот же, что у базы A399 (TRAIN_DEV). Отличаются область,
временное окно, роль `EXTERNAL_TEST` и проверки целостности теста. Проект A399 и его база не меняются.

## Что гарантирует пакет
- **Модель заморожена до теста.** Пока нет `MODEL_FREEZE.json` в ML-пакете, `preflight` не проходит, а `seed` и `claim` отказываются работать. Финальный гейт `model_frozen_before_test_extraction` проверяет, что заморозка была раньше первой задачи.
- **Ослепление.** Агенты не могут читать ML-пакет (модель, прогнозы) и проект A399: это блокирует хук.
- **Нет пересечения с TRAIN_DEV.** Статьи с DOI или названием из A399 исключаются при сборке корпуса и ещё раз проверяются гейтом `no_overlap_with_train_dev`.
- **Тот же отбор, что у A399.** Каждая статья сначала проходит отбор по критериям включения (SCOPE, классы A–E/X) и проверку даты первой онлайн-публикации по оригиналу (TEMPORAL). Версия, вышедшая онлайн до 2024-01-01, исключается автоматически.

## Шаги

**1. Заморозить модель (в ML-пакете).** Откройте `03_freeze_model.ipynb`, переключите подтверждение на True и выполните.
Появится `SynerPlant_Local_ML\outputs\MODEL_FREEZE.json`. После этого модель менять нельзя.

**2. Подтвердить сопоставление файлов.** Откройте `inputs\file_mapping_FOR_CONFIRMATION.xlsx`, лист `mapping`.
- Строки `AUTO` уже подтверждены: файл опознан по DOI или названию на первой странице либо по правилам издателя.
- **Жёлтые строки проверьте сами**, в колонке `approved` поставьте `yes`:
  - `PROPOSED_DOWNLOAD_TIME_AFTER:…` — приложение Frontiers («Data Sheet 1», «table 1»…), привязанное к статье, скачанной непосредственно перед ним;
  - `SEVERAL_PDFS_SAME_STUDY` — у статьи два PDF: основной текст и приложение;
  - `NOT_IN_REGISTRY` (T101–T110) — полный текст, которого нет в реестре. Это вне заранее заданного поиска: подтвердите, чтобы включить, или впишите `IGNORE` в `study_id`.
- Если привязка неверна, исправьте `study_id` (T###) или `role` (FULLTEXT/SUPPLEMENT).
- Лист `registry`: 28 записей реестра без полного текста. Можно добавить их PDF в папку статей и повторить шаг 2 (запустите `.venv\Scripts\python tools\bootstrap_test_corpus.py` ещё раз — ваши отметки сохранятся) или принять, что они не войдут в тест.

**3. Собрать корпус и манифесты (один раз).** Закройте Excel и выполните:
```
.venv\Scripts\python tools\bootstrap_test_corpus.py --finalize
```
Будут созданы:
- копия корпуса только для чтения в `C:\Users\lenovo\Desktop\master's\TFM_TEST_2024_2026_CORPUS`; оригиналы в папке статей не трогаются;
- `manifests\scope_TEST.csv`, `source_manifest_TEST.csv`, `train_dev_identity.csv` и `excluded_registry_records.csv`;
- стартовая книга и настройки (`config\paths.yaml`, значения в `config\pipeline.yaml`).

**4. Создать базу и очередь.**
```
.venv\Scripts\Activate.ps1
python tools/tfm.py init
python tools/tfm.py import-xlsx
python tools/tfm.py preflight
python tools/tfm.py metadata-normalize
python tools/tfm.py seed
```
`preflight` должен вернуть `PASS` и записать хеш MODEL_FREEZE. `seed` создаёт задачи SCOPE и TEMPORAL для каждой статьи.

**5. Запустить агентов.** В этой папке откройте `claude` и выполните `/tfm-finalize`. Агенты работают так же, как при A399:
SCOPE и TEMPORAL → TRIAGE → DESIGN → извлечение A/B и графики → модераторы → RoB → QA → гейты → аудит человеком → `export`.
При прерывании: `claude --continue`, затем снова `/tfm-finalize`.

**6. Передать тест в ML-пакет (один раз, после финальной выгрузки).**
```
cd C:\Users\lenovo\Desktop\SynerPlant_Local_ML_Starter\SynerPlant_Local_ML
.venv\Scripts\python build_handoff_from_freeze.py --external-test --freeze "<путь к exports\DATA_FREEZE_... тестовой базы>"
```
Затем однократно выполните `04_external_test_LATER.ipynb`. Повторный запуск теста запрещён самим пакетом.

## Проверка пакета
```
.venv\Scripts\python -m unittest tests.test_external_test_mode
```
