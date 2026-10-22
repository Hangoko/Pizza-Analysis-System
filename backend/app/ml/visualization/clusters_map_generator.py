import sys
import os

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
if base_dir not in sys.path:
    sys.path.append(base_dir)

import folium
from backend.app.ml.services.kmeans_service import KMeansAnalyzer

class ClustersMapGenerator:
    def __init__(self, analyzer: KMeansAnalyzer):
        self.analyzer = analyzer

    def generate_clusters_map(self, output_filename="clusters_map.html"):
        """Генерирует HTML-карту с зонами спроса в виде пузырьков"""
        print("Запуск анализа K-Means...")
        
        # Получаем рекомендации (центры кластеров и количество заказов)
        recommendations = self.analyzer.analyze_demand()
        
        # Центрируем карту на Нижнем Новгороде
        m = folium.Map(location=(56.32, 44.00), zoom_start=12, tiles="Esri.WorldGrayCanvas")

        # 1. Отрисовка сырых данных (оранжевые точки) для фона
        try:
            df = self.analyzer.load_data()
            # Берем только 500 точек, чтобы карта не тормозила
            for _, row in df.head(500).iterrows():
                folium.CircleMarker(
                    location=(row['client_lat'], row['client_lon']),
                    radius=1.5,
                    color='orange',
                    fill=True,
                    fill_opacity=0.5
                ).add_to(m)
        except Exception as e:
            print(f"Не удалось отрисовать точки заказов: {e}")

        # 2. Отрисовка пузырьков (кластеров)
        for rec in recommendations:
            lat = rec["center_lat"]
            lon = rec["center_lon"]
            count = rec["order_count"]
            rec_text = rec["recommendation"]

            if rec_text == "Открыть филиал":
                color = "red"
                fill_color = "#ff0000"
            else:
                color = "blue"
                fill_color = "#0000ff"

            bubble_radius = max(10, count / 5) 

            folium.CircleMarker(
                location=(lat, lon),
                radius=bubble_radius,
                color=color,
                weight=2,
                fill=True,
                fill_color=fill_color,
                fill_opacity=0.4,
                tooltip=(
                    f"<b>Зона {rec['zone_id']}</b><br>"
                    f"Заказов: {count}<br>"
                    f"Рекомендация: <b>{rec_text}</b>"
                )
            ).add_to(m)

            folium.CircleMarker(
                location=(lat, lon),
                radius=3,
                color="black",
                fill=True,
                fill_color="black"
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
    
    print("Генерация карты кластеров...")
    map_file = map_gen.generate_clusters_map()
    print(f"HTML файл успешно сохранен: {map_file}")