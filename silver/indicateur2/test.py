from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017')
db = client['urban_data']

print("Collections :", db.list_collection_names())
print("\nantennes_detail :", db['antennes_detail'].count_documents({}))
print("fibre_paris :", db['fibre_paris'].count_documents({}))

print("\n--- Exemple antenne ---")
doc = db['antennes_detail'].find_one()
for k, v in doc.items():
    print(f"  {k}: {v}")