import pandas as pd
import os
from sklearn.cluster import KMeans
import numpy as np

class KMeansAnalyzer:
    def __init__(self, n_clusters=5):
        # n_clusters - количество зон (кластеров), на которые мы разобьем город
        self.n_clusters = n_clusters
        self.model = KMeans(n_clusters=self.n_clusters, random_state=42, n_init=10)

    def load_data(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        file_path = os.path.join(base_dir, "data", "synthetic_orders.csv")
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Файл данных не найден: {file_path}")
            
        df = pd.read_csv(file_path)
        df = df[df['status'] == 'Delivered']
        return df

    def analyze_demand(self):
        df = self.load_data()
        
        coords = df[['client_lat', 'client_lon']].values
        
        self.model.fit(coords)
        
        centroids = self.model.cluster_centers_
        
        df['cluster'] = self.model.labels_
        cluster_counts = df['cluster'].value_counts().sort_index()
        
        recommendations = []
        for i, (lat, lon) in enumerate(centroids):
            recommendations.append({
                "zone_id": i,
                "center_lat": round(lat, 6),
                "center_lon": round(lon, 6),
                "order_count": int(cluster_counts[i]),
                "recommendation": "Открыть филиал" if cluster_counts[i] > 150 else "Спрос низкий"
            })
            
        return recommendations

if __name__ == "__main__":
    analyzer = KMeansAnalyzer(n_clusters=5)
    results = analyzer.analyze_demand()
    print("Результаты кластеризации (Топ зон спроса):")
    for res in results:
        print(res)