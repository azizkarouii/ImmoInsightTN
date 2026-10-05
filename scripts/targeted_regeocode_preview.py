import json
from pymongo import MongoClient
from bson import ObjectId
from etl.geocoder import geocode_address, _infer_location_candidates

DB = MongoClient('mongodb://localhost:27017')['immoinsight']

with open('reports/duplicate_coords.json', 'r', encoding='utf-8') as f:
    clusters = json.load(f)

preview = []

for cluster in clusters:
    for ex in cluster['examples']:
        coll = ex['collection']
        doc_id = ex['id']
        try:
            doc = DB[coll].find_one({'_id': ObjectId(doc_id)})
        except Exception:
            doc = None
        if not doc:
            continue
        existing_lat = doc.get('lat')
        existing_lon = doc.get('lon')
        # try geocode using full doc
        result = geocode_address(doc.get('adresse_brute', ''), doc.get('gouvernorat', ''), doc.get('ville', ''), doc=doc)
        candidate = None
        if result:
            candidate = {'lat': result.get('lat'), 'lon': result.get('lon'), 'provider': result.get('provider'), 'query': result.get('geocoded_query')}
        preview.append({
            'collection': coll,
            'id': doc_id,
            'titre': doc.get('titre'),
            'url': doc.get('url'),
            'existing': {'lat': existing_lat, 'lon': existing_lon},
            'candidate': candidate
        })

# summarize
improvements = [p for p in preview if p['candidate'] and (round(p['candidate']['lat'],6)!=round(p['existing']['lat'],6) or round(p['candidate']['lon'],6)!=round(p['existing']['lon'],6))]
nochange = [p for p in preview if p['candidate'] and (round(p['candidate']['lat'],6)==round(p['existing']['lat'],6) and round(p['candidate']['lon'],6)==round(p['existing']['lon'],6))]
missing = [p for p in preview if not p['candidate']]

out = {
    'total_checked': len(preview),
    'would_change': len(improvements),
    'no_change': len(nochange),
    'no_candidate': len(missing),
    'details': preview
}

with open('reports/regeocode_preview.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print('preview_saved', 'reports/regeocode_preview.json')
print('total_checked', out['total_checked'])
print('would_change', out['would_change'])
print('no_candidate', out['no_candidate'])
