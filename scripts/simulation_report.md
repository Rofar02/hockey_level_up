# IceLevel -- долгосрочная симуляция (26 недель), отчёт

Сгенерировано: 2026-08-19T03:48:31.519840+00:00Z

## Сценарий: stable
3x/неделю, 26 недель, благоприятный feedback -- без сбоев

- Тестовый пользователь: `b7535f6f-2e9d-4864-a93d-18820abffb6e`
- Всего завершённых сессий: 78
- Время выполнения сценария: 70.494s

### 1. Таймлайн переходов block_phase
| Сессия # | Неделя | Дата (пн) | Было | Стало |
|---|---|---|---|---|
| 6 | 3 | 2025-01-20 | block 1/accumulation | block 1/intensification |
| 12 | 5 | 2025-02-03 | block 1/intensification | block 1/deload |
| 18 | 7 | 2025-02-17 | block 1/deload | block 2/accumulation |
| 24 | 9 | 2025-03-03 | block 2/accumulation | block 2/intensification |
| 30 | 11 | 2025-03-17 | block 2/intensification | block 2/deload |
| 36 | 13 | 2025-03-31 | block 2/deload | block 3/accumulation |
| 42 | 15 | 2025-04-14 | block 3/accumulation | block 3/intensification |
| 48 | 17 | 2025-04-28 | block 3/intensification | block 3/deload |
| 54 | 19 | 2025-05-12 | block 3/deload | block 4/accumulation |
| 60 | 21 | 2025-05-26 | block 4/accumulation | block 4/intensification |
| 66 | 23 | 2025-06-09 | block 4/intensification | block 4/deload |
| 72 | 25 | 2025-06-23 | block 4/deload | block 5/accumulation |

### 2. Кривая level/xp (контрольные точки каждые 4 недели)
| Неделя | level | xp | макс. доступная сложность |
|---|---|---|---|
| 1 | 4 | 156 | 2 |
| 5 | 10 | 430 | 3 |
| 9 | 13 | 532 | 3 |
| 13 | 15 | 530 | 5 |
| 17 | 16 | 1406 | 5 |
| 21 | 18 | 196 | 5 |
| 25 | 19 | 107 | 5 |

### 3. Срабатывания тормозов
Ни один тормоз не сработал.

### 4. Распределение наград по target_stat
| Stat | Кол-во начислений | Суммарный прирост |
|---|---|---|
| agility | 505 | 27539.32 |
| endurance | 120 | 2972.53 |
| intellect | 44 | 739.08 |
| strength | 238 | 10622.67 |

### 5. Исключения при накоплении истории
Исключений не зафиксировано.

### 6. Тайминги резолва блока/сборки сессии -- первые 10 vs последние 10
- resolve (block/overload): первые 0.022s -> последние 0.014s
- assembly (сборка недели): первые 0.121s -> последние 0.098s

## Сценарий: irregular
Переменная частота (густо/пусто), включая гэп > 8 недель

- Тестовый пользователь: `e4393c3f-2cdc-4433-8c5d-5e6a38d8c2dd`
- Всего завершённых сессий: 36
- Время выполнения сценария: 28.572s

### 1. Таймлайн переходов block_phase
| Сессия # | Неделя | Дата (пн) | Было | Стало |
|---|---|---|---|---|
| 6 | 3 | 2025-01-20 | block 1/accumulation | block 1/intensification |
| 12 | 5 | 2025-02-03 | block 1/intensification | block 1/deload |
| 18 | 11 | 2025-03-17 | block 1/deload | block 2/accumulation |
| 24 | 13 | 2025-03-31 | block 2/accumulation | block 2/intensification |
| 24 | 21 | 2025-05-26 | block 2/intensification | block 2/deload |
| 30 | 24 | 2025-06-16 | block 2/deload | block 3/accumulation |
| 36 | 26 | 2025-06-30 | block 3/accumulation | block 3/intensification |

### 2. Кривая level/xp (контрольные точки каждые 4 недели)
| Неделя | level | xp | макс. доступная сложность |
|---|---|---|---|
| 1 | 4 | 146 | 2 |
| 5 | 9 | 410 | 3 |
| 9 | 10 | 400 | 3 |
| 13 | 13 | 122 | 3 |
| 17 | 13 | 122 | 3 |
| 21 | 13 | 122 | 3 |
| 25 | 15 | 260 | 5 |

