import sys
import os

# Определяем корень проекта (выносим наверх, чтобы использовать в разных местах)
base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
if base_dir not in sys.path:
    sys.path.append(base_dir)

import folium
import osmnx as ox
import pandas as pd

from backend.app.ml.services.routing_service import RoutingService

class MapGenerator:
    def __init__(self, routing_service: RoutingService):
        # Мы передаем сюда созданный сервис маршрутизации, чтобы иметь доступ к графу и филиалам
        self.router = routing_service

    def generate_route_map(self, recommendation, output_filename="route_map.html"):
        """Генерирует HTML-карту с маршрутом и всеми филиалами"""
        if not recommendation:
            return None

        graph = self.router.graph
        driver_node = recommendation["driver_node"]
        route_nodes = recommendation["route_nodes"]
        
        route_coords = [(graph.nodes[node]['y'], graph.nodes[node]['x']) for node in route_nodes]
        driver_coords = (graph.nodes[driver_node]['y'], graph.nodes[driver_node]['x'])

        # Создаем карту (центр на водителе)
        m = folium.Map(location=driver_coords, zoom_start=12, tiles="Esri.WorldGrayCanvas")

        # 1. Отрисовка всех дорог (серый фон)
        try:
            edges_gdf = ox.graph_to_gdfs(graph, nodes=False)
            edges_gdf.explore(m=m, color="#cccccc", weight=0.5, opacity=0.5, legend=False)
        except Exception as e:
            print(f"Не удалось отрисовать фоновые дороги: {e}")

        try:
            data_path = os.path.join(base_dir, "data", "synthetic_orders.csv")
            if os.path.exists(data_path):
                df = pd.read_csv(data_path)
                # Берем первые 300 заказов, чтобы карта не тормозила
                for _, row in df.head(300).iterrows():
                    folium.CircleMarker(
                        location=(row['client_lat'], row['client_lon']),
                        radius=2,
                        color='orange',
                        fill=True,
                        fill_opacity=0.6,
                        tooltip=f"Заказ: {row['order_id']}"
                    ).add_to(m)
                print(f"  Отрисовано заказов: 300")
            else:
                print("  CSV файл с заказами не найден.")
        except Exception as e:
            print(f"Не удалось загрузить заказы: {e}")
        # =========================================================


        # 3. Линия маршрута (рисуем ПОВЕРХ заказов, чтобы не перекрывать)
        folium.PolyLine(
            route_coords, 
            color="#d62728",
            weight=5, 
            opacity=0.9,
            tooltip=f"Маршрут ({recommendation['travel_time_minutes']} мин)"
        ).add_to(m)

        # 4. Отрисовка ВСЕХ филиалов (цикл)
        for branch_id, info in self.router.branches.items():
            is_recommended = (branch_id == recommendation["branch_id"])
            
            if is_recommended:
                color = "red"
                icon_name = "cutlery"
                tooltip_text = f"РЕКОМЕНДОВАНО: {info['name']} (Очередь: {info['queue']})"
            else:
                color = "blue"
                icon_name = "home"
                tooltip_text = f"{info['name']} (Очередь: {info['queue']})"

            folium.Marker(
                location=(info["lat"], info["lon"]), 
                tooltip=tooltip_text, 
                icon=folium.Icon(color=color, icon=icon_name, prefix='fa')
            ).add_to(m)

        # 5. Маркер водителя
        folium.Marker(
            location=driver_coords, 
            tooltip="Водитель", 
            icon=folium.Icon(color="green", icon="flag")
        ).add_to(m)

        # Сохранение файла
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        
        file_path = os.path.join(data_dir, output_filename)
        m.save(file_path)
        
        return file_path

if __name__ == "__main__":
    print("Инициализация...")
    router = RoutingService()
    map_gen = MapGenerator(router)
    
    test_lat, test_lon = 56.3270, 44.0020
    print(f"Ищем рекомендацию для водителя ({test_lat}, {test_lon})...")
    
    rec = router.get_driver_recommendation(test_lat, test_lon)
    
    if rec:
        print("\n--- РЕКОМЕНДАЦИЯ ---")
        print(f"Ехать в: {rec['branch_name']}")
        print(f"Время в пути: {rec['travel_time_minutes']} мин.")
        
        print("\nГенерация карты...")
        map_file = map_gen.generate_route_map(rec)
        print(f"HTML файл успешно сохранен: {map_file}")
    else:
        print("Путь не найден.")