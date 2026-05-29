# 🧠 VELA Daily · {{date_human}} ({{weekday}}) | {{prev_date_human}} ✓ полный день
{{header_unitka}}

Обновлено {{generated_at}}

---

## 🧾 Актуальный день · {{date_human}} ✓ {{data_quality}}

### Сводный KPI

| Метрика | Значение | Дельта |
|---|---|---|
| **Прибыль {{prev_date_human}}** | {{profit_value}} | {{profit_delta_emoji}} {{profit_components}} |
| **Заказов WB** | {{orders_total}} | бритва {{orders_razors}} · ресницы {{orders_lashes}} |
| **Затраты** | {{costs_total}} | бритва {{costs_razors}} · ресницы {{costs_lashes}} |
| **ДРР бритва** | {{drr_razors}}% | БУ {{bu_razors}}% {{drr_razors_status}} · ресницы {{drr_lashes}}% {{drr_lashes_status}} |

### 🪒 Бритва (29230612) {{razors_status_label}}

| Заказов | Затраты | CPS | ДРР | Прибыль |
|---|---|---|---|---|
| **{{razors_orders}}** ({{razors_orders_rk}} РК + {{razors_orders_org}} орг) | **{{razors_costs}}** ({{razors_costs_rub}} × {{usd_rate}}) | **{{razors_cps}}** ({{razors_cps_rub}} × {{usd_rate}}) | **{{razors_drr}}%** БУ {{bu_razors}}% {{razors_drr_delta}} | **{{razors_profit}}** ({{razors_orders}} × {{razors_unit_profit}}) |

### 👁 Ресницы (32284868) {{lashes_status_label}}

| Заказов | Затраты | CPS | ДРР | Прибыль |
|---|---|---|---|---|
| **{{lashes_orders}}** ({{lashes_orders_rk}} РК + {{lashes_orders_org}} орг) | **{{lashes_costs}}** ({{lashes_costs_rub}} × {{usd_rate}}) | **{{lashes_cps}}** ({{lashes_cps_rub}} × {{usd_rate}}) | **{{lashes_drr}}%** БУ {{bu_lashes}}% {{lashes_drr_delta}} | **{{lashes_profit}}** ({{lashes_orders}} × {{lashes_unit_profit}}) |

---

## 🪒 БРИТВА · СТАТИСТИКА {{date_human}}

### 📊 РК по зонам

| Зона | % | Показы | Клики | CTR% | CPM ₽ | Затраты ₽ | Корзин | Зак РК | СРО ₽ | CRO% | ДРР% | Статус |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Итого ✓ | 100% | {{razors_views}} | {{razors_clicks}} | {{razors_ctr}}% | {{razors_cpm}} | {{razors_costs_rub}} | {{razors_carts}} | {{razors_orders_rk}} | {{razors_cpo}} | {{razors_cro}}% | {{razors_drr}}% | {{razors_status}} |
| 🔍 Поиск | {{razors_search_pct}}% | {{razors_search_views}} | {{razors_search_clicks}} | {{razors_search_ctr}}% | {{razors_search_cpm}} | {{razors_search_costs}} | {{razors_search_carts}} | {{razors_search_orders}} | {{razors_search_cpo}} | {{razors_search_cro}}% | {{razors_search_drr}}% | {{razors_search_status}} |
| 📦 Полки | {{razors_shelf_pct}}% | {{razors_shelf_views}} | {{razors_shelf_clicks}} | {{razors_shelf_ctr}}% | {{razors_shelf_cpm}} | {{razors_shelf_costs}} | {{razors_shelf_carts}} | {{razors_shelf_orders}} | {{razors_shelf_cpo}} | {{razors_shelf_cro}}% | {{razors_shelf_drr}}% | {{razors_shelf_status}} |
| 📚 Каталог | {{razors_catalog_pct}}% | {{razors_catalog_views}} | {{razors_catalog_clicks}} | {{razors_catalog_ctr}}% | {{razors_catalog_cpm}} | {{razors_catalog_costs}} | — | — | — | — | — | — |

