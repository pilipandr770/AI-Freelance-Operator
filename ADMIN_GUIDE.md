# Admin Panel Guide

## Доступ до адмін панелі

URL: `http://localhost:5000/admin`

## Структура адмін панелі

### 1. Dashboard (`/admin`)

Головна сторінка з оглядом системи:

- **Статистика:**
  - Загальна кількість проєктів
  - Активні проєкти
  - Кількість клієнтів
  - Кількість AI агентів

- **Останні проєкти** - список 5 останніх проєктів
- **Статус системи** - підключення до БД і OpenAI

### 2. AI Agents Management (`/admin/agents`)

Управління AI агентами та їх інструкціями.

#### Структура агента:

```json
{
  "agent_name": "email_parser",
  "system_prompt": "You are an expert email parser...",
  "instruction_text": "Extract project details from email: title, description...",
  "is_active": true,
  "version": 1
}
```

#### Операції:

**Додати нового агента:**
1. Кнопка "+ Add New Agent"
2. Заповнити форму:
   - Agent Name (унікальне, lowercase, без пробілів)
   - System Prompt (роль агента)
   - Instruction Text (детальні інструкції)
   - Active checkbox

**Редагувати агента:**
1. Кнопка "Edit" біля потрібного агента
2. Змінити промпти/інструкції
3. Save (версія автоматично +1)

**Активувати/Деактивувати:**
- Кнопка "Deactivate" / "Activate"
- Деактивовані агенти не викликаються системою

#### Вбудовані агенти:

При ініціалізації БД автоматично створюються:

1. **email_parser** - парсинг вхідних email
2. **scam_filter** - виявлення шахрайства
3. **classification_agent** - класифікація складності
4. **requirement_engineer** - збір вимог від клієнта
5. **estimation_agent** - оцінка годин
6. **dialogue_orchestrator** - ведення діалогу з клієнтом
7. **offer_generator** - генерація комерційних пропозицій

### 3. Projects (`/admin/projects`)

Управління проєктами (в розробці).

Поки що доступно через API:
- `GET /api/projects` - список всіх проєктів
- `GET /api/projects/<id>` - деталі проєкту

### 4. Clients (`/admin/clients`)

Управління клієнтами (в розробці).

### 5. System Settings (`/admin/settings`)

Налаштування системи у runtime:

**Основні налаштування:**
- `hourly_rate` - погодинна ставка ($)
- `auto_negotiation_enabled` - автоматичні переговори
- `auto_invoice_enabled` - автоматичні інвойси
- `prepayment_percentage` - відсоток передоплати
- `scam_filter_threshold` - поріг виявлення scam (0-1)
- `min_project_budget` - мінімальний бюджет проєкту
- `max_project_budget` - максимальний бюджет (вище потребує схвалення)

**Редагування:**
1. Знайти налаштування
2. Кнопка "Edit"
3. Ввести нове значення
4. Зміни застосовуються миттєво

### 6. Activity Logs (`/admin/logs`)

Перегляд журналу дій AI агентів:

**Показує:**
- Час виконання
- Назва агента
- Дія (action)
- Статус (Success/Failed)
- Час виконання (ms)
- Використані токени
- Вартість виклику ($)

**Використання:**
- Моніторинг роботи агентів
- Відстеження витрат на OpenAI API
- Debugging помилок

## API Endpoints для адмін панелі

### Агенти

```bash
# Отримати список всіх агентів
GET /admin/agents

# Отримати агента за ID
GET /admin/agents/<id>

# Створити нового агента
POST /admin/agents
Content-Type: application/json

{
  "agent_name": "my_agent",
  "system_prompt": "You are...",
  "instruction_text": "Do this...",
  "is_active": true
}

# Оновити агента
PUT /admin/agents/<id>
Content-Type: application/json

{
  "agent_name": "my_agent",
  "system_prompt": "Updated prompt...",
  "instruction_text": "Updated instructions...",
  "is_active": true
}

# Активувати/деактивувати агента
POST /admin/agents/<id>/toggle
Content-Type: application/json

{
  "is_active": true
}
```

### Налаштування

```bash
# Отримати всі налаштування
GET /api/settings

# Оновити налаштування
POST /api/settings
Content-Type: application/json

{
  "key": "hourly_rate",
  "value": "75.0",
  "value_type": "float"
}
```

## Приклади використання

### Створення Custom Agent

```bash
curl -X POST http://localhost:5000/admin/agents \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "invoice_generator",
    "system_prompt": "You are a professional invoice generator. Create clear and detailed invoices.",
    "instruction_text": "Generate invoice with: client details, project description, itemized breakdown, payment terms (50% prepayment), payment methods, and due date.",
    "is_active": true
  }'
```

### Оновлення інструкцій для agenta

```bash
curl -X PUT http://localhost:5000/admin/agents/1 \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "email_parser",
    "system_prompt": "You are an expert email parser specializing in freelance project inquiries.",
    "instruction_text": "Extract: 1) Project title 2) Description 3) Budget range 4) Deadline 5) Required tech stack 6) Client contact info. If any critical info is missing, flag for human review.",
    "is_active": true
  }'
```

### Зміна погодинної ставки

```bash
curl -X POST http://localhost:5000/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "key": "hourly_rate",
    "value": "100.0",
    "value_type": "float"
  }'
```

## Best Practices

### Написання промптів для агентів

**System Prompt** - хто агент:
- Коротко і чітко
- Визначте роль і експертизу
- Приклад: "You are an expert requirements engineer with 10 years of experience in software projects."

**Instruction Text** - що робити:
- Детальні кроки
- Очікуваний формат виводу
- Граничні випадки
- Приклад: "Extract project details: 1) title, 2) budget, 3) deadline. If budget is missing, estimate based on complexity. Output as JSON."

### Версіонування

- Кожна зміна інструкцій збільшує версію
- Зберігайте старі версії для rollback (manually in DB)
- Тестуйте нові версії перед активацією

### Моніторинг

Регулярно перевіряйте:
- `/admin/logs` - чи агенти працюють правильно
- `tokens_used` - витрати на API
- `execution_time_ms` - швидкість виконання

### Безпека

- Не додавайте конфіденційну інформацію в промпти
- Використовуйте environment variables для секретів
- Деактивуйте агенти, які не використовуються

## Troubleshooting

**Агент не відповідає:**
1. Перевірте `/admin/logs` на помилки
2. Переконайтесь, що агент активний (`is_active = true`)
3. Перевірте OpenAI API key і ліміти

**Помилка при збереженні агента:**
- Agent name повинен бути унікальним
- Всі обов'язкові поля заповнені
- Перевірте підключення до БД

**Агент працює повільно:**
- Перевірте `execution_time_ms` в логах
- Зменште `max_tokens` в конфігурації
- Спростіть інструкції