### 3. Срабатывания тормозов
Ни один тормоз не сработал.

### 4. Распределение наград по target_stat
| Stat | Кол-во начислений | Суммарный прирост |
|---|---|---|
| agility | 234 | 8846.82 |
| endurance | 52 | 603.35 |
| intellect | 14 | 78.12 |
| strength | 120 | 3903.41 |

### 5. Исключения при накоплении истории
Исключений не зафиксировано.

### 6. Тайминги резолва блока/сборки сессии -- первые 10 vs последние 10
- resolve (block/overload): первые 0.009s -> последние 0.011s
- assembly (сборка недели): первые 0.055s -> последние 0.049s

## Сценарий: overloaded
3x/неделю, спроектированные всплески hard/max для обоих тормозов

- Тестовый пользователь: `2dea2f78-d789-48b0-b20c-80ee27c9f66b`
- Всего завершённых сессий: 78
- Время выполнения сценария: 68.342s

### 1. Таймлайн переходов block_phase
| Сессия # | Неделя | Дата (пн) | Было | Стало |
|---|---|---|---|---|
| 6 | 3 | 2025-01-20 | block 1/accumulation | block 1/intensification |
| 12 | 5 | 2025-02-03 | block 1/intensification | block 1/deload |
| 18 | 7 | 2025-02-17 | block 1/deload | block 2/accumulation |
| 24 | 9 | 2025-03-03 | block 2/accumulation | block 2/intensification |
| 30 | 11 | 2025-03-17 | block 2/intensification | block 2/deload |
| 36 | 13 | 2025-03-31 | block 2/deload | block 3/accumulation |
| 42 | 15 | 2025-04-14 | block 3/accumulation | block 3/intensification |
| 48 | 17 | 2025-04-28 | block 3/intensification | block 3/deload |
| 54 | 19 | 2025-05-12 | block 3/deload | block 4/accumulation |
| 60 | 21 | 2025-05-26 | block 4/accumulation | block 4/intensification |
| 66 | 23 | 2025-06-09 | block 4/intensification | block 4/deload |
| 72 | 25 | 2025-06-23 | block 4/deload | block 5/accumulation |

### 2. Кривая level/xp (контрольные точки каждые 4 недели)
| Неделя | level | xp | макс. доступная сложность |
|---|---|---|---|
| 1 | 5 | 23 | 2 |
| 5 | 10 | 230 | 3 |
| 9 | 13 | 362 | 3 |
| 13 | 15 | 200 | 5 |
| 17 | 16 | 1046 | 5 |
| 21 | 17 | 1435 | 5 |
| 25 | 18 | 1516 | 5 |

### 3. Срабатывания тормозов
| Сессия # | Неделя | Дата | Тормоз | Событие | Детали |
|---|---|---|---|---|---|
| 2 | 1 | 2025-01-08 | tactical | engaged | feedback this session: {'hard': 4, 'normal': 1, 'max': 3} |
| 7 | 3 | 2025-01-20 | tactical | released | feedback this session: {'normal': 4, 'hard': 1} |
| 7 | 3 | 2025-01-20 | structural | push | throttle 0 -> 1 |
| 8 | 3 | 2025-01-22 | structural | recover | throttle 1 -> 0 |
| 11 | 4 | 2025-01-29 | tactical | engaged | feedback this session: {'max': 1, 'hard': 3} |
| 13 | 5 | 2025-02-03 | tactical | released | feedback this session: {'easy': 1, 'normal': 2} |
| 26 | 9 | 2025-03-05 | tactical | engaged | feedback this session: {'hard': 4, 'max': 1, 'normal': 1} |
| 28 | 10 | 2025-03-10 | structural | push | throttle 0 -> 1 |
| 31 | 11 | 2025-03-17 | tactical | released | feedback this session: {'easy': 2, 'normal': 4, 'hard': 1} |
| 32 | 11 | 2025-03-19 | structural | recover | throttle 1 -> 0 |
| 35 | 12 | 2025-03-26 | tactical | engaged | feedback this session: {'normal': 1, 'hard': 3, 'max': 3} |
| 37 | 13 | 2025-03-31 | tactical | released | feedback this session: {'normal': 2, 'easy': 2} |
| 50 | 17 | 2025-04-30 | tactical | engaged | feedback this session: {'max': 1, 'hard': 3} |
| 52 | 18 | 2025-05-05 | structural | push | throttle 0 -> 1 |
| 55 | 19 | 2025-05-12 | tactical | released | feedback this session: {'easy': 1, 'normal': 5} |
| 56 | 19 | 2025-05-14 | structural | recover | throttle 1 -> 0 |
| 59 | 20 | 2025-05-21 | tactical | engaged | feedback this session: {'normal': 1, 'hard': 3, 'max': 5} |
| 61 | 21 | 2025-05-26 | tactical | released | feedback this session: {'easy': 3, 'hard': 1, 'normal': 1} |
| 74 | 25 | 2025-06-25 | tactical | engaged | feedback this session: {'hard': 3, 'max': 2} |
| 76 | 26 | 2025-06-30 | structural | push | throttle 0 -> 1 |

