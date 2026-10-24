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
        """Генерирует HTML-карту с серой подложкой Esri, Heatmap, филиалами и центроидами K-Means."""
        print("Запуск анализа K-Means...")
        df = self.analyzer.load_data()
        recommendations = self.analyzer.analyze_demand(df=df)

        # 1. Создаем базовую карту без дефолтного цветного слоя
        m = folium.Map(
            location=(56.32, 44.00),
            zoom_start=12,
            tiles=None,
        )

        # 2. Подключаем публичную серую подложку Esri World Gray Canvas (без API Key)
        esri_gray_url = (
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
        )
        esri_attribution = "Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ"

        folium.TileLayer(
            tiles=esri_gray_url,
            attr=esri_attribution,
            name="Esri World Gray Canvas",
            max_zoom=16,
            control=False,
        ).add_to(m)

        # 3. Наносим плавную тепловую карту (Heatmap) по координатам заказов
        try:
            heat_data = df[["client_lat", "client_lon"]].dropna().values.tolist()

            if heat_data:
                HeatMap(
                    data=heat_data,
                    name="Тепловая карта спроса",
                    radius=25,
                    blur=18,
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

        # 4. Отрисовываем действующие филиалы на карте
        for branch in self.analyzer.branches:
            folium.Marker(
                location=(branch["lat"], branch["lon"]),
                tooltip=(
                    f"<b>Действующий филиал:</b> {branch['name']}<br>"
                    f"Координаты: ({branch['lat']}, {branch['lon']})"
                ),
                icon=folium.Icon(color="darkblue", icon="cutlery", prefix="fa"),
            ).add_to(m)

        # 5. Наносим маркеры и точки центроидов K-Means поверх тепловой карты
        style_map = {
            "Открыть филиал": ("red", "#d62728", "plus-sign"),
            "Закрыть филиал": ("orange", "#ff7f0e", "warning-sign"),
            "Филиал рентабелен": ("green", "#2ca02c", "ok-sign"),
            "Спрос низкий": ("blue", "#1f77b4", "info-sign"),
        }

        for rec in recommendations:
            lat = rec["center_lat"]
            lon = rec["center_lon"]
            zone_id = rec["zone_id"]
            count = rec["order_count"]
            rec_text = rec["recommendation"]
            nearest_name = rec.get("nearest_branch_name") or "Нет"
            dist_km = rec.get("distance_to_branch_km")
            dist_str = f"{dist_km} км" if dist_km is not None else "—"

            marker_color, hex_color, icon_name = style_map.get(
                rec_text, ("blue", "#1f77b4", "info-sign")
            )

            tooltip_html = (
                f"<b>Зона ID: {zone_id}</b><br>"
                f"Количество заказов: <b>{count}</b><br>"
                f"Ближайший филиал: {nearest_name} ({dist_str})<br>"
                f"Рекомендация: <b>{rec_text}</b>"
            )

            # Точка с белой обводкой в точных координатах центроида
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

        # 6. Сохраняем результат в папку data
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