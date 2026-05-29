# 💰 VELA Finance · {{month_human}} {{year}}

Полный финансовый разбор месяца. Ведёт Зара. Источники: WB sales + reportDetailByPeriod + cost-structure.md.

Обновлено {{generated_at}}

---

## 📊 P&L ЗА МЕСЯЦ

### Сводный отчёт

| Статья | Сумма ₸ | % от выручки |
|---|---|---|
| **Выручка (валовая)** | {{revenue}} | 100% |
| Себестоимость товаров | {{cogs}} | {{cogs_pct}}% |
| **Валовая прибыль** | {{gross_profit}} | {{gross_margin_pct}}% |
| | | |
| Удержания WB: комиссия | {{wb_commission}} | {{wb_commission_pct}}% |
| Удержания WB: логистика | {{wb_logistics}} | {{wb_logistics_pct}}% |
| Удержания WB: хранение | {{wb_storage}} | {{wb_storage_pct}}% |
| Удержания WB: возвраты | {{wb_returns}} | {{wb_returns_pct}}% |
| Удержания WB: эквайринг | {{wb_acquiring}} | {{wb_acquiring_pct}}% |
| Удержания WB: штрафы | {{wb_fines}} | {{wb_fines_pct}}% |
| **Всего удержано WB** | {{wb_total_retentions}} | {{wb_total_pct}}% |
| | | |
| Расход на рекламу | {{ads_costs}} | {{ads_pct}}% |
| УСН 6% от выручки | {{tax}} | 6% |
| | | |
| **Чистая прибыль** | **{{net_profit}}** | **{{net_margin_pct}}%** |

### По товарам

| Товар | Выручка | Себестоимость | Удержания | Реклама | УСН | **Чистая прибыль** | Маржа % | Норма |
|---|---|---|---|---|---|---|---|---|
| 🪒 Бритва | {{razors_revenue}} | {{razors_cogs}} | {{razors_retentions}} | {{razors_ads}} | {{razors_tax}} | **{{razors_net_profit}}** | {{razors_margin_pct}}% | ≥35% {{razors_status}} |
| 👁 Ресницы | {{lashes_revenue}} | {{lashes_cogs}} | {{lashes_retentions}} | {{lashes_ads}} | {{lashes_tax}} | **{{lashes_net_profit}}** | {{lashes_margin_pct}}% | ≥40% {{lashes_status}} |

---

## 📦 ЮНИТ-ЭКОНОМИКА

### Бритва

| Параметр | Значение |
|---|---|
| Розничная цена | {{razors_retail_price}} ₸ |
| Себестоимость (закупка + упак + маркировка) | {{razors_cogs_per_unit}} ₸ |
| Логистика до склада WB (на штуку) | {{razors_logistics_per_unit}} ₸ |
| Комиссия WB ({{wb_commission_rate_razors}}%) | {{razors_commission_per_unit}} ₸ |
| Логистика WB до покупателя (средняя) | {{razors_wb_logistics_per_unit}} ₸ |
| Хранение (на штуку, среднее за мес) | {{razors_storage_per_unit}} ₸ |
| Эквайринг | {{razors_acquiring_per_unit}} ₸ |
| Возвраты (вероятностные) | {{razors_returns_per_unit}} ₸ |
| Реклама на штуку (средневзвешенная) | {{razors_ads_per_unit}} ₸ |
| УСН 6% | {{razors_tax_per_unit}} ₸ |
| **Чистая прибыль на штуку** | **{{razors_profit_per_unit}}** ₸ |
| **Маржа на штуку** | **{{razors_unit_margin_pct}}%** |

### Ресницы

(аналогичная структура)

---

## 🔄 ТРЕНД 3 МЕСЯЦА

| Месяц | Выручка | Удержания % | Реклама % | Чистая прибыль | Маржа % |
|---|---|---|---|---|---|
| {{month_minus_2}} | {{m_minus_2_revenue}} | {{m_minus_2_retentions_pct}}% | {{m_minus_2_ads_pct}}% | {{m_minus_2_profit}} | {{m_minus_2_margin}}% |
| {{month_minus_1}} | {{m_minus_1_revenue}} | {{m_minus_1_retentions_pct}}% | {{m_minus_1_ads_pct}}% | {{m_minus_1_profit}} | {{m_minus_1_margin}}% |
| **{{month_current}}** | **{{revenue}}** | **{{wb_total_pct}}%** | **{{ads_pct}}%** | **{{net_profit}}** | **{{net_margin_pct}}%** |

---

## ⚠ ФИНАНСОВЫЕ АЛЕРТЫ ОТ ЗАРЫ

{{#alerts}}
### {{emoji}} {{title}}
{{description}}

**Что предлагаю:** {{proposal}}

{{/alerts}}

---

## 📈 ЦЕЛИ И ПРОГРЕСС

| Цель | План | Факт | % выполнения |
|---|---|---|---|
{{#finance_goals}}
| {{goal_name}} | {{plan}} | {{actual}} | {{progress_pct}}% |
{{/finance_goals}}

---

_Финансовый отчёт ведёт Зара. Согласован с Максом. Если цифры расходятся с твоим учётом — пиши в чат, разберём._
