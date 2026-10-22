import pandas as pd
import numpy as np
import random
import os
from datetime import datetime, timedelta

def generate_orders(num_orders=1000):
    # Примерные центры: Нижегородский, Автозавод, Сормово, Приокский, Московский, Канавинский, Советский районы
    city_centers = [
        (56.322974, 44.034741),
        (56.241094, 43.861618),
        (56.364246, 43.816756),
        (56.245525, 43.985747),
        (56.326492, 43.871275),
        (56.312834, 43.937238),
        (56.293337, 44.013856),

    ]
    
    branches = [1, 2, 3, 4, 5] 
    drivers = list(range(1, 21)) 
    statuses = ["Delivered", "Canceled"]
    data = []
    
    start_time = datetime(2026, 10, 1)
    
    for i in range(num_orders):
        center = random.choice(city_centers)
        client_lat = center[0] + random.uniform(-0.03, 0.03)
        client_lon = center[1] + random.uniform(-0.05, 0.05)
        
        branch_id = random.choice(branches)
        driver_id = random.choice(drivers)
        order_time = start_time + timedelta(minutes=random.randint(0, 43200))
        
        status = random.choices(statuses, weights=[0.9, 0.1], k=1)[0]
        delivery_time = random.randint(15, 60) if status == "Delivered" else None
        
        data.append({
            "order_id": f"ORD-{i+1:04d}",
            "client_lat": round(client_lat, 6),
            "client_lon": round(client_lon, 6),
            "branch_id": branch_id,
            "driver_id": driver_id,
            "order_time": order_time.strftime("%Y-%m-%d %H:%M:%S"),
            "delivery_time_minutes": delivery_time,
            "status": status
        })
        
    df = pd.DataFrame(data)
    
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    data_dir = os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    
    file_path = os.path.join(data_dir, "synthetic_orders.csv")
    df.to_csv(file_path, index=False)
    print(f"Сгенерировано {num_orders} заказов для Нижнего Новгорода. Файл сохранен: {file_path}")

if __name__ == "__main__":
    generate_orders()