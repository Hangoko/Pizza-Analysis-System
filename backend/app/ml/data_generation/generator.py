import os
import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd


def generate_orders(num_orders=1000, seed=42):
    random.seed(seed)
    np.random.seed(seed)

    # Центры спроса:
    # Первые 5 совпадают с районами действующих филиалов,
    # а 2 зоны (Верхние Печеры и Мещерское озеро) находятся вдали от открытых филиалов
    demand_centers = [
        (56.322974, 44.034741),  # 1. Нижегородский (есть филиал, высокий спрос)
        (56.241094, 43.861618),  # 2. Автозавод (есть филиал, высокий спрос)
        (56.364246, 43.816756),  # 3. Сормово (есть филиал, средний спрос)
        (56.245525, 43.985747),  # 4. Приокский (есть филиал, НИЗКИЙ спрос -> кандидат на закрытие)
        (56.312834, 43.937238),  # 5. Канавинский (есть филиал, средний спрос)
        (56.346500, 43.945000),  # 6. Мещерское озеро (НЕТ филиала рядом, ВЫСОКИЙ спрос -> открыть)
        (56.298000, 44.075000),  # 7. Верхние Печеры (НЕТ филиала рядом, ВЫСОКИЙ спрос -> открыть)
    ]
    # Веса популярности зон спроса
    center_weights = [0.18, 0.17, 0.14, 0.04, 0.13, 0.17, 0.17]

    branches = [1, 2, 3, 4, 5, 6, 7]
    drivers = list(range(1, 21))
    statuses = ["Delivered", "Canceled"]
    data = []

    start_time = datetime(2026, 10, 1)

    for i in range(num_orders):
        center = random.choices(demand_centers, weights=center_weights, k=1)[0]
        client_lat = center[0] + random.uniform(-0.015, 0.015)
        client_lon = center[1] + random.uniform(-0.020, 0.020)

        branch_id = random.choice(branches)
        driver_id = random.choice(drivers)
        order_time = start_time + timedelta(minutes=random.randint(0, 43200))

        status = random.choices(statuses, weights=[0.9, 0.1], k=1)[0]
        delivery_time = random.randint(15, 60) if status == "Delivered" else None

        data.append(
            {
                "order_id": f"ORD-{i + 1:04d}",
                "client_lat": round(client_lat, 6),
                "client_lon": round(client_lon, 6),
                "branch_id": branch_id,
                "driver_id": driver_id,
                "order_time": order_time.strftime("%Y-%m-%d %H:%M:%S"),
                "delivery_time_minutes": delivery_time,
                "status": status,
            }
        )

    df = pd.DataFrame(data)

    base_dir = os.path.dirname(
        os.path.dirname(
            os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
        )
    )
    data_dir = os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)

    file_path = os.path.join(data_dir, "synthetic_orders.csv")
    df.to_csv(file_path, index=False)
    print(f"Сгенерировано {num_orders} заказов. Файл сохранен: {file_path}")


if __name__ == "__main__":
    generate_orders()