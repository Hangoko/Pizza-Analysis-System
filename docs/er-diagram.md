# Схема БД (ER-диаграмма)

СУБД — PostgreSQL 16 (в тестах — SQLite). Схема описана ORM-моделями
`backend/app/db/models/` и создаётся миграциями Alembic (`backend/alembic/versions/`).

```mermaid
erDiagram
    users ||--o| drivers : "учётная запись"
    users ||--o{ report_templates : "владелец"
    branches ||--o{ drivers : "закреплён"
    branches ||--o{ orders : "принял"
    drivers ||--o{ orders : "доставил"

    users {
        int id PK
        string username UK
        string email UK "NULL"
        string full_name "NULL"
        string password_hash
        string role "admin | manager | executive | driver"
        bool is_active
        timestamptz created_at
        timestamptz updated_at
    }

    branches {
        int id PK
        string name UK
        float lat
        float lon
        int current_queue "очередь заказов, >= 0"
        bool is_active
        timestamptz created_at
    }

    drivers {
        int id PK
        string full_name
        string phone "NULL"
        int branch_id FK "NULL, SET NULL"
        int user_id FK,UK "NULL, SET NULL"
        bool is_active
        timestamptz created_at
    }

    orders {
        int id PK
        string external_id UK "ORD-0001"
        float client_lat
        float client_lon
        int branch_id FK "RESTRICT"
        int driver_id FK "NULL, SET NULL"
        timestamptz order_time
        timestamptz delivered_at "NULL"
        int delivery_time_minutes "NULL, >= 0"
        string status "Pending | InDelivery | Delivered | Canceled"
        timestamptz created_at
    }

    report_templates {
        int id PK
        string name "UK вместе с owner_id"
        text description "NULL"
        bool is_system
        int owner_id FK "NULL = системный, CASCADE"
        json config
        timestamptz created_at
        timestamptz updated_at
    }
```

## Ограничения и индексы

| Таблица | Ограничения | Индексы |
|---|---|---|
| `users` | `uq_users_username`, `uq_users_email`, `ck_users_role` | — |
| `branches` | `uq_branches_name`, `ck_branches_current_queue_non_negative` | — |
| `drivers` | `uq_drivers_user_id` | `ix_drivers_branch_id` |
| `orders` | `uq_orders_external_id`, `ck_orders_status`, `ck_orders_delivery_time_non_negative` | `ix_orders_order_time`, `ix_orders_branch_id_order_time`, `ix_orders_status`, `ix_orders_driver_id` |
| `report_templates` | `uq_report_templates_owner_id_name` | — |

Роли и статусы хранятся строками с `CHECK`-ограничением (а не нативным enum PostgreSQL),
`config` — переносимый `JSON`: так схема одинаково работает на PostgreSQL и SQLite.
Все даты — `timestamptz`, приложение работает с ними в UTC.