### 4. Распределение наград по target_stat
| Stat | Кол-во начислений | Суммарный прирост |
|---|---|---|
| agility | 505 | 27434.95 |
| endurance | 112 | 2508.55 |
| intellect | 33 | 493.9 |
| strength | 202 | 8350.04 |

### 5. Исключения при накоплении истории
Исключений не зафиксировано.

### 6. Тайминги резолва блока/сборки сессии -- первые 10 vs последние 10
- resolve (block/overload): первые 0.014s -> последние 0.017s
- assembly (сборка недели): первые 0.134s -> последние 0.119s

## Сценарий: fast_progress
3x/неделю, преимущественно easy/normal -- кривая level

- Тестовый пользователь: `def56ac5-2c9d-4602-928e-6de02e0f3114`
- Всего завершённых сессий: 78
- Время выполнения сценария: 71.354s

### 1. Таймлайн переходов block_phase
| Сессия # | Неделя | Дата (пн) | Было | Стало |
|---|---|---|---|---|
| 6 | 3 | 2025-01-20 | block 1/accumulation | block 1/intensification |
| 12 | 5 | 2025-02-03 | block 1/intensification | block 1/deload |
| 18 | 7 | 2025-02-17 | block 1/deload | block 2/accumulation |
| 24 | 9 | 2025-03-03 | block 2/accumulation | block 2/intensification |
| 30 | 11 | 2025-03-17 | block 2/intensification | block 2/deload |
| 36 | 13 | 2025-03-31 | block 2/deload | block 3/accumulation |
| 42 | 15 | 2025-04-14 | block 3/accumulation | block 3/intensification |
| 48 | 17 | 2025-04-28 | block 3/intensification | block 3/deload |
| 54 | 19 | 2025-05-12 | block 3/deload | block 4/accumulation |
| 60 | 21 | 2025-05-26 | block 4/accumulation | block 4/intensification |
| 66 | 23 | 2025-06-09 | block 4/intensification | block 4/deload |
| 72 | 25 | 2025-06-23 | block 4/deload | block 5/accumulation |

### 2. Кривая level/xp (контрольные точки каждые 4 недели)
| Неделя | level | xp | макс. доступная сложность |
|---|---|---|---|
| 1 | 5 | 13 | 2 |
| 5 | 11 | 34 | 3 |
| 9 | 13 | 752 | 3 |
| 13 | 15 | 830 | 5 |
| 17 | 17 | 265 | 5 |
| 21 | 18 | 676 | 5 |
| 25 | 19 | 477 | 5 |

### 3. Срабатывания тормозов
Ни один тормоз не сработал.

### 4. Распределение наград по target_stat
| Stat | Кол-во начислений | Суммарный прирост |
|---|---|---|
| agility | 534 | 29986.25 |
| endurance | 119 | 2715.33 |
| intellect | 43 | 697.1 |
| strength | 231 | 10434.99 |

### 5. Исключения при накоплении истории
Исключений не зафиксировано.

### 6. Тайминги резолва блока/сборки сессии -- первые 10 vs последние 10
- resolve (block/overload): первые 0.013s -> последние 0.014s
- assembly (сборка недели): первые 0.115s -> последние 0.112s
