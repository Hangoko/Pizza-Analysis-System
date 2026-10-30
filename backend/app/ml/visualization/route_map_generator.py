
import os

import folium
import networkx as nx
import pandas as pd
from sqlalchemy.orm import Session

from backend.app.db.models.order import OrderStatus
from backend.app.ml.services.routing_service import RoutingService
from backend.app.repositories.order import OrderRepository

base_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")
)


class MapGenerator:
    def __init__(
        self,
        routing_service: RoutingService,
        session: Session | None = None,
    ):
        self.router = routing_service
        self.session = session or routing_service.session

    def _load_orders_df(self) -> pd.DataFrame | None:
        if self.session is not None:
            return OrderRepository(self.session).fetch_df(status=OrderStatus.DELIVERED)

        data_path = os.path.join(base_dir, "data", "synthetic_orders.csv")
        if os.path.exists(data_path):
            return pd.read_csv(data_path)
        return None

    @staticmethod
    def _extract_edge_lines(
        graph: nx.MultiDiGraph,
    ) -> list[list[tuple[float, float]]]:
        """Извлекает координаты рёбер графа для отрисовки через folium.PolyLine."""
        nodes = graph.nodes
        seen_pairs: set[tuple[object, object]] = set()
        edge_lines: list[list[tuple[float, float]]] = []

        for u, v, data in graph.edges(data=True):
            pair = (u, v) if str(u) <= str(v) else (v, u)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            geometry = data.get("geometry")
            if geometry is not None and hasattr(geometry, "coords"):
                line = [(float(lat), float(lon)) for lon, lat in geometry.coords]
            else:
                u_node, v_node = nodes[u], nodes[v]
                if "y" not in u_node or "x" not in u_node:
                    continue
                if "y" not in v_node or "x" not in v_node:
                    continue
                line = [
                    (float(u_node["y"]), float(u_node["x"])),
                    (float(v_node["y"]), float(v_node["x"])),
                ]
            edge_lines.append(line)

        return edge_lines

    def generate_route_map(self, recommendation, output_filename="route_map.html"):
        """Генерирует HTML-карту с маршрутом и всеми филиалами."""
        if not recommendation:
            return None

        graph = self.router.graph
        driver_node = recommendation["driver_node"]
        route_nodes = recommendation["route_nodes"]

        route_coords = [
            (graph.nodes[node]["y"], graph.nodes[node]["x"])
            for node in route_nodes
        ]
        driver_coords = (
            graph.nodes[driver_node]["y"],
            graph.nodes[driver_node]["x"],
        )

        # Создаем карту (центр на водителе) с серой подложкой Esri без API Key
        m = folium.Map(location=driver_coords, zoom_start=12, tiles=None)
        esri_gray_url = (
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
        )
        folium.TileLayer(
            tiles=esri_gray_url,
            attr="Tiles © Esri — Esri, DeLorme, NAVTEQ",
            name="Esri World Gray Canvas",
            max_zoom=16,
            control=False,
        ).add_to(m)

        # 1. Отрисовка всех дорог (серый фон через единый folium.PolyLine без explore)
        try:
            edge_lines = self._extract_edge_lines(graph)
            if edge_lines:
                folium.PolyLine(
                    locations=edge_lines,
                    color="#cccccc",
                    weight=0.7,
                    opacity=0.5,
                ).add_to(m)
        except Exception as e:
            print(f"Не удалось отрисовать фоновые дороги: {e}")

        # 2. Отрисовка точек заказов (из БД или CSV)
        try:
            df = self._load_orders_df()
            if df is not None and not df.empty:
                for _, row in df.head(300).iterrows():
                    folium.CircleMarker(
                        location=(row["client_lat"], row["client_lon"]),
                        radius=2,
                        color="orange",
                        fill=True,
                        fill_opacity=0.6,
                        tooltip=f"Заказ: {row['order_id']}",
                    ).add_to(m)
                print(f"  Отрисовано заказов: {min(300, len(df))}")
            else:
                print("  Данные о заказах не найдены.")
        except Exception as e:
            print(f"Не удалось загрузить заказы: {e}")

        # 3. Линия маршрута
        folium.PolyLine(
            route_coords,
            color="#d62728",
            weight=5,
            opacity=0.9,
            tooltip=f"Маршрут ({recommendation['travel_time_minutes']} мин)",
        ).add_to(m)

        # 4. Отрисовка ВСЕХ филиалов
        for branch_id, info in self.router.branches.items():
            is_recommended = branch_id == recommendation["branch_id"]

            if is_recommended:
                color = "red"
                icon_name = "cutlery"
                tooltip_text = (
                    f"РЕКОМЕНДОВАНО: {info['name']} (Очередь: {info['queue']})"
                )
            else:
                color = "blue"
                icon_name = "home"
                tooltip_text = f"{info['name']} (Очередь: {info['queue']})"

            folium.Marker(
                location=(info["lat"], info["lon"]),
                tooltip=tooltip_text,
                icon=folium.Icon(color=color, icon=icon_name, prefix="fa"),
            ).add_to(m)

        # 5. Маркер водителя
        folium.Marker(
            location=driver_coords,
            tooltip="Водитель",
            icon=folium.Icon(color="green", icon="flag"),
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