{{razors_zones_comment}}

### 📦 Всего по товару (реклама + органика)

| Просмотры | Переходы | Корзин | Заказов | В заказах ₸ | Сред. цена ₸ | CPS ₽ | CPS ₸ | Чистая прибыль ₸/шт |
|---|---|---|---|---|---|---|---|---|
| {{razors_views_total}} | {{razors_clicks_total}} | {{razors_carts_total}} | **{{razors_orders}}** | {{razors_revenue}} ₸ | {{razors_avg_price}} ₸ | {{razors_cps_rub}} ₽ | **{{razors_cps_kzt}}** ₸ | **+{{razors_unit_profit}}** ₸ |

{{razors_cps_comment}}

### 🧱 КЛАСТЕРЫ БРИТВЫ ({{razors_clusters_count}} управляемых)

| Кластер | Частота | CPM ₽ | Ср.поз | Позиция | BT% | Показы | Клики | CTR% | CPC ₽ | Затраты ₽ | Корз РК | CPL РК | Зак РК | СРО РК ₽ | CRO% | ДРРз РК% |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
{{#razors_clusters}}
| {{name}} | {{frequency}} | {{cpm}} | {{avg_pos}} | {{position_status}} | {{bt_pct}}% | {{views}} | {{clicks}} | {{ctr}}% | {{cpc}} | {{costs}} | {{carts_rk}} | {{cpl_rk}} | {{orders_rk}} | {{cpo_rk}} | {{cro}}% | {{drrz_rk}}% |
{{/razors_clusters}}
| **ИТОГО ({{razors_clusters_count}}, актив {{razors_clusters_active}})** | {{razors_clusters_freq_total}} | {{razors_clusters_cpm_avg}} | — | — | {{razors_clusters_bt_avg}}% | {{razors_clusters_views_total}} | {{razors_clusters_clicks_total}} | {{razors_clusters_ctr_avg}}% | {{razors_clusters_cpc_avg}} | {{razors_clusters_costs_total}} | {{razors_clusters_carts_total}} | {{razors_clusters_cpl_avg}} | {{razors_clusters_orders_total}} | {{razors_clusters_cpo_avg}} | {{razors_clusters_cro_avg}}% | {{razors_clusters_drrz_avg}}% |

### 🎯 Воронка CTR

**{{razors_ctr_rk}}% CTR РК** vs **{{razors_ctr_total}}% CTR общий** — {{razors_funnel_verdict}}

---

## 👁 РЕСНИЦЫ · СТАТИСТИКА {{date_human}}

(аналогичная структура — таблицы РК по зонам, всего по товару, кластеры, воронка)

---

## ⚠ АНОМАЛИИ {{date_short}}

{{#anomalies}}
### {{emoji}} {{title}}
{{description}}

{{/anomalies}}

---

## 🚀 ПРОРЫВЫ {{date_short}}

{{#breakthroughs}}
### {{emoji}} {{title}}
{{description}}
{{badges}}

{{/breakthroughs}}

---

## 🎯 РЕКОМЕНДАЦИИ НА {{next_date_human}} ({{next_weekday}})

{{#recommendations}}
### {{priority_emoji}} #{{number}}: {{title}}

{{rationale}}

**Прогноз эффекта:** {{forecast}}

{{/recommendations}}

---

## 👤 ПОРТРЕТ ПОКУПАТЕЛЯ (ПО ЗОНАМ)

{{portrait_status}}

{{portrait_data_or_manual_note}}

---

## 📅 История по товарам · Гипотезы {{month_human}}

<details>
<summary>Развернуть</summary>

{{hypotheses_md}}

</details>

---

## 📦 Кластеры · история {{month_human}}

<details>
<summary>Развернуть</summary>

{{clusters_history_md}}

</details>

---

_Отчёт автогенерирован VELA Office. Источник данных: WB API. Автор аналитики: команда агентов (Лео, Анна, Зара, Ева, Макс). Если что-то не сходится — пиши в общий чат, исправим._
