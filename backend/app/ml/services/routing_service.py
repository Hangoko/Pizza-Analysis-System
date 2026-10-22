import networkx as nx
import osmnx as ox
import os
import pickle

class RoutingService:
    def __init__(self):
        self.branches = {
            1: {"name": "Филиал Нижегородский", "lat": 56.322974, "lon": 44.034741, "queue": 5},
            2: {"name": "Филиал Автозавод", "lat": 56.241094, "lon": 43.861618, "queue": 1},
            3: {"name": "Филиал Сормово", "lat": 56.364246, "lon": 43.816756, "queue": 4},
            4: {"name": "Филиал Приокский", "lat": 56.245525, "lon": 43.985747, "queue": 2},
            5: {"name": "Филиал Московский", "lat": 56.326492, "lon": 43.871275, "queue": 3},
            6: {"name": "Филиал Канавинский", "lat": 56.312834, "lon": 43.937238, "queue": 6},
            7: {"name": "Филиал Советский", "lat": 56.293337, "lon": 44.013856, "queue": 0}
        }
        self.graph = self._load_or_download_graph()

    def _load_or_download_graph(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
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
                        "branch_node": branch_node,
                        "route_nodes": nx.shortest_path(self.graph, source=driver_node, target=branch_node, weight='travel_time')
                    }
            except nx.NetworkXNoPath:
                continue
                
        return best_branch