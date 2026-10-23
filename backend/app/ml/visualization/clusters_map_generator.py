import os
import sys

# Настройка путей для корректного импорта модулей проекта из папки visualization
base_dir = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
    )
)
if base_dir not in sys.path:
    sys.path.append(base_dir)

import folium
from folium.plugins import HeatMap
from backend.app.ml.services.kmeans_service import KMeansAnalyzer


class ClustersMapGenerator:
    def __init__(self, analyzer: KMeansAnalyzer):
        self.analyzer = analyzer

    def generate_clusters_map(self, output_filename="clusters_map.html"):
        """Генерирует HTML-карту с плавной тепловой картой (Heatmap) и центроидами K-Means."""
        print("Запуск анализа K-Means...")
        recommendations = self.analyzer.analyze_demand()

        # Базовая карта
        m = folium.Map(
            location=(56.32, 44.00),
            zoom_start=12,
            tiles="Esri.WorldGrayCanvas"
        )

        try:
            df = self.analyzer.load_data()
            heat_data = df[["client_lat", "client_lon"]].dropna().values.tolist()

            if heat_data:
                HeatMap(
                    data=heat_data,
                    name="Тепловая карта спроса",
                    radius=25,       # Радиус влияния точки для слияния в единое облако
                    blur=18,         # Степень размытия границ для плавного градиента
                    min_opacity=0.35,
                    max_zoom=13,
                    gradient={
                        0.2: "blue",
                        0.45: "cyan",
                        0.65: "lime",
                        0.85: "yellow",
                        1.0: "red",
                    },
                ).add_to(m)
                print(f"Тепловая карта построена по {len(heat_data)} заказам.")
        except Exception as e:
            print(f"Не удалось построить тепловую карту заказов: {e}")

        # Маркеры и точки центроидов поверх тепловой карты
        for rec in recommendations:
            lat = rec["center_lat"]
            lon = rec["center_lon"]
            zone_id = rec["zone_id"]
            count = rec["order_count"]
            rec_text = rec["recommendation"]

            is_recommended = (rec_text == "Открыть филиал")
            marker_color = "red" if is_recommended else "blue"
            hex_color = "#d62728" if is_recommended else "#1f77b4"
            icon_name = "plus-sign" if is_recommended else "info-sign"

            tooltip_html = (
                f"<b>Зона ID: {zone_id}</b><br>"
                f"Количество заказов: <b>{count}</b><br>"
                f"Статус: <b>{rec_text}</b>"
            )

            # Точка с белой обводкой в точных координатах центроида (чтобы не сливалась с фоном Heatmap)
            folium.CircleMarker(
                location=(lat, lon),
                radius=8,
                color="#ffffff",
                weight=2,
                fill=True,
                fill_color=hex_color,
                fill_opacity=1.0,
                tooltip=tooltip_html,
            ).add_to(m)

            # Иконка-маркер центроида поверх точки
            folium.Marker(
                location=(lat, lon),
                tooltip=tooltip_html,
                icon=folium.Icon(color=marker_color, icon=icon_name),
            ).add_to(m)

        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)

        file_path = os.path.join(data_dir, output_filename)
        m.save(file_path)

        return file_path


if __name__ == "__main__":
    print("Инициализация K-Means...")
    analyzer = KMeansAnalyzer(n_clusters=7)
    map_gen = ClustersMapGenerator(analyzer)

    print("Генерация тепловой карты кластеров...")
    map_file = map_gen.generate_clusters_map()
    print(f"HTML файл успешно сохранен: {map_file}")