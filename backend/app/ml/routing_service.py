import networkx as nx
import osmnx as ox
import folium
import os
import pickle

class RoutingService:
    def __init__(self):
        self.branches = {
            1: {"name": "Филиал Нижегородский", "lat": 56.322974, "lon": 44.034741, "queue": 5},
            2: {"name": "Филиал Автозавод", "lat": 56.241094, "lon": 43.861618, "queue": 1},
            3: {"name": "Филиал Сормово", "lat": 56.364246, "lon": 43.816756, "queue": 4}
        }
        self.graph = self._load_or_download_graph()

    def _load_or_download_graph(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        graph_path = os.path.join(data_dir, "nn_graph.pkl")

        if os.path.exists(graph_path):
            print("Загрузка графа из кэша...")
            with open(graph_path, 'rb') as f:
                return pickle.load(f)
        else:
            print("Скачивание графа дорог Нижнего Новгорода (это займет пару минут)...")
            G = ox.graph_from_point((56.32, 44.00), dist=15000, network_type="drive")
            G = ox.add_edge_speeds(G)
            G = ox.add_edge_travel_times(G)
            
            with open(graph_path, 'wb') as f:
                pickle.dump(G, f)
            return G

    def get_driver_recommendation(self, driver_lat, driver_lon):
        driver_node = ox.distance.nearest_nodes(self.graph, X=driver_lon, Y=driver_lat)
        best_branch = None
        best_score = float('inf')
        
        for branch_id, info in self.branches.items():
            branch_node = ox.distance.nearest_nodes(self.graph, X=info["lon"], Y=info["lat"])
            
            try:
                travel_time = nx.shortest_path_length(self.graph, source=driver_node, target=branch_node, weight='travel_time')
                travel_time_min = travel_time / 60 
                score = travel_time_min - (info["queue"] * 2)
                
                if score < best_score:
                    best_score = score
                    best_branch = {
                        "branch_id": branch_id,
                        "branch_name": info["name"],
                        "travel_time_minutes": round(travel_time_min, 1),
                        "queue_size": info["queue"],
                        "driver_node": driver_node,
                        "branch_node": branch_node
                    }
            except nx.NetworkXNoPath:
                continue
                
        return best_branch

    def generate_route_map(self, recommendation, output_filename="route_map.html"):
        """Генерирует HTML-карту с маршрутом"""
        if not recommendation:
            return None

        driver_node = recommendation["driver_node"]
        branch_node = recommendation["branch_node"]
        
        route_nodes = nx.shortest_path(self.graph, source=driver_node, target=branch_node, weight='travel_time')
        
        route_coords = [(self.graph.nodes[node]['y'], self.graph.nodes[node]['x']) for node in route_nodes]
        driver_coords = (self.graph.nodes[driver_node]['y'], self.graph.nodes[driver_node]['x'])
        branch_coords = (self.graph.nodes[branch_node]['y'], self.graph.nodes[branch_node]['x'])

        m = folium.Map(location=driver_coords, zoom_start=12, tiles="Esri.WorldGrayCanvas")

        # Отрисовка всех дорог
        try:
            edges_gdf = ox.graph_to_gdfs(self.graph, nodes=False)
            edges_gdf.explore(
                m=m,
                color="#cccccc",
                weight=0.5,
                opacity=0.5,
                legend=False,
            )
        except Exception as e:
            print(f"Не удалось отрисовать фоновые дороги: {e}")

        # Линия маршрута
        folium.PolyLine(
            route_coords, 
            color="#d62728",
            weight=4, 
            opacity=0.9,
            tooltip=f"Маршрут ({recommendation['travel_time_minutes']} мин)"
        ).add_to(m)

        for branch_id, info in self.branches.items():
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

        # Маркер водителя
        folium.Marker(
            location=driver_coords, 
            tooltip="Водитель", 
            icon=folium.Icon(color="green", icon="flag")
        ).add_to(m)

        # Маркер филиала
        folium.Marker(
            location=branch_coords, 
            tooltip=f"{recommendation['branch_name']} (Очередь: {recommendation['queue_size']})", 
            icon=folium.Icon(color="red", icon="cutlery", prefix='fa')
        ).add_to(m)

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        
        file_path = os.path.join(data_dir, output_filename)
        m.save(file_path)
        
        return file_path

if __name__ == "__main__":
    print("Инициализация сервиса маршрутизации...")
    router = RoutingService()
    
    test_driver_lat = 56.3270 
    test_driver_lon = 44.0020
    
    print(f"Ищем рекомендацию для водителя на координатах ({test_driver_lat}, {test_driver_lon})...")
    rec = router.get_driver_recommendation(test_driver_lat, test_driver_lon)
    
    if rec:
        print("\n--- РЕКОМЕНДАЦИЯ ---")
        print(f"Ехать в: {rec['branch_name']}")
        print(f"Время в пути: {rec['travel_time_minutes']} мин.")
        print(f"Очередь в филиале: {rec['queue_size']} заказов")
        
        print("\nГенерация карты...")
        map_file = router.generate_route_map(rec)
        print(f"html файл успешно сохранен: {map_file}")
    else:
        print("Путь до филиалов не найден.")