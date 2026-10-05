from pymongo import MongoClient
import json
from collections import defaultdict

DB = MongoClient('mongodb://localhost:27017')['immoinsight']
collections = ['clean_vente', 'clean_estival']
clusters = defaultdict(list)

for coll in collections:
    for d in DB[coll].find({'lat': {'$exists': True}, 'lon': {'$exists': True}}, {'_id':1,'titre':1,'url':1,'ville':1,'gouvernorat':1,'lat':1,'lon':1}):
        try:
            lat = round(float(d['lat']), 6)
            lon = round(float(d['lon']), 6)
        except Exception:
            continue
        key = f"{lat},{lon}"
        clusters[key].append({'collection': coll, 'id': str(d['_id']), 'titre': d.get('titre'), 'url': d.get('url'), 'ville': d.get('ville'), 'gouvernorat': d.get('gouvernorat')})

# keep only groups with more than one listing
dup_clusters = []
for coord, items in clusters.items():
    if len(items) > 1:
        lat, lon = coord.split(',')
        dup_clusters.append({
            'coord': {'lat': float(lat), 'lon': float(lon)},
            'count': len(items),
            'examples': items[:6]
        })

# sort by count desc
dup_clusters.sort(key=lambda x: x['count'], reverse=True)

out_path = 'reports/duplicate_coords.json'
import os
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(dup_clusters, f, ensure_ascii=False, indent=2)

print('report_saved', out_path)
print('clusters_found', len(dup_clusters))
if dup_clusters:
    print('top_cluster_count', dup_clusters[0]['count'])
    print('top_cluster_coord', dup_clusters[0]['coord'])
    print('sample_example', dup_clusters[0]['examples'][0])
else:
    print('no duplicates')
