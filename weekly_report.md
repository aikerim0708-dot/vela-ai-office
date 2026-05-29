# 📅 VELA Weekly · неделя {{week_label}} ({{week_start}} — {{week_end}})

Обновлено {{generated_at}}

---

## 💰 ИТОГИ НЕДЕЛИ

### Сводный P&L

| Метрика | Значение | vs прошлая неделя |
|---|---|---|
| **Чистая прибыль** | {{net_profit}} ₸ | {{profit_delta}} |
| **Выручка** | {{revenue}} ₸ | {{revenue_delta}} |
| **Заказов** | {{orders_total}} | {{orders_delta}} |
| **Удержания WB** | {{wb_retentions}} ₸ ({{retentions_pct}}%) | {{retentions_delta}} |
| **Реклама** | {{ads_costs}} ₸ ({{ads_pct}}%) | {{ads_delta}} |
| **Себестоимость** | {{cogs}} ₸ ({{cogs_pct}}%) | — |
| **УСН 6%** | {{tax}} ₸ | — |

### По товарам

| Товар | Заказов | Выручка | Чистая прибыль | Маржа % | Норма |
|---|---|---|---|---|---|
| 🪒 Бритва | {{razors_orders_week}} | {{razors_revenue_week}} ₸ | {{razors_profit_week}} ₸ | {{razors_margin_week}}% | ≥35% {{razors_margin_status}} |
| 👁 Ресницы | {{lashes_orders_week}} | {{lashes_revenue_week}} ₸ | {{lashes_profit_week}} ₸ | {{lashes_margin_week}}% | ≥40% {{lashes_margin_status}} |

---

## 📊 ТРЕНДЫ ЗА НЕДЕЛЮ

### Бритва — динамика день-к-дню

| Дата | Заказы | Затраты | ДРР | Прибыль |
|---|---|---|---|---|
{{#razors_daily}}
| {{date}} | {{orders}} | {{costs}} | {{drr}}% | {{profit}} |
{{/razors_daily}}

### Ресницы — динамика день-к-дню

| Дата | Заказы | Затраты | ДРР | Прибыль |
|---|---|---|---|---|
{{#lashes_daily}}
| {{date}} | {{orders}} | {{costs}} | {{drr}}% | {{profit}} |
{{/lashes_daily}}

---

## 🎯 ГЛАВНЫЕ СОБЫТИЯ НЕДЕЛИ

{{#weekly_events}}
### {{emoji}} {{title}}
{{description}}

{{/weekly_events}}

---

## 🧪 ГИПОТЕЗЫ — что тестировали

{{#weekly_hypotheses}}
### {{hypothesis_title}}

- **Метрика:** {{metric}}
- **Срок:** {{deadline}}
- **Критерий успеха:** {{success_criteria}}
- **Результат:** {{outcome}}
- **Что делаем дальше:** {{next_action}}

{{/weekly_hypotheses}}

---

## 🎯 ПЛАН НА СЛЕДУЮЩУЮ НЕДЕЛЮ

### Бритва
{{#next_week_razors}}
- {{action}} ({{rationale}})
{{/next_week_razors}}

### Ресницы
{{#next_week_lashes}}
- {{action}} ({{rationale}})
{{/next_week_lashes}}

### Общее
{{#next_week_general}}
- {{action}} ({{owner}})
{{/next_week_general}}

---

## 🏭 ОСТАТКИ И ПОСТАВКИ

| SKU | Остаток | Дней до OOS | Статус | Действие |
|---|---|---|---|---|
{{#stock_summary}}
| {{sku_name}} | {{stock}} | {{days_to_oos}} | {{status}} | {{action}} |
{{/stock_summary}}

---

_Отчёт сводит Макс. Источник: WB API (sales, fullstats, reportDetailByPeriod) + Brain VELA._
